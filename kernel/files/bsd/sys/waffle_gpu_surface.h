#ifndef WAFFLE_GPU_SURFACE_H
#define WAFFLE_GPU_SURFACE_H
#include <stdint.h>
#include <stdbool.h>
/* Internal ownership token, never a userspace handle or a CPU cache alias.
 * Native MiniIOSurface backing is cached. It must not use the WC BO mapper. */
struct waffle_gpu_surface_backing {
 uintptr_t object,pixels;
 uint32_t surface,bytes,offset,stride,width,height;
 bool published,gpu_reading;
};
#define WAFFLE_SURFACE_READ_BATCH_MAX 1024u
#define WAFFLE_SURFACE_WAIT_MS 250u
typedef struct waffle_gpu_surface_backing *(*waffle_surface_read_getter)(const void *,uint32_t);
#ifdef __cplusplus
extern "C" {
#endif
bool waffle_gpu_surface_hold(uint32_t,struct waffle_gpu_surface_backing *);
uint64_t waffle_gpu_surface_page(const struct waffle_gpu_surface_backing *,uint32_t);
/* Tokens remain retained by caller. Acquisition is all-or-none, never holds
 * a subset while waiting for CPU writers. Getter must be pure and stable. */
bool waffle_gpu_surface_reads_begin(uint32_t,waffle_surface_read_getter,const void *,uint32_t wait_ms);
bool waffle_gpu_surface_reads_end(uint32_t,waffle_surface_read_getter,const void *);
bool waffle_gpu_surface_read_state(struct waffle_gpu_surface_backing *,uint32_t *readers,uint32_t *waiting);
bool waffle_gpu_surface_read_end_one(struct waffle_gpu_surface_backing *);
bool waffle_gpu_surface_release(struct waffle_gpu_surface_backing *,bool gpu_detached);
#ifdef __cplusplus
}
#endif
#endif
