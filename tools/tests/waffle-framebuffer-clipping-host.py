#!/usr/bin/env python3
"""Run actual framebuffer layer/row code against clipped, padded surfaces."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_text()
helpers = source[source.index('static inline uint32_t\nblend('):source.index('void\nIOMobileFramebuffer::helperMain(')]
layer = source[source.index('void\nIOMobileFramebuffer::drawLayer('):source.index('void\nIOMobileFramebuffer::reportFrameTimes(')]
harness = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
struct MiniIOSurface {
 struct {uint32_t width,height,bytesPerRow;} info;
 uint8_t *base;
 uint8_t *pixels(){return base;}
};
struct RowJob;
struct IOMobileFramebuffer {
 uint8_t *fBase;
 uint32_t fPanelWidth,fPanelHeight,fRowBytes,fWidth,fHeight;
 uint32_t *fColumn,*fBlendRow=nullptr,fBlendRowSize=0;
 uint16_t *fColumnWeight;
 bool fDiff=false;
 uint64_t fDiffPixels=0;
 uint32_t fDiffLeft=~0u,fDiffRight=0,fDiffTop=~0u,fDiffBottom=0;
 unsigned fThreads=1,fHelpersStarted=0,fHelpersBusy=0,fHelperGeneration=0;
 uint32_t *fHelperBlend[8]{};
 void *fHelperLock=nullptr;
 RowJob *fHelperJob=nullptr;
 void drawRows(const RowJob *,int32_t,int32_t,uint32_t *);
 void drawLayer(MiniIOSurface *,const int32_t *,const int32_t *);
};
static unsigned gFilter;
#define IONew(type,n) new type[n]
#define IODelete(p,type,n) delete[] p
#define THREAD_UNINT 0
static bool redwood_gpu_ready(){return false;}
static void redwood_gpu_to_memory(void *,uint64_t){assert(false);}
static void IOLockLock(void *){assert(false);}
static void IOLockUnlock(void *){assert(false);}
static void IOLockWakeup(void *,void *,bool){assert(false);}
static void IOLockSleep(void *,void *,int){assert(false);}
'''
tests = r'''
static uint32_t pattern(unsigned x,unsigned y){return 0xff000000u | ((x*23+y*3)%256)<<16 | ((y*19+x*7)%256)<<8 | ((x*11+y*13)%256);}
static uint32_t mix(uint32_t a,uint32_t b,unsigned w){
 uint32_t out=0;
 for(unsigned c=0;c<4;c++){unsigned v=(((a>>(c*8))&255)*(256-w)+((b>>(c*8))&255)*w)/256;out|=v<<(c*8);}
 return out;
}
static int at(int index,int input,int output){
 int64_t fixed=((int64_t(2)*index+1)*input-output)*128/output;
 return int(std::max<int64_t>(0,std::min<int64_t>((input-1)*256,fixed)));
}
int main(){
 const int w=19,h=23,pw=29,ph=31;
 const uint32_t sentinel=0xa5a5a5a5;
 std::vector<uint32_t> input((w+3)*h,sentinel), output((pw+5)*ph+16,sentinel);
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)input[y*(w+3)+x]=pattern(x,y);
 MiniIOSurface s={{w,h,(w+3)*4},(uint8_t *)input.data()};
 std::vector<uint32_t> columns(pw);std::vector<uint16_t> weights(pw);
 IOMobileFramebuffer fb{};fb.fBase=(uint8_t *)(output.data()+8);fb.fPanelWidth=pw;fb.fPanelHeight=ph;
 fb.fRowBytes=(pw+5)*4;fb.fWidth=pw;fb.fHeight=ph;fb.fColumn=columns.data();fb.fColumnWeight=weights.data();
 const int32_t destinations[][4]={
  {-40,0,7,9},{40,0,7,9},{0,-40,7,9},{0,40,7,9},
  {-5,-4,27,28},{18,20,27,28},{0,0,29,31},{3,4,11,13},{0,0,1,1},{4,2,19,23}
 };
 unsigned cases=0;
 for(gFilter=0;gFilter<=1;gFilter++)for(unsigned cropped=0;cropped<2;cropped++)for(const auto &dst:destinations){
  int32_t src[4]={cropped?3:0,cropped?2:0,cropped?11:w,cropped?13:h};
  std::fill(output.begin(),output.end(),sentinel);fb.drawLayer(&s,src,dst);
  for(int y=0;y<ph;y++)for(int x=0;x<pw+5;x++){
   uint32_t expected=sentinel;
   if(x<pw && x>=dst[0] && x<dst[0]+dst[2] && y>=dst[1] && y<dst[1]+dst[3]){
    if(dst[2]==src[2] && dst[3]==src[3] && dst[0]>=0 && dst[0]+dst[2]<=pw)
     expected=pattern(src[0]+x-dst[0],src[1]+y-dst[1]);
    else if(!gFilter)expected=pattern(src[0]+(x-dst[0])*src[2]/dst[2],src[1]+(y-dst[1])*src[3]/dst[3]);
    else {
     int ax=at(x-dst[0],src[2],dst[2]),ay=at(y-dst[1],src[3],dst[3]);
     int x0=ax/256,y0=ay/256,x1=std::min(x0+1,src[2]-1),y1=std::min(y0+1,src[3]-1);
     uint32_t a=mix(pattern(src[0]+x0,src[1]+y0),pattern(src[0]+x0,src[1]+y1),ay%256);
     uint32_t b=mix(pattern(src[0]+x1,src[1]+y0),pattern(src[0]+x1,src[1]+y1),ay%256);
     expected=mix(a,b,ax%256);
    }
   }
   assert(output[8+y*(pw+5)+x]==expected);
  }
  for(int i=0;i<8;i++)assert(output[i]==sentinel && output[output.size()-1-i]==sentinel);
  cases++;
 }
 delete[] fb.fBlendRow;
 assert(cases==40);
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.cpp').write_text(harness + helpers + layer + tests)
    subprocess.run(['c++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra',
                    '-Wno-unused-variable', '-fsanitize=address,undefined',
                    str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('PASS actual framebuffer: 40 filtered/unfiltered, cropped, offscreen, padded and scaled layers; independent pixels and canaries. No panel/GPU claim.')
