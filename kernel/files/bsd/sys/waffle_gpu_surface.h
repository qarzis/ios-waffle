#ifndef WAFFLE_GPU_SURFACE_H
#define WAFFLE_GPU_SURFACE_H
#include <stdint.h>
#include <stdbool.h>
/* Internal ownership token, never a userspace handle or a CPU cache alias.
 * Native MiniIOSurface backing is cached. It must not use the WC BO mapper. */
struct waffle_gpu_surface_backing {
 uintptr_t object,pixels;
 uint32_t surface,bytes,offset,stride,width,height;
 bool published;
};
#ifdef __cplusplus
extern "C" {
#endif
bool waffle_gpu_surface_hold(uint32_t,struct waffle_gpu_surface_backing *);
uint64_t waffle_gpu_surface_page(const struct waffle_gpu_surface_backing *,uint32_t);
bool waffle_gpu_surface_release(struct waffle_gpu_surface_backing *,bool gpu_detached);
#ifdef __cplusplus
}
#endif
#endif
