"""Actual C++ general BO allocation/physical pages/map/lifetime failure model."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=re.sub(r'^#include .*$','',(root/'kernel/files/iokit/Kernel/WaffleGPUMemory.cpp').read_text(),flags=re.M).replace('__asm__ volatile("dsb sy":::"memory");','').replace('__asm__ volatile("dc ivac, %0"::"r"(address):"memory");','host_cache_line(address,true);').replace('__asm__ volatile("dc cvac, %0"::"r"(address):"memory");','host_cache_line(address,false);')
h=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include "waffle_gpu_memory.h"
#include "waffle_gpu_surface.h"
static void *IOMallocZero(size_t size){return calloc(1,size);}
static void IOFree(void *p,size_t size){(void)size;free(p);}
static unsigned cache_cleaned,cache_invalidated;
static uintptr_t cache_first,cache_last;
static void host_cache_line(uintptr_t a,bool invalidate){assert(!(a&63));if(!cache_cleaned && !cache_invalidated)cache_first=a;cache_last=a;if(invalidate)cache_invalidated++;else cache_cleaned++;}
static bool surface_fail=true;static unsigned surface_holds,surface_drops;
bool waffle_gpu_surface_hold(uint32_t sid,struct waffle_gpu_surface_backing *b){
 if(surface_fail)return false;
 assert(sid==79 && b && !b->object);
 surface_holds++;*b={.object=0x1234,.pixels=0x10000000,.surface=79,.bytes=32768,.offset=0,.stride=3072,.width=750,.height=8,.published=false};return true;
}
uint64_t waffle_gpu_surface_page(const struct waffle_gpu_surface_backing *b,uint32_t off){assert(b && b->object && off<b->bytes);return 0x8000000+off*2;}
bool waffle_gpu_surface_release(struct waffle_gpu_surface_backing *b,bool detached){assert(b && b->object);if(b->published && !detached)return false;surface_drops++;*b={};return true;}

using IOByteCount=uint64_t;
static unsigned mode,releases,options_seen,maps;
static int kernel_task=7;static int current_task(){return mode==8?7:9;}
static constexpr unsigned kIODirectionInOut=3,kIOMemoryKernelUserShared=4,kIOMapWriteCombineCache=16,kIOMemoryMapperNone=0,kIOMapAnywhere=32,kIOMapUnique=64,kIOMapReadOnly=128;
class IOMemoryMap {public:uint64_t getAddress(){return 0x100000000ULL;}int unmap(){return 0;}void release(){}};
static IOMemoryMap mapping;
class IOBufferMemoryDescriptor {
public:void *memory=nullptr;uint32_t bytes=0;
static IOBufferMemoryDescriptor *inTaskWithOptions(int,unsigned,uint32_t,unsigned);
void *getBytesNoCopy(){return mode==2?(void *)((uintptr_t)memory+1):memory;}
uint64_t getPhysicalSegment(uint32_t offset,IOByteCount *length,unsigned options){
 assert(offset<bytes && !(offset&4095) && options==0);*length=mode==5?2048:4096;
 if(mode==3 && offset==4096)return 0;
 if(mode==4)return 1ULL<<36;
 if(mode==6)return 0x1000001;
 /* Deliberately noncontiguous physical4KiB pages. */
 return 0x1000000+offset*2;
}
IOMemoryMap *createMappingInTask(int task,uint64_t at,unsigned options,unsigned offset,unsigned length){
 assert(task==9 && !at && !offset && length==bytes && (options&(16|32|64))==(16|32|64));maps++;options_seen=options;return mode==7?nullptr:&mapping;
}
void release(){releases++;free(memory);memory=nullptr;}
};
static IOBufferMemoryDescriptor descriptor;
IOBufferMemoryDescriptor *IOBufferMemoryDescriptor::inTaskWithOptions(int task,unsigned options,uint32_t bytes,unsigned alignment){
 assert(task==7 && options==(3|4|16) && alignment==16384 && bytes && !(bytes&16383));
 if(mode==1)return nullptr;
 assert(!descriptor.memory);descriptor.memory=aligned_alloc(16384,bytes);assert(descriptor.memory);descriptor.bytes=bytes;memset(descriptor.memory,0xcd,bytes);return &descriptor;
}
'''
t=r'''
int main(){
 for(unsigned bytes:{4096u,8192u,16384u,4194304u,5242880u,WAFFLE_GPU_BO_MAX_BYTES}){
  for(unsigned flags:{WAFFLE_GPU_BO_WC,WAFFLE_GPU_BO_WC|WAFFLE_GPU_BO_READONLY}){
   struct waffle_gpu_memory bo={};mode=0;assert(waffle_gpu_memory_create(bytes,flags,&bo));
   assert(bo.bytes==bytes && bo.flags==flags && bo.allocation_bytes==((bytes+16383)&~16383u));
   for(unsigned i=0;i<bo.allocation_bytes;i++)assert(!((unsigned char *)bo.memory)[i]);
   for(unsigned i=0;i<bo.allocation_bytes;i+=4096)assert(waffle_gpu_memory_page(&bo,i)==0x1000000+i*2);
   assert(!waffle_gpu_memory_page(&bo,1) && !waffle_gpu_memory_page(&bo,bo.allocation_bytes));
   uintptr_t token=0;uint64_t address=0;assert(waffle_gpu_memory_map(&bo,true,&address,&token));assert(token && address==0x100000000ULL && (options_seen&128));
   bo.published=true;uintptr_t object=bo.object;assert(!waffle_gpu_memory_destroy(&bo,false) && bo.object==object);
   assert(waffle_gpu_memory_destroy(&bo,true) && !bo.object);
  }
 }
 for(mode=1;mode<=6;mode++){
  struct waffle_gpu_memory bo={};assert(!waffle_gpu_memory_create(16384,WAFFLE_GPU_BO_WC,&bo) && !bo.object && !descriptor.memory);
 }
 mode=0;struct waffle_gpu_memory bo={};
 assert(!waffle_gpu_memory_create(0,WAFFLE_GPU_BO_WC,&bo));assert(!waffle_gpu_memory_create(WAFFLE_GPU_BO_MAX_BYTES+1,WAFFLE_GPU_BO_WC,&bo));
 assert(!waffle_gpu_memory_create(4096,0x80000,&bo));assert(!waffle_gpu_memory_create(4096,WAFFLE_GPU_BO_WC|1,&bo));
 assert(waffle_gpu_memory_create(4096,WAFFLE_GPU_BO_WC,&bo));
 uintptr_t token=0;uint64_t address=0;mode=7;assert(!waffle_gpu_memory_map(&bo,false,&address,&token));mode=8;assert(!waffle_gpu_memory_map(&bo,false,&address,&token));mode=0;
 assert(waffle_gpu_memory_destroy(&bo,false));
 assert(!waffle_gpu_memory_surface(79,&bo) && !bo.object);
 surface_fail=false;assert(waffle_gpu_memory_surface(79,&bo) && surface_holds==1);
 assert(bo.storage==WAFFLE_GPU_STORAGE_SURFACE && bo.flags==WAFFLE_GPU_BO_CACHED && bo.memory==0x10000000);
 assert(waffle_gpu_memory_page(&bo,4096)==0x8002000);
 unsigned old_maps=maps;token=0;address=0x1234;
 assert(!waffle_gpu_memory_map(&bo,false,&address,&token) && !token && maps==old_maps && address==0x1234);
 assert(!waffle_gpu_memory_surface(79,&bo) && surface_holds==1);
 bo.published=true;
 assert(!waffle_gpu_memory_surface_sync(&bo,0,0,0));
 assert(!waffle_gpu_memory_surface_sync(&bo,bo.bytes,1,0));
 assert(!waffle_gpu_memory_surface_sync(&bo,0,16,2));
 assert(waffle_gpu_memory_surface_sync(&bo,64,16,WAFFLE_GPU_SURFACE_TO_GPU));
 assert(cache_cleaned==1 && !cache_invalidated && cache_first==bo.memory+64 && cache_last==cache_first);
 assert(waffle_gpu_memory_surface_sync(&bo,127,2,WAFFLE_GPU_SURFACE_TO_CPU));
 assert(cache_invalidated==2 && cache_last==bo.memory+128);
 assert(!waffle_gpu_memory_destroy(&bo,false) && !surface_drops);
 assert(waffle_gpu_memory_destroy(&bo,true) && surface_drops==1 && !bo.object && !bo.storage);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cc').write_text('#include <initializer_list>\n'+h+s+t)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.cc'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual general BO C++ storage:4KiB/8KiB/16KiB/4MiB zeroed WC/readonly,16KiB rounding, noncontiguous4KiB PA validation, allocation/map failures, published backing retained until GPU detach; host only')
