#!/usr/bin/env python3
"""Actual native-surface hold/pages/release; no GPU or cache transition mocked as success."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
def function(s,sig):
 a=s.index(sig);at=s.index('{',a);b=at+1;depth=1
 while depth:depth+=(s[b]=='{')-(s[b]=='}');b+=1
 return s[a:b]
s=(root/'kernel/files/iokit/Kernel/MiniIOSurface.cpp').read_text()
code=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include "waffle_gpu_surface.h"
#include "waffle_gpu_memory.h"
constexpr uint64_t PAGE_SIZE=16384;constexpr unsigned kIOMemoryMapperNone=0;
using IOByteCount=uint64_t;
static uint64_t round_page_64(uint64_t n){return (n+PAGE_SIZE-1)&~(PAGE_SIZE-1);}
static unsigned mode,held,copies,drops,page_queries;
struct Buffer {
 uint64_t capacity;
 uint64_t getCapacity(){return capacity;}
 uint64_t getPhysicalSegment(uint64_t offset,IOByteCount *length,unsigned options){
  assert(held && offset>=PAGE_SIZE && !(offset&4095) && offset<capacity && options==0);page_queries++;
  *length=mode==1?2048:4096;
  if(mode==2 && offset==PAGE_SIZE+4096)return 0;
  if(mode==3)return (1ULL<<36);
  if(mode==4)return 0x1000001;
  /* Deliberately noncontiguous physical pages, sharing the original header. */
  return 0x1000000+(offset-PAGE_SIZE)*2;
 }
};
struct minisurf_result {uint32_t allocSize,offset,bytesPerRow,width,height,pixelFormat,planeCount,bytesPerElement;};
struct MiniIOSurface {void *client;Buffer *memory;uint8_t *kbase,*kpixels;minisurf_result info;};
static MiniIOSurface surface;static Buffer memory;
static MiniIOSurface *MiniIOSurfaceCopy(uint32_t id){copies++;if(id!=79)return nullptr;held++;return &surface;}
static void MiniIOSurfaceDrop(MiniIOSurface *s){assert(s==&surface && held==1);held--;drops++;}
'''+ '\n'.join(function(s,sig) for sig in ['extern "C" uint64_t\nwaffle_gpu_surface_page(', 'extern "C" bool\nwaffle_gpu_surface_hold(', 'extern "C" bool\nwaffle_gpu_surface_release('])+r'''
static void reset(){
 assert(!held);mode=copies=drops=page_queries=0;
 surface={};surface.memory=&memory;surface.kbase=(uint8_t *)0x10000000;surface.kpixels=surface.kbase+PAGE_SIZE;
 surface.info={uint32_t(round_page_64(3008*1624)),0,3008,750,1624,0x42475241,0,4};memory.capacity=PAGE_SIZE+surface.info.allocSize;
}
int main(){
 reset();waffle_gpu_surface_backing b={};
 assert(!waffle_gpu_surface_hold(0,&b) && !copies);
 assert(!waffle_gpu_surface_hold(79,nullptr) && !copies);
 assert(!waffle_gpu_surface_hold(99,&b) && !held && !drops);
 for(unsigned n=0;n<1000;n++){
  reset();surface.info.bytesPerRow=n%2?3008:3072;
  surface.info.allocSize=round_page_64(uint64_t(surface.info.bytesPerRow)*1624);memory.capacity=PAGE_SIZE+surface.info.allocSize;
  assert(waffle_gpu_surface_hold(79,&b) && held==1 && !drops && b.object && b.pixels==(uintptr_t)surface.kpixels);
  assert(b.bytes==surface.info.allocSize && b.stride==surface.info.bytesPerRow && !b.published);
  assert(page_queries==b.bytes/4096 && waffle_gpu_surface_page(&b,0)==0x1000000 && waffle_gpu_surface_page(&b,4096)==0x1002000);
  assert(!waffle_gpu_surface_page(&b,1) && !waffle_gpu_surface_page(&b,b.bytes));
  auto original=b;assert(!waffle_gpu_surface_hold(79,&b) && !memcmp(&b,&original,sizeof(b)) && held==1);
  b.published=true;assert(!waffle_gpu_surface_release(&b,false) && held==1 && !drops && b.object);
  assert(waffle_gpu_surface_release(&b,true) && !held && drops==1 && !b.object && !b.published);
  assert(waffle_gpu_surface_release(&b,false) && drops==1);
 }
 for(unsigned n=1;n<=4;n++){
  reset();mode=n;memset(&b,0,sizeof(b));assert(!waffle_gpu_surface_hold(79,&b) && !held && drops==1 && !b.object);
 }
 for(unsigned n=0;n<12;n++){
  reset();b={};
  switch(n){case 0:surface.client=&surface;break;case 1:surface.info.pixelFormat=0;break;case 2:surface.info.planeCount=1;break;
   case 3:surface.info.bytesPerElement=8;break;case 4:surface.info.bytesPerRow=3000;break;case 5:surface.info.offset=1;break;
   case 6:surface.info.width=UINT32_MAX;break;case 7:surface.info.height=UINT32_MAX;break;case 8:surface.kpixels++;break;
   case 9:memory.capacity--;break;case 10:surface.info.allocSize=UINT32_MAX;break;case 11:surface.info.width=0;break;}
  assert(!waffle_gpu_surface_hold(79,&b) && !held && drops==1 && !b.object);
 }
 reset();b={};surface.info.height=1625;surface.info.allocSize=surface.info.bytesPerRow*1625;memory.capacity=PAGE_SIZE+round_page_64(surface.info.allocSize);
 /* Page-rounded backing has enough room for four-row GMEM overfetch. */
 assert(waffle_gpu_surface_hold(79,&b));assert(waffle_gpu_surface_release(&b,false));
 reset();b={};surface.info.height=4;surface.info.bytesPerRow=16384;surface.info.allocSize=65536;surface.info.offset=64;memory.capacity=PAGE_SIZE+65536;
 assert(!waffle_gpu_surface_hold(79,&b) && !held && drops==1); /* overfetch/range refusal */
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual retained surface:1000 balanced holds/drops, header exclusion/noncontiguous4KiB pages, cached backing unchanged, early release blocked after publication, pitch/format/planes/overflow/overfetch/PA/capacity failures; native lookup and physical page query modeled, no GPU PTE or cache mutation')
