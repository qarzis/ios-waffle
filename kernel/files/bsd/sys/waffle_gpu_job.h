#ifndef WAFFLE_GPU_JOB_H
#define WAFFLE_GPU_JOB_H
#include <stdint.h>
#include <stdbool.h>
#include "waffle_gpu_copy.h"
/* New bounded kernel-only blocking API. Caller serializes access, owns stable
 * kernel input/output storage, and keeps the parent owner live throughout.
 * Exactly256 pixels; fixed audited shader, not arbitrary PM4 or user pointers.
 * fence is zero unless complete GPU output and GPU-written token are verified. */
struct waffle_gpu_copy_job {
    const uint32_t *input;
    uint32_t *output;
    unsigned words;
    uint32_t fence;
    bool uploaded; /* E31: immutable, prevalidated user command/data BO contents. */
};
#define WAFFLE_JOB_EVENT_WORD 430u
#define WAFFLE_JOB_WAIT_WORD 435u
static inline bool waffle_job_buffer_valid(uintptr_t address,uintptr_t alias)
{
    if(!address || address>UINTPTR_MAX-1024 || (address&3))return false;
    return address+1024<=alias || address>=alias+16384;
}
static inline uint32_t waffle_job_word(const uint32_t *input,uint32_t fence,unsigned word,bool completed)
{
    if(word>=3328 && word<3584)return input[word-3328];
    if(completed && word>=3072 && word<3328)return input[word-3072];
    if(word==WAFFLE_JOB_EVENT_WORD || word==WAFFLE_JOB_WAIT_WORD)return fence;
    if(word==2048)return completed?fence:0;
    return waffle_copy_initial(2,word);
}
static inline uint32_t waffle_job_test_pixel(unsigned fence,unsigned pixel)
{
    const uint32_t masks[]={0x00010101u,0x002a173cu,0x0065ab19u};
    return waffle_copy_payload[3328+pixel]^masks[fence-1];
}
#endif
