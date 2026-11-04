#ifndef WAFFLE_GPU_SURFACE_WRITE_H
#define WAFFLE_GPU_SURFACE_WRITE_H
#include "waffle_gpu_writeback.h"
struct waffle_surface_write_ops {
 void *context;
 bool (*to_gpu)(void *);
 /* False is uncertain submission/completion, never permission to free. */
 bool (*execute)(void *,uint32_t *fence);
 bool (*to_cpu)(void *);
};
struct waffle_surface_write_result {
 uint32_t actual[4],fence,wrong;
 bool saved,attempted,completed,restored,uncertain;
};
/* Isolated caller owns the surface against CPU writers. Only execute() may
 * populate the GPU pattern; CPU saves/restores original words, never expected. */
static inline bool waffle_surface_write_check(const struct waffle_surface_write_ops *ops,
 volatile uint32_t *pixels,struct waffle_surface_write_result *r)
{
 if(!r)return false;
 *r=(struct waffle_surface_write_result){0};
 if(!ops || !pixels || !ops->to_gpu || !ops->execute || !ops->to_cpu)return false;
 uint32_t saved[4];
 for(unsigned i=0;i<4;i++)saved[i]=pixels[i];
 r->saved=true;
 if(!ops->to_gpu(ops->context))return false;
 r->attempted=true;
 if(!ops->execute(ops->context,&r->fence) || !r->fence){r->uncertain=true;return false;}
 r->completed=true;
 if(!ops->to_cpu(ops->context)){r->uncertain=true;return false;}
 for(unsigned i=0;i<4;i++){
  r->actual[i]=pixels[i];r->wrong+=r->actual[i]!=waffle_writeback_values[i];
 }
 for(unsigned i=0;i<4;i++)pixels[i]=saved[i];
 if(!ops->to_gpu(ops->context)){r->uncertain=true;return false;}
 r->restored=true;
 return r->wrong==0;
}
#endif
