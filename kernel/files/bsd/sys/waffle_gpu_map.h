#ifndef WAFFLE_GPU_MAP_H
#define WAFFLE_GPU_MAP_H
#include <stdint.h>
#include <stdbool.h>
/* Diagnostic handoff: owner retains BO backing until every mapping is revoked.
 * Token belongs to kernel; no IOMemoryMap pointer crosses the user boundary. */
#ifdef __cplusplus
extern "C" {
#endif
bool waffle_gpu_map_create(uintptr_t kernel_memory,bool readonly,uint64_t *address,uintptr_t *token);
bool waffle_gpu_map_revoke(uintptr_t *token);
#ifdef __cplusplus
}
#endif
#endif
