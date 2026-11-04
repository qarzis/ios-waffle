#!/usr/bin/env python3
"""Execute actual C++ metadata bridge and compare its existing Darwin Mesa ABI."""
from pathlib import Path
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
def function(source, signature):
    start=source.index(signature);at=source.index('{',start);end=at+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
source=(root/'kernel/files/iokit/Kernel/MiniIOSurface.cpp').read_text()
msm=(root/'kernel/files/bsd/sys/waffle_gpu_msm.h').read_text()
mesa=(root/'tools/mesa/drm-shim/xf86drm.h').read_text()
struct=re.search(r'struct waffle_msm_surface \{.*?\n\};',msm,re.S)[0]
native=re.search(r'struct redwood_drm_surface \{.*?\n\};',mesa,re.S)[0]
code=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cerrno>
#include <climits>
'''+struct+'\n'+native+r'''
#define WAFFLE_MSM_SURFACE_DESCRIBE UINT32_MAX
#define SAME(f) static_assert(offsetof(waffle_msm_surface,f)==offsetof(redwood_drm_surface,f));
static_assert(sizeof(waffle_msm_surface)==40 && sizeof(waffle_msm_surface)==sizeof(redwood_drm_surface));
SAME(surface) SAME(handle) SAME(size) SAME(offset) SAME(row_bytes) SAME(width) SAME(height) SAME(pixel_format) SAME(planes)
constexpr uint64_t PAGE_SIZE=16384;
static uint64_t round_page_64(uint64_t n){return (n+PAGE_SIZE-1)&~(PAGE_SIZE-1);}
struct Buffer {uint64_t capacity;uint64_t getCapacity(){return capacity;}};
struct Info {uint32_t allocSize,offset,bytesPerRow,width,height,pixelFormat,planeCount;};
struct MiniIOSurface {void *client;Buffer *memory;uint8_t *kbase,*kpixels;Info info;};
static MiniIOSurface object;static Buffer memory;
static unsigned copies,drops,held;
static MiniIOSurface *MiniIOSurfaceCopy(uint32_t id){copies++;assert(id);if(id!=79)return nullptr;held++;return &object;}
static void MiniIOSurfaceDrop(MiniIOSurface *s){assert(s==&object && held==1);held--;drops++;}
'''+function(source,'extern "C" int\nwaffle_gpu_surface_describe(')+r'''
static void reset(){
 object={};memory.capacity=PAGE_SIZE+round_page_64(3072ULL*1624);
 object.memory=&memory;object.kbase=(uint8_t *)0x10000000;object.kpixels=object.kbase+PAGE_SIZE;
 object.info={uint32_t(3072*1624),0,3072,750,1624,0x42475241,0};copies=drops=held=0;
}
static waffle_msm_surface request(){waffle_msm_surface r;memset(&r,0xa5,sizeof(r));r.surface=79;r.handle=UINT32_MAX;return r;}
int main(){
 reset();auto r=request();auto prior=r;
 assert(waffle_gpu_surface_describe(nullptr)==EINVAL && !copies);
 r.surface=0;assert(waffle_gpu_surface_describe(&r)==EINVAL && !copies);
 r=prior;r.handle=0;assert(waffle_gpu_surface_describe(&r)==EINVAL && !copies);
 r=prior;r.surface=65535;auto before=r;assert(waffle_gpu_surface_describe(&r)==ENOENT && !memcmp(&r,&before,sizeof(r)) && !drops);
 for(unsigned n=0;n<8;n++){
  reset();r=request();before=r;
  switch(n){case 0:object.client=&object;break;case 1:object.memory=nullptr;break;case 2:object.kbase=nullptr;break;
   case 3:object.kpixels++;break;case 4:object.info.allocSize=0;break;case 5:memory.capacity=PAGE_SIZE;break;
   case 6:memory.capacity=round_page_64(object.info.allocSize);break;case 7:memory.capacity=PAGE_SIZE+round_page_64(object.info.allocSize)-1;break;}
  assert(waffle_gpu_surface_describe(&r)!=0 && !memcmp(&r,&before,sizeof(r)) && copies==1 && drops==1 && !held);
 }
 for(unsigned n=0;n<10000;n++){
  reset();r=request();object.info.offset=128;object.info.bytesPerRow=n%2?3008:3072;
  object.info.pixelFormat=n%3?0x42475241:0x12345678;object.info.planeCount=n%3;
  const auto original=object.info;
  assert(!waffle_gpu_surface_describe(&r) && copies==1 && drops==1 && !held && !r.handle);
  assert(r.surface==79 && r.size==round_page_64(original.allocSize) && r.offset==128 && r.row_bytes==original.bytesPerRow);
  assert(r.width==750 && r.height==1624 && r.pixel_format==original.pixelFormat && r.planes==original.planeCount);
  assert(!memcmp(&object.info,&original,sizeof(original)));
 }
}
'''
with tempfile.TemporaryDirectory() as t:
    p=Path(t);(p/'test.cpp').write_text(code)
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS actual surface descriptor: exact native Mesa40-byte ABI/all offsets, balanced hold/drop over10000 snapshots, absent/client/malformed backing rejection and no failure output writes; native lookup/backing modeled, no GPU mapping')
