#ifndef WAFFLE_GPU_REGISTRY_H
#define WAFFLE_GPU_REGISTRY_H
#include "waffle_gpu_memory.h"
#define WAFFLE_GPU_BO_VA_BASE 0x100000000ULL
/* Bounded general heap, independent from 32-bit firmware regions. No handle
 * reuse or GPU VA reuse until context destruction; failed publication poisons
 * the registry and retains all backing for parent-controlled GPU detach. */
struct waffle_gpu_registry {
 struct waffle_gpu_memory buffers[WAFFLE_GPU_BO_LIMIT];
 uint32_t count,used;
 bool poisoned;
};
struct waffle_gpu_registry_ops {
 bool (*idle)(void *);
 bool (*vacant)(void *,uint64_t);
 bool (*map_page)(void *,uint64_t,uint64_t,bool);
 void (*clean)(void *);
 bool (*tlb)(void *);
 void *context;
};
static inline bool waffle_gpu_registry_flags(uint64_t bytes,uint32_t flags)
{
 return bytes && bytes<=WAFFLE_GPU_BO_MAX_BYTES &&
  (flags==WAFFLE_GPU_BO_WC || flags==(WAFFLE_GPU_BO_WC|WAFFLE_GPU_BO_READONLY));
}
static inline struct waffle_gpu_memory *waffle_gpu_registry_new(struct waffle_gpu_registry *r,
 const struct waffle_gpu_registry_ops *ops,uint64_t bytes,uint32_t flags)
{
 if(!r || !ops || !ops->idle || !ops->vacant || !ops->map_page || !ops->clean || !ops->tlb ||
    r->poisoned || r->count>=WAFFLE_GPU_BO_LIMIT || !waffle_gpu_registry_flags(bytes,flags))return 0;
 uint32_t allocated=((uint32_t)bytes+16383)&~16383u;
 if(r->used>WAFFLE_GPU_BO_HEAP_BYTES || allocated>WAFFLE_GPU_BO_HEAP_BYTES-r->used || !ops->idle(ops->context))return 0;
 uint64_t address=WAFFLE_GPU_BO_VA_BASE+r->used;
 for(uint32_t off=0;off<allocated;off+=4096)if(!ops->vacant(ops->context,address+off))return 0;
 struct waffle_gpu_memory *bo=&r->buffers[r->count];
 if(!waffle_gpu_memory_create(bytes,flags,bo))return 0;
 bo->gpu_va=address;
 ++r->count;r->used+=allocated;
 /* Mark before touching any PTE: uncertain partial publication retains BO. */
 bo->published=true;
 for(uint32_t off=0;off<allocated;off+=4096){
  uint64_t pa=waffle_gpu_memory_page(bo,off);
  if(!pa || !ops->map_page(ops->context,address+off,pa,(flags&WAFFLE_GPU_BO_READONLY)!=0)){
   r->poisoned=true;return 0;
  }
 }
 ops->clean(ops->context);
 if(!ops->tlb(ops->context)){r->poisoned=true;return 0;}
 return bo;
}
static inline bool waffle_gpu_registry_destroy(struct waffle_gpu_registry *r,bool gpu_detached)
{
 if(!r || !gpu_detached)return false;
 for(uint32_t i=0;i<r->count;i++)if(!waffle_gpu_memory_destroy(&r->buffers[i],true))return false;
 r->count=r->used=0;r->poisoned=false;return true;
}
#endif
