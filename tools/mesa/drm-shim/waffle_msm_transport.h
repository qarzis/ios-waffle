#ifndef WAFFLE_MSM_TRANSPORT_H
#define WAFFLE_MSM_TRANSPORT_H
#include "waffle_gpu_msm.h"
/* Encode only the documented MSM requests supported by the general Waffle
 * endpoint. Direct drmIoctl retains its caller-supplied request encoding. */
static inline unsigned long waffle_msm_request(unsigned number,size_t size)
{
#define REQ(n,t,r) case n:return size==sizeof(t)?r:0
 switch(number){
 REQ(0x40,struct waffle_msm_param,WAFFLE_MSM_PARAM);
 REQ(0x42,struct waffle_msm_gem_new,WAFFLE_MSM_NEW);
 REQ(0x43,struct waffle_msm_gem_info,WAFFLE_MSM_INFO);
 REQ(0x44,struct waffle_msm_cpu_prep,WAFFLE_MSM_CPU_PREP);
 REQ(0x45,struct waffle_msm_cpu_fini,WAFFLE_MSM_CPU_FINI);
 REQ(0x46,struct waffle_msm_submit,WAFFLE_MSM_SUBMIT);
 REQ(0x47,struct waffle_msm_wait,WAFFLE_MSM_WAIT);
 REQ(0x48,struct waffle_msm_madvise,WAFFLE_MSM_MADVISE);
 REQ(0x4a,struct waffle_msm_queue,WAFFLE_MSM_QUEUE_NEW);
 REQ(0x4b,uint32_t,WAFFLE_MSM_QUEUE_CLOSE);
 REQ(0x4c,struct waffle_msm_queue_query,WAFFLE_MSM_QUEUE_QUERY);
 REQ(0x09,struct waffle_msm_close,WAFFLE_MSM_CLOSE);
 default:return 0;
 }
#undef REQ
}
#endif
