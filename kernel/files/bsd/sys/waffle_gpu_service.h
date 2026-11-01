#ifndef WAFFLE_GPU_SERVICE_H
#define WAFFLE_GPU_SERVICE_H
#include <stdbool.h>
#include "waffle_gpu_job.h"
/* Bounded kernel-only context; try operations refuse concurrent callers.
 * No user pointer or generic PM4 ABI. End consumes *context only when it
 * actually stops the parent; busy refusal leaves *context intact. */
struct waffle_gpu_context;
struct waffle_gpu_context *waffle_gpu_context_begin(void);
bool waffle_gpu_context_copy(struct waffle_gpu_context *,struct waffle_gpu_copy_job *);
bool waffle_gpu_context_end(struct waffle_gpu_context **);
bool waffle_gpu_service_probe(void);
/* Internal parent transport, called only with the service lock held. */
struct waffle_gpu_parent;
struct waffle_gpu_parent *waffle_gpu_parent_begin(void);
bool waffle_gpu_parent_copy(struct waffle_gpu_parent *,struct waffle_gpu_copy_job *);
bool waffle_gpu_parent_end(struct waffle_gpu_parent *);
#endif
