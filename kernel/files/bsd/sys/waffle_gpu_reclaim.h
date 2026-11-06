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
 uint32_t mapped=waffle_gpu_memory_gpu_bytes(bo);
 if(!owned || !bo->object || !bo->published || !bo->allocation_bytes ||
    (bo->allocation_bytes&16383) || bo->allocation_bytes>r->used ||
    (bo->gpu_va&(bo->mapped_bytes?4095:16383)) || bo->gpu_va<WAFFLE_GPU_BO_VA_BASE ||
    bo->gpu_va>WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES ||
    mapped>WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES-bo->gpu_va ||
    !mapped || (mapped&4095) || mapped>bo->allocation_bytes || !base->idle(base->context))return false;
 uint32_t bytes=bo->allocation_bytes;
 bool readonly=(bo->flags&WAFFLE_GPU_BO_READONLY)!=0;
 /* Validate every leaf before changing the first one. */
 for(uint32_t off=0;off<mapped;off+=4096){
  uint64_t pa=waffle_gpu_memory_page(bo,off);
  if(!pa || !ops->owns_page(base->context,bo->gpu_va+off,pa,readonly))return false;
 }
 /* Any uncertainty after this point retains backing and forbids more work. */
 r->poisoned=true;
 for(uint32_t off=0;off<mapped;off+=4096)
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
/* Native IOVA placement exposes logical 4KiB pages independently of 16KiB
 * CPU backing. The ordinary allocation/publication path is unchanged.
 * Validate every old page and target collision before modifying a leaf. */
static inline bool waffle_gpu_registry_relocate_access(struct waffle_gpu_registry *r,
 const struct waffle_gpu_reclaim_ops *ops,struct waffle_gpu_memory *bo,
 uint64_t address,bool cpu_unmapped,bool readonly)
{
 if(!r || !r->buffers || r->poisoned || !ops || !ops->registry ||
    !ops->owns_page || !ops->unmap_page || !bo || !cpu_unmapped)return false;
 const struct waffle_gpu_registry_ops *b=ops->registry;
 if(!b->idle || !b->vacant || !b->map_page || !b->clean || !b->tlb)return false;
 bool owned=false;for(uint32_t i=0;i<r->count;i++)if(bo==&r->buffers[i])owned=true;
 uint32_t old_bytes=waffle_gpu_memory_gpu_bytes(bo);
 uint32_t bytes=(bo->bytes+4095u)&~4095u;
 uint64_t end=WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES;
 if(!owned || !bo->object || !bo->published || !bytes || !bo->bytes || bo->bytes>bo->allocation_bytes ||
    !old_bytes || (old_bytes&4095) || old_bytes>bo->allocation_bytes || bytes>bo->allocation_bytes || bo->allocation_bytes>r->used ||
    (address&4095) || address<WAFFLE_GPU_BO_VA_BASE || address>=end || bytes>end-address ||
    (bo->gpu_va&4095) || bo->gpu_va<WAFFLE_GPU_BO_VA_BASE || bo->gpu_va>=end || old_bytes>end-bo->gpu_va ||
    !b->idle(b->context))return false;
 bool old_ro=(bo->flags&WAFFLE_GPU_BO_READONLY)!=0,ro=readonly;
 for(uint32_t off=0;off<old_bytes;off+=4096){
  uint64_t pa=waffle_gpu_memory_page(bo,off);
  if(!pa || !ops->owns_page(b->context,bo->gpu_va+off,pa,old_ro))return false;
 }
 if(address==bo->gpu_va && bytes==old_bytes && old_ro==ro){bo->mapped_bytes=bytes;return true;}
 for(uint32_t off=0;off<bytes;off+=4096){
  uint64_t va=address+off;
  /* Overlap with this same validated old mapping is allowed; it is removed
   * completely and flushed before any new address is published. */
  if(va>=bo->gpu_va && va-bo->gpu_va<old_bytes)continue;
  if(!b->vacant(b->context,va))return false;
 }
 r->poisoned=true;
 for(uint32_t off=0;off<old_bytes;off+=4096)
  if(!ops->unmap_page(b->context,bo->gpu_va+off,waffle_gpu_memory_page(bo,off),old_ro))return false;
 b->clean(b->context);
 if(!b->tlb(b->context) || !b->idle(b->context))return false;
 for(uint32_t off=0;off<bytes;off+=4096)
  if(!b->map_page(b->context,address+off,waffle_gpu_memory_page(bo,off),ro))return false;
 b->clean(b->context);
 if(!b->tlb(b->context) || !b->idle(b->context))return false;
 bo->gpu_va=address;bo->mapped_bytes=bytes;
 bo->flags=(bo->flags&~WAFFLE_GPU_BO_READONLY)|(ro?WAFFLE_GPU_BO_READONLY:0);
 r->poisoned=false;return true;
}
static inline bool waffle_gpu_registry_relocate(struct waffle_gpu_registry *r,
 const struct waffle_gpu_reclaim_ops *ops,struct waffle_gpu_memory *bo,uint64_t address,bool cpu_unmapped)
{
 return waffle_gpu_registry_relocate_access(r,ops,bo,address,cpu_unmapped,bo && (bo->flags&WAFFLE_GPU_BO_READONLY));
}
#endif
