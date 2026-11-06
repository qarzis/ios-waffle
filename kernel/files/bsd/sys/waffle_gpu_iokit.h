#ifndef WAFFLE_GPU_IOKIT_H
#define WAFFLE_GPU_IOKIT_H
#include "waffle_unixnu_gpu.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Exclusive diagnostic connection, independent of cdev FD lifetime. */
int waffle_gpu_iokit_open(void *owner);
int waffle_gpu_iokit_call(void *owner,struct waffle_unixnu_call *);
int waffle_gpu_iokit_close(void *owner);
/* Borrowed IOBufferMemoryDescriptor, only while the caller holds its client
 * gate and a matching CPU lease. Never crosses the userspace boundary. */
uintptr_t waffle_gpu_iokit_memory(void *owner,uint32_t token);
bool waffle_gpu_iokit_register(void);
#ifdef __cplusplus
}
#endif
#endif
