#ifndef WAFFLE_GPU_REGISTRY_H
#define WAFFLE_GPU_REGISTRY_H
#include "waffle_gpu_memory.h"
#define WAFFLE_GPU_BO_VA_BASE 0x100000000ULL
/* Bounded general heap, independent from 32-bit firmware regions. Handles
 * include a generation. Only completely revoked slots/VA holes may be reused; failed
 * publication poisons the registry and retains backing until GPU detach. */
struct waffle_gpu_registry {
 struct waffle_gpu_memory *buffers;
 void (*release_storage)(uintptr_t,uint32_t);
 uint32_t storage_bytes;
 uint32_t count,used,issued;
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
static inline bool waffle_gpu_registry_vacant_range(const struct waffle_gpu_registry_ops *ops,
 uint64_t address,uint32_t allocated)
{
 for(uint32_t off=0;off<allocated;off+=4096)if(!ops->vacant(ops->context,address+off))return false;
 return true;
}
/* Keep the old append placement as a fast path. After a proven revocation,
 * physical usage is no longer a VA frontier: search vacant, aligned holes
 * within the original bounded window instead of extending that window. */
static inline uint64_t waffle_gpu_registry_find_hole(const struct waffle_gpu_registry *r,
 const struct waffle_gpu_registry_ops *ops,uint32_t allocated)
{
 uint64_t end=WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES-allocated;
 uint64_t hint=WAFFLE_GPU_BO_VA_BASE+r->used;
 if(hint<=end && waffle_gpu_registry_vacant_range(ops,hint,allocated))return hint;
 for(uint64_t address=WAFFLE_GPU_BO_VA_BASE;address<=end;address+=16384)
  if(address!=hint && waffle_gpu_registry_vacant_range(ops,address,allocated))return address;
 return 0;
}
static inline struct waffle_gpu_memory *waffle_gpu_registry_new(struct waffle_gpu_registry *r,
 const struct waffle_gpu_registry_ops *ops,uint64_t bytes,uint32_t flags)
{
 if(!r || !r->buffers || !ops || !ops->idle || !ops->vacant || !ops->map_page || !ops->clean || !ops->tlb ||
    r->poisoned || r->count>WAFFLE_GPU_BO_LIMIT || r->issued==UINT32_MAX || !waffle_gpu_registry_flags(bytes,flags))return 0;
 uint32_t slot=0;
 while(slot<r->count && r->buffers[slot].object)slot++;
 if(slot>=WAFFLE_GPU_BO_LIMIT)return 0;
 uint32_t allocated=((uint32_t)bytes+16383)&~16383u;
 if(r->used>WAFFLE_GPU_BO_HEAP_BYTES || allocated>WAFFLE_GPU_BO_HEAP_BYTES-r->used || !ops->idle(ops->context))return 0;
 uint64_t address=waffle_gpu_registry_find_hole(r,ops,allocated);
 if(!address)return 0;
 struct waffle_gpu_memory *bo=&r->buffers[slot];
 if(!waffle_gpu_memory_create(bytes,flags,bo))return 0;
 bo->gpu_va=address;
 if(slot==r->count)r->count++;
 bo->serial=++r->issued;r->used+=allocated;
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
/* Transfer one prepared retained surface into the existing publication
 * protocol. Before the move, every failure leaves ownership with the caller.
 * After it, even uncertain PTE/TLB failure retains storage in this registry. */
static inline struct waffle_gpu_memory *waffle_gpu_registry_adopt(struct waffle_gpu_registry *r,
 const struct waffle_gpu_registry_ops *ops,struct waffle_gpu_memory *prepared)
{
 if(!r || !r->buffers || !ops || !ops->idle || !ops->vacant || !ops->map_page || !ops->clean || !ops->tlb ||
    !prepared || !prepared->object || !prepared->memory || prepared->published || prepared->gpu_va || prepared->serial ||
    prepared->storage!=WAFFLE_GPU_STORAGE_SURFACE ||
    (prepared->flags!=WAFFLE_GPU_BO_CACHED && prepared->flags!=(WAFFLE_GPU_BO_CACHED|WAFFLE_GPU_BO_READONLY)) ||
    !prepared->bytes || prepared->bytes>WAFFLE_GPU_BO_MAX_BYTES || prepared->allocation_bytes!=prepared->bytes ||
    (prepared->allocation_bytes&16383) || r->poisoned || r->count>WAFFLE_GPU_BO_LIMIT || r->issued==UINT32_MAX)return 0;
 /* A registry entry cannot be moved into itself or another live slot. */
 uintptr_t input=(uintptr_t)prepared,base=(uintptr_t)r->buffers;
 if(input>=base && input-base<(uintptr_t)WAFFLE_GPU_BO_LIMIT*sizeof(*prepared))return 0;
 uint32_t slot=0;
 while(slot<r->count && r->buffers[slot].object)slot++;
 if(slot>=WAFFLE_GPU_BO_LIMIT)return 0;
 uint32_t allocated=prepared->allocation_bytes;
 if(r->used>WAFFLE_GPU_BO_HEAP_BYTES || allocated>WAFFLE_GPU_BO_HEAP_BYTES-r->used || !ops->idle(ops->context))return 0;
 uint64_t address=waffle_gpu_registry_find_hole(r,ops,allocated);
 if(!address)return 0;
 struct waffle_gpu_memory *bo=&r->buffers[slot];
 *bo=*prepared;*prepared=(struct waffle_gpu_memory){0};
 bo->gpu_va=address;bo->serial=++r->issued;r->used+=allocated;
 if(slot==r->count)r->count++;
 bo->published=true;
 for(uint32_t off=0;off<allocated;off+=4096){
  uint64_t pa=waffle_gpu_memory_page(bo,off);
  if(!pa || !ops->map_page(ops->context,address+off,pa,(bo->flags&WAFFLE_GPU_BO_READONLY)!=0)){
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
 for(uint32_t i=0;i<r->count;i++)if(r->buffers[i].object && !waffle_gpu_memory_destroy(&r->buffers[i],true))return false;
 if(r->release_storage && r->buffers)r->release_storage((uintptr_t)r->buffers,r->storage_bytes);
 r->buffers=0;r->release_storage=0;r->storage_bytes=0;
 r->count=r->used=r->issued=0;r->poisoned=false;return true;
}
#endif
