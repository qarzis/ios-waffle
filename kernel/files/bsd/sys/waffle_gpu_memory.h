#ifndef WAFFLE_GPU_MEMORY_H
#define WAFFLE_GPU_MEMORY_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_GPU_BO_HEAP_BYTES (192u*1024u*1024u)
/* Native compositor requests include 10 and 12 MiB objects. The registry
 * enforces aggregate residency before allocation; one object may consume
 * any remaining part of that same bounded heap. */
#define WAFFLE_GPU_BO_MAX_BYTES WAFFLE_GPU_BO_HEAP_BYTES
/* Virtual placement can contain vacant holes without consuming backing. */
#define WAFFLE_GPU_BO_VA_BYTES (256u*1024u*1024u)
/* Handle generations retain the qualified 8192-slot encoding independently
 * of physical residency. Increasing backing must not change that ABI. */
#define WAFFLE_GPU_BO_LIMIT 8192u
#define WAFFLE_GPU_BO_WC 0x00020000u
#define WAFFLE_GPU_BO_READONLY 2u
#define WAFFLE_GPU_BO_CACHED 0x00080000u
#define WAFFLE_GPU_STORAGE_OWNED 0u
#define WAFFLE_GPU_STORAGE_SURFACE 1u
struct waffle_gpu_memory {
 uintptr_t object,memory;
 uint64_t gpu_va;
 uint32_t bytes,allocation_bytes,flags,serial;
 bool published;
 uint32_t storage;
};
#ifdef __cplusplus
extern "C" {
#endif
/* Internal preparation only: no registry publication or user import handle. */
bool waffle_gpu_memory_surface(uint32_t surface,struct waffle_gpu_memory *);
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *);
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *,uint32_t offset);
bool waffle_gpu_memory_map(const struct waffle_gpu_memory *,bool readonly,uint64_t *address,uintptr_t *token);
/* Caller owns CPU access, and DEVICE_TO_CPU requires proven GPU completion.
 * These operations do not establish ownership or wait on a fence. */
#define WAFFLE_GPU_SURFACE_TO_GPU 0u
#define WAFFLE_GPU_SURFACE_TO_CPU 1u
/* Caller pins every BO until end; acquisition is atomic across the batch. */
bool waffle_gpu_memory_surface_reads_begin(struct waffle_gpu_memory *const *,uint32_t count,uint32_t wait_ms);
bool waffle_gpu_memory_surface_read_state(struct waffle_gpu_memory *,uint32_t *,uint32_t *);
bool waffle_gpu_memory_surface_reads_end(struct waffle_gpu_memory *const *,uint32_t count);
bool waffle_gpu_memory_surface_sync(const struct waffle_gpu_memory *,uint32_t offset,uint32_t bytes,unsigned direction);
/* A published object can only be destroyed after its GPU context is detached. */
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *,bool gpu_detached);
#ifdef __cplusplus
}
#endif
#endif
