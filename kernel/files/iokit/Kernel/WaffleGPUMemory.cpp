/* General sized, page-backed BO storage; mapping ownership stays in the parent. */
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <kern/task.h>
#include <libkern/libkern.h>
#include "../../bsd/sys/waffle_gpu_memory.h"
#include "../../bsd/sys/waffle_gpu_surface.h"
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t offset)
{
 if(!bo || !bo->object || (offset&4095) || offset>=bo->allocation_bytes)return 0;
 if(bo->storage==WAFFLE_GPU_STORAGE_SURFACE)
  return waffle_gpu_surface_page(reinterpret_cast<const struct waffle_gpu_surface_backing *>(bo->object),offset);
 if(bo->storage!=WAFFLE_GPU_STORAGE_OWNED)return 0;
 auto *memory=reinterpret_cast<IOBufferMemoryDescriptor *>(bo->object);
 IOByteCount length=0;
 uint64_t pa=memory->getPhysicalSegment(offset,&length,kIOMemoryMapperNone);
 return pa && !(pa&4095) && pa<(1ULL<<36) && length>=4096?pa:0;
}
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *bo)
{
 if(!bo || bo->object || bo->storage!=WAFFLE_GPU_STORAGE_OWNED || !bytes || bytes>WAFFLE_GPU_BO_MAX_BYTES ||
    (flags!=WAFFLE_GPU_BO_WC && flags!=(WAFFLE_GPU_BO_WC|WAFFLE_GPU_BO_READONLY)))return false;
 uint32_t allocated=(static_cast<uint32_t>(bytes)+16383)&~16383u;
 auto *memory=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
     kIODirectionInOut|kIOMemoryKernelUserShared|kIOMapWriteCombineCache,allocated,16384);
 if(!memory)return false;
 uintptr_t address=reinterpret_cast<uintptr_t>(memory->getBytesNoCopy());
 if(!address || (address&16383)){memory->release();return false;}
 *bo=(struct waffle_gpu_memory){.object=reinterpret_cast<uintptr_t>(memory),.memory=address,.gpu_va=0,
     .bytes=static_cast<uint32_t>(bytes),.allocation_bytes=allocated,.flags=flags,.serial=0,.published=false,.storage=WAFFLE_GPU_STORAGE_OWNED};
 for(uint32_t offset=0;offset<allocated;offset+=4096)if(!waffle_gpu_memory_page(bo,offset)){
     memory->release();*bo={};return false;
 }
 bzero(reinterpret_cast<void *>(address),allocated);
 __asm__ volatile("dsb sy":::"memory");
 return true;
}
bool waffle_gpu_memory_surface(uint32_t sid,struct waffle_gpu_memory *bo)
{
 if(!bo || bo->object || bo->published || bo->storage!=WAFFLE_GPU_STORAGE_OWNED || !sid)return false;
 auto *backing=static_cast<struct waffle_gpu_surface_backing *>(IOMallocZero(sizeof(struct waffle_gpu_surface_backing)));
 if(!backing)return false;
 if(!waffle_gpu_surface_hold(sid,backing)){IOFree(backing,sizeof(*backing));return false;}
 *bo=(struct waffle_gpu_memory){.object=reinterpret_cast<uintptr_t>(backing),.memory=backing->pixels,.gpu_va=0,
     .bytes=backing->bytes,.allocation_bytes=backing->bytes,.flags=WAFFLE_GPU_BO_CACHED,.serial=0,.published=false,
     .storage=WAFFLE_GPU_STORAGE_SURFACE};
 return true;
}
bool waffle_gpu_memory_map(const struct waffle_gpu_memory *bo,bool readonly,uint64_t *address,uintptr_t *token)
{
 if(!bo || !bo->object || bo->storage!=WAFFLE_GPU_STORAGE_OWNED || !address || !token || *token || current_task()==kernel_task)return false;
 *address=0;
 auto *memory=reinterpret_cast<IOBufferMemoryDescriptor *>(bo->object);
 auto *map=memory->createMappingInTask(current_task(),0,
     kIOMapAnywhere|kIOMapUnique|kIOMapWriteCombineCache|(readonly?kIOMapReadOnly:0),0,bo->allocation_bytes);
 if(!map)return false;
 uint64_t va=map->getAddress();
 if(!va || (va&16383)){map->unmap();map->release();return false;}
 *address=va;*token=reinterpret_cast<uintptr_t>(map);return true;
}
static void waffle_surface_cache_line(uintptr_t address,bool invalidate)
{
 if(invalidate)__asm__ volatile("dc ivac, %0"::"r"(address):"memory");
 else __asm__ volatile("dc cvac, %0"::"r"(address):"memory");
}
bool waffle_gpu_memory_surface_sync(const struct waffle_gpu_memory *bo,uint32_t offset,uint32_t bytes,unsigned direction)
{
 if(!bo || !bo->object || !bo->published || bo->storage!=WAFFLE_GPU_STORAGE_SURFACE ||
    (bo->flags!=WAFFLE_GPU_BO_CACHED && bo->flags!=(WAFFLE_GPU_BO_CACHED|WAFFLE_GPU_BO_READONLY)) || !bo->memory || (bo->memory&16383) ||
    !bytes || offset>bo->bytes || bytes>bo->bytes-offset || bo->bytes>bo->allocation_bytes ||
    (bo->allocation_bytes&16383) || direction>WAFFLE_GPU_SURFACE_TO_CPU ||
    bo->memory>UINTPTR_MAX-bo->allocation_bytes)return false;
 uintptr_t start=(bo->memory+offset)&~(uintptr_t)63;
 uintptr_t end=(bo->memory+offset+bytes+63)&~(uintptr_t)63;
 if(end<start || end-bo->memory>bo->allocation_bytes)return false;
 __asm__ volatile("dsb sy":::"memory");
 for(uintptr_t at=start;at<end;at+=64)waffle_surface_cache_line(at,direction==WAFFLE_GPU_SURFACE_TO_CPU);
 __asm__ volatile("dsb sy":::"memory");
 return true;
}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool gpu_detached)
{
 if(!bo || (bo->published && !gpu_detached))return false;
 if(bo->storage==WAFFLE_GPU_STORAGE_SURFACE){
  if(bo->object){
   auto *backing=reinterpret_cast<struct waffle_gpu_surface_backing *>(bo->object);
   backing->published=bo->published;
   if(!waffle_gpu_surface_release(backing,gpu_detached))return false;
   IOFree(backing,sizeof(*backing));
  }
 }else if(bo->storage==WAFFLE_GPU_STORAGE_OWNED){
  if(bo->object)reinterpret_cast<IOBufferMemoryDescriptor *>(bo->object)->release();
 }else return false;
 *bo={};return true;
}
