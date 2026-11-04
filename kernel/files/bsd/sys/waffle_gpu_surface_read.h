#ifndef WAFFLE_GPU_SURFACE_READ_H
#define WAFFLE_GPU_SURFACE_READ_H
#include "waffle_gpu_surface_write.h"
/* Mesa adreno_pm4.xml CP_MEM_TO_MEM=0x73; five payload words:
 * flags=0 (32-bit), destination64, source64. tu_query_pool.cc uses this form.
 * Four independent copies followed by CP_WAIT_MEM_WRITES. No HFI envelope. */
static inline unsigned waffle_surface_read_packet(uint32_t *out,unsigned capacity,uint64_t src,uint64_t dst)
{
 if(!out || capacity<25 || ((src|dst)&3) || src>UINT64_MAX-15 || dst>UINT64_MAX-15 ||
    !waffle_gpu_va_valid(src) || !waffle_gpu_va_valid(src+15) ||
    !waffle_gpu_va_valid(dst) || !waffle_gpu_va_valid(dst+15) ||
    (src<dst+16 && dst<src+16))return 0;
 for(unsigned i=0;i<4;i++){
  uint64_t s=src+4*i,d=dst+4*i;unsigned at=6*i;
  out[at]=0x70738005u;out[at+1]=0;
  out[at+2]=(uint32_t)d;out[at+3]=(uint32_t)(d>>32);
  out[at+4]=(uint32_t)s;out[at+5]=(uint32_t)(s>>32);
 }
 out[24]=0x70928000u;return 25;
}
/* CPU populates source only. Destination must be separate and GPU-populated.
 * Caller owns source against concurrent writers and provides completion/cache
 * callbacks. Uncertain completion leaves both allocations retained by caller. */
static inline bool waffle_surface_read_check(const struct waffle_surface_write_ops *ops,
 volatile uint32_t *source,volatile uint32_t *destination,struct waffle_surface_write_result *r)
{
 if(!r)return false;*r=(struct waffle_surface_write_result){0};
 if(!ops || !source || !destination || source==destination ||
    !ops->to_gpu || !ops->execute || !ops->to_cpu)return false;
 uint32_t saved[4];for(unsigned i=0;i<4;i++)saved[i]=source[i];r->saved=true;
 for(unsigned i=0;i<4;i++){source[i]=waffle_writeback_values[i];destination[i]=0xbad00000u+i;}
 if(!ops->to_gpu(ops->context)){
  for(unsigned i=0;i<4;i++)source[i]=saved[i];r->restored=true;return false;
 }
 r->attempted=true;
 if(!ops->execute(ops->context,&r->fence) || !r->fence){r->uncertain=true;return false;}
 r->completed=true;
 if(!ops->to_cpu(ops->context)){r->uncertain=true;return false;}
 for(unsigned i=0;i<4;i++){
  r->actual[i]=destination[i];r->wrong+=r->actual[i]!=waffle_writeback_values[i];
  r->wrong+=source[i]!=waffle_writeback_values[i];
 }
 for(unsigned i=0;i<4;i++)source[i]=saved[i];
 if(!ops->to_gpu(ops->context)){r->uncertain=true;return false;}
 r->restored=true;return !r->wrong;
}
#endif
