#ifndef WAFFLE_SURFACE_ACCESS_H
#define WAFFLE_SURFACE_ACCESS_H
#include <stdint.h>
#include <stdbool.h>
/* Private kernel state. Caller serializes every operation with gSurfaceLock.
 * CPU/CPU locking semantics stay unchanged; these counts bound GPU reads. */
struct waffle_surface_access {uint32_t cpu_writers,gpu_readers,waiting_writers;};
static inline bool waffle_surface_cpu_write_begin(struct waffle_surface_access *s,uint32_t *client)
{
 if(!s || !client || s->gpu_readers || s->cpu_writers==UINT32_MAX || *client==UINT32_MAX)return false;
 s->cpu_writers++;(*client)++;return true;
}
static inline bool waffle_surface_cpu_write_end(struct waffle_surface_access *s,uint32_t *client)
{
 if(!s || !client || !*client || s->cpu_writers<*client)return false;
 s->cpu_writers--;(*client)--;return true;
}
static inline bool waffle_surface_cpu_write_drop(struct waffle_surface_access *s,uint32_t *client)
{
 if(!s || !client || s->cpu_writers<*client)return false;
 s->cpu_writers-=*client;*client=0;return true;
}
static inline bool waffle_surface_cpu_wait_begin(struct waffle_surface_access *s)
{
 if(!s || s->waiting_writers==UINT32_MAX)return false;
 s->waiting_writers++;return true;
}
static inline bool waffle_surface_cpu_wait_end(struct waffle_surface_access *s)
{
 if(!s || !s->waiting_writers)return false;
 s->waiting_writers--;return true;
}
static inline bool waffle_surface_gpu_read_begin(struct waffle_surface_access *s)
{
 if(!s || s->cpu_writers || s->waiting_writers || s->gpu_readers==UINT32_MAX)return false;
 s->gpu_readers++;return true;
}
static inline bool waffle_surface_gpu_read_end(struct waffle_surface_access *s)
{
 if(!s || !s->gpu_readers)return false;
 s->gpu_readers--;return true;
}
#endif
