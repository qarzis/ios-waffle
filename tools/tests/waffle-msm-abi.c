#include <stddef.h>
#include "waffle_gpu_msm.h"
#include "drm-uapi/msm_drm.h"
#define SAME(a,b) _Static_assert((a)==(b),#a " must match pinned Mesa UAPI")
SAME(WAFFLE_MSM_PARAM,DRM_IOCTL_MSM_GET_PARAM);
SAME(WAFFLE_MSM_NEW,DRM_IOCTL_MSM_GEM_NEW);
SAME(WAFFLE_MSM_INFO,DRM_IOCTL_MSM_GEM_INFO);
SAME(WAFFLE_MSM_CPU_PREP,DRM_IOCTL_MSM_GEM_CPU_PREP);
SAME(WAFFLE_MSM_CPU_FINI,DRM_IOCTL_MSM_GEM_CPU_FINI);
SAME(WAFFLE_MSM_SUBMIT,DRM_IOCTL_MSM_GEM_SUBMIT);
SAME(WAFFLE_MSM_WAIT,DRM_IOCTL_MSM_WAIT_FENCE);
SAME(WAFFLE_MSM_MADVISE,DRM_IOCTL_MSM_GEM_MADVISE);
SAME(WAFFLE_MSM_QUEUE_NEW,DRM_IOCTL_MSM_SUBMITQUEUE_NEW);
SAME(WAFFLE_MSM_QUEUE_CLOSE,DRM_IOCTL_MSM_SUBMITQUEUE_CLOSE);
SAME(WAFFLE_MSM_QUEUE_QUERY,DRM_IOCTL_MSM_SUBMITQUEUE_QUERY);
SAME(WAFFLE_MSM_CLOSE,DRM_IOCTL_GEM_CLOSE);
SAME(offsetof(struct waffle_msm_submit,cmds),offsetof(struct drm_msm_gem_submit,cmds));
SAME(offsetof(struct waffle_msm_submit,queueid),offsetof(struct drm_msm_gem_submit,queueid));
SAME(offsetof(struct waffle_msm_param,value),offsetof(struct drm_msm_param,value));
int main(void){return 0;}
