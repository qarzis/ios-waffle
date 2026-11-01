#ifndef WAFFLE_GPU_RECLAIM_H
#define WAFFLE_GPU_RECLAIM_H
#include "waffle_gpu_registry.h"
/* CPU mappings must already be revoked; the owner serializes GPU work. */
struct waffle_gpu_reclaim_ops {
 const struct waffle_gpu_registry_ops *registry;
 bool (*owns_page)(void *,uint64_t,uint64_t,bool);
 bool (*unmap_page)(void *,uint64_t,uint64_t,bool);
};
static inline bool waffle_gpu_registry_reclaim(struct waffle_gpu_registry *r,
 const struct waffle_gpu_reclaim_ops *ops,struct waffle_gpu_memory *bo,bool cpu_unmapped)
{
 if(!r || !r->buffers || r->poisoned || !ops || !ops->registry ||
    !ops->owns_page || !ops->unmap_page || !cpu_unmapped)return false;
 const struct waffle_gpu_registry_ops *base=ops->registry;
 if(!base->idle || !base->clean || !base->tlb)return false;
 bool owned=false;
 for(uint32_t i=0;i<r->count;i++)if(bo==&r->buffers[i])owned=true;
 if(!owned || !bo->object || !bo->published || !bo->allocation_bytes ||
    (bo->allocation_bytes&16383) || bo->allocation_bytes>r->used ||
    (bo->gpu_va&16383) || bo->gpu_va<WAFFLE_GPU_BO_VA_BASE ||
    bo->gpu_va>WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_HEAP_BYTES ||
    bo->allocation_bytes>WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_HEAP_BYTES-bo->gpu_va ||
    !base->idle(base->context))return false;
 uint32_t bytes=bo->allocation_bytes;
 bool readonly=(bo->flags&WAFFLE_GPU_BO_READONLY)!=0;
 /* Validate every leaf before changing the first one. */
 for(uint32_t off=0;off<bytes;off+=4096){
  uint64_t pa=waffle_gpu_memory_page(bo,off);
  if(!pa || !ops->owns_page(base->context,bo->gpu_va+off,pa,readonly))return false;
 }
 /* Any uncertainty after this point retains backing and forbids more work. */
 r->poisoned=true;
 for(uint32_t off=0;off<bytes;off+=4096)
  if(!ops->unmap_page(base->context,bo->gpu_va+off,
                    waffle_gpu_memory_page(bo,off),readonly))return false;
 base->clean(base->context);
 if(!base->tlb(base->context) || !base->idle(base->context))return false;
 /* The GPU context remains live; this object is now unpublished. Do not
  * pretend the entire context was detached to bypass the destroy guard. */
 bo->published=false;
 if(!waffle_gpu_memory_destroy(bo,false))return false;
 r->used-=bytes;r->poisoned=false;
 return true;
}
#endif
