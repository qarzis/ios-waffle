#ifndef WAFFLE_DISPLAY_SOURCE_H
#define WAFFLE_DISPLAY_SOURCE_H
#include <stdint.h>
#include <stdbool.h>
struct waffle_display_source_stamp {uint32_t seed,hash;bool valid;};
/* Positive differences bracket a draw; unchanged16point samples do not prove
 * an entire surface stayed unchanged or exclude an in-progress writer. */
static inline struct waffle_display_source_stamp waffle_display_source_observe(const volatile uint32_t *seed,const void *pixels,uint64_t bytes,uint32_t width,uint32_t height,uint32_t stride)
{
 struct waffle_display_source_stamp s={0};
 if(!seed || !pixels || ((uintptr_t)pixels&3) || !width || !height || (stride&3) ||
    (uint64_t)width*4>stride || (uint64_t)(height-1)*stride+(uint64_t)width*4>bytes)return s;
 __atomic_thread_fence(__ATOMIC_SEQ_CST);
 s.seed=__atomic_load_n(seed,__ATOMIC_ACQUIRE);s.hash=2166136261u;
 for(unsigned y=0;y<4;y++)for(unsigned x=0;x<4;x++){
  uint64_t offset=((uint64_t)(height-1)*y/3)*stride+((uint64_t)(width-1)*x/3)*4;
  s.hash=(s.hash^*(const volatile uint32_t *)((const uint8_t *)pixels+offset))*16777619u;
 }
 __atomic_thread_fence(__ATOMIC_SEQ_CST);s.valid=true;return s;
}
#endif
