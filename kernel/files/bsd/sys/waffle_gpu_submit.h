#ifndef WAFFLE_GPU_SUBMIT_H
#define WAFFLE_GPU_SUBMIT_H
#include <stdint.h>
#include <stdbool.h>
#include "waffle_gpu_memory.h"
#define WAFFLE_GPU_SUBMIT_COMMANDS 16u
#define WAFFLE_GPU_SUBMIT_WORDS 1024u
#define WAFFLE_GPU_SUBMIT_TAIL_WORDS 15u
struct waffle_gpu_command {
 const struct waffle_gpu_memory *buffer;
 uint32_t offset,bytes;
};
struct waffle_gpu_submit_job {
 const struct waffle_gpu_command *commands;
 uint32_t count,fence;
};
/* Private kernel BO: user roots are copied verbatim then the already-qualified
 * Mesa A7xx completion tail is appended. No extra IB nesting level is added. */
static inline uint32_t waffle_gpu_submit_tail(unsigned index,uint32_t fence,uint64_t result_va)
{
 if(index==0)return 0x70268000u; /* Qualified CP_WAIT_FOR_IDLE before completion event. */
 switch(index-1){
 case 0:return 0x70460004u; /* CP_EVENT_WRITE7 CACHE_FLUSH_TS */
 case 1:return 0x08000016u;
 case 2:case 7:return (uint32_t)result_va;
 case 3:case 8:return (uint32_t)(result_va>>32);
 case 4:case 9:return fence;
 case 5:return 0x70bc8006u; /* CP_WAIT_REG_MEM, equal32 */
 case 6:return 0x13u;
 case 10:return 0xffffffffu;
 case 11:return 0x10u;
 case 12:return 0x70460001u;
 case 13:return 0x32u;
 default:return 0;
 }
}
static inline bool waffle_gpu_command_valid(const struct waffle_gpu_command *c)
{
 return c && c->buffer && c->buffer->object && c->buffer->published && c->bytes &&
  !(c->offset&3) && !(c->bytes&3) && c->offset<=c->buffer->bytes && c->bytes<=c->buffer->bytes-c->offset;
}
static inline uint32_t waffle_gpu_submit_initial(unsigned index,uint32_t command_words,
 const uint32_t *commands,uint32_t fence,uint64_t result_va,bool completed)
{
 if(index==2048)return completed?fence:0;
 if(index>=256 && index<256+command_words)return commands[index-256];
 if(index>=256+command_words && index<256+command_words+WAFFLE_GPU_SUBMIT_TAIL_WORDS)
  return waffle_gpu_submit_tail(index-256-command_words,fence,result_va);
 return 0xc0e00000u^index;
}
#endif
