#ifndef WAFFLE_GPU_MEMORY_H
#define WAFFLE_GPU_MEMORY_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_GPU_BO_MAX_BYTES (8u*1024u*1024u)
#define WAFFLE_GPU_BO_HEAP_BYTES (192u*1024u*1024u)
/* Virtual placement can contain vacant holes without consuming backing. */
#define WAFFLE_GPU_BO_VA_BYTES (256u*1024u*1024u)
/* Handle generations retain the qualified 8192-slot encoding independently
 * of physical residency. Increasing backing must not change that ABI. */
#define WAFFLE_GPU_BO_LIMIT 8192u
#define WAFFLE_GPU_BO_WC 0x00020000u
#define WAFFLE_GPU_BO_READONLY 2u
struct waffle_gpu_memory {
 uintptr_t object,memory;
 uint64_t gpu_va;
 uint32_t bytes,allocation_bytes,flags,serial;
 bool published;
};
#ifdef __cplusplus
extern "C" {
#endif
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *);
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *,uint32_t offset);
bool waffle_gpu_memory_map(const struct waffle_gpu_memory *,bool readonly,uint64_t *address,uintptr_t *token);
/* A published object can only be destroyed after its GPU context is detached. */
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *,bool gpu_detached);
#ifdef __cplusplus
}
#endif
#endif
