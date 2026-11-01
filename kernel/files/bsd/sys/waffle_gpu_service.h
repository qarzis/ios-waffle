#ifndef WAFFLE_GPU_SERVICE_H
#define WAFFLE_GPU_SERVICE_H
#include <stdbool.h>
#include "waffle_gpu_job.h"
#include "waffle_gpu_buffer.h"
#include "waffle_gpu_submit.h"
/* Bounded kernel-only context; try operations refuse concurrent callers.
 * No user pointer or generic PM4 ABI. End consumes *context only when it
 * actually stops the parent; busy refusal leaves *context intact. */
struct waffle_gpu_context;
struct waffle_gpu_context *waffle_gpu_context_begin(void);
bool waffle_gpu_context_copy(struct waffle_gpu_context *,struct waffle_gpu_copy_job *);
struct waffle_gpu_memory *waffle_gpu_context_memory_new(struct waffle_gpu_context *,uint64_t,uint32_t);
bool waffle_gpu_context_submit(struct waffle_gpu_context *,struct waffle_gpu_submit_job *);
bool waffle_gpu_context_end(struct waffle_gpu_context **);
bool waffle_gpu_service_probe(void);
bool waffle_gpu_user_register(void);
bool waffle_gpu_msm_register(void);
bool waffle_gpu_drm_register(void);
bool waffle_gpu_context_buffers(struct waffle_gpu_context *,struct waffle_gpu_buffer [2]);

/* Internal parent transport, called only with the service lock held. */
struct waffle_gpu_parent;
struct waffle_gpu_memory *waffle_gpu_parent_memory_new(struct waffle_gpu_parent *,uint64_t,uint32_t);
bool waffle_gpu_parent_submit(struct waffle_gpu_parent *,struct waffle_gpu_submit_job *);
bool waffle_gpu_parent_buffers(struct waffle_gpu_parent *,struct waffle_gpu_buffer [2]);
struct waffle_gpu_parent *waffle_gpu_parent_begin(void);
bool waffle_gpu_parent_copy(struct waffle_gpu_parent *,struct waffle_gpu_copy_job *);
bool waffle_gpu_parent_end(struct waffle_gpu_parent *);
#endif
