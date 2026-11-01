#ifndef WAFFLE_GPU_HANDLES_H
#define WAFFLE_GPU_HANDLES_H
#include "waffle_gpu_memory.h"
/* Generation remains part of the public32-bit handle. Never wrap a slot's
 * generation: a stale userspace handle must not alias a later allocation. */
static inline uint32_t waffle_gpu_handle_slot(uint32_t handle)
{
 return handle?(handle-1)%WAFFLE_GPU_BO_LIMIT:WAFFLE_GPU_BO_LIMIT;
}
static inline uint32_t waffle_gpu_handle_next(uint32_t previous,uint32_t slot)
{
 if(slot>=WAFFLE_GPU_BO_LIMIT)return 0;
 if(!previous)return slot+1;
 if(waffle_gpu_handle_slot(previous)!=slot || previous>UINT32_MAX-WAFFLE_GPU_BO_LIMIT)return 0;
 return previous+WAFFLE_GPU_BO_LIMIT;
}
#endif
