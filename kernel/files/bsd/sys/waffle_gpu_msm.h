#ifndef WAFFLE_GPU_MSM_H
#define WAFFLE_GPU_MSM_H
#include <stdint.h>
#include <sys/ioccom.h>
/* Exact legacy MSM UAPI layouts used by MacanGPU.cpp and Mesa drm-shim.
 * E31 supports two owned16KiB BOs and one audited191word compute IB only.
 * Upload/download is a diagnostic extension, not GEM mmap or a full DRM fd. */
struct waffle_msm_gem_new { uint64_t size; uint32_t flags,handle; };
struct waffle_msm_gem_info { uint32_t handle,info; uint64_t value; uint32_t len,pad; };
struct waffle_msm_submit_bo { uint32_t flags,handle; uint64_t presumed; };
struct waffle_msm_submit_cmd { uint32_t type,submit_idx,submit_offset,size,pad,nr_relocs; uint64_t relocs; };
struct waffle_msm_submit {
 uint32_t flags,fence,nr_bos,nr_cmds; uint64_t bos,cmds;
 int32_t fence_fd; uint32_t queueid; uint64_t in_syncobjs,out_syncobjs;
 uint32_t nr_in_syncobjs,nr_out_syncobjs,syncobj_stride,pad;
};
struct waffle_msm_wait { uint32_t fence,flags; int64_t seconds,nanoseconds; uint32_t queueid,pad; };
struct waffle_msm_close { uint32_t handle,pad; };
struct waffle_msm_transfer { uint64_t pointer; uint32_t handle,offset,bytes,flags; };
struct waffle_msm_report { uint32_t version,checks,wrong,fence,negative; };
#define WAFFLE_MSM_NEW _IOWR('d',0x42,struct waffle_msm_gem_new)
#define WAFFLE_MSM_INFO _IOWR('d',0x43,struct waffle_msm_gem_info)
#define WAFFLE_MSM_SUBMIT _IOWR('d',0x46,struct waffle_msm_submit)
#define WAFFLE_MSM_WAIT _IOW('d',0x47,struct waffle_msm_wait)
#define WAFFLE_MSM_CLOSE _IOW('d',0x09,struct waffle_msm_close)
#define WAFFLE_MSM_UPLOAD _IOW('W',0x50,struct waffle_msm_transfer)
#define WAFFLE_MSM_DOWNLOAD _IOW('W',0x51,struct waffle_msm_transfer)
#define WAFFLE_MSM_REPORT _IOW('W',0x52,struct waffle_msm_report)
_Static_assert(sizeof(struct waffle_msm_submit)==72,"MSM submit layout");
_Static_assert(sizeof(struct waffle_msm_submit_cmd)==32,"MSM command layout");
_Static_assert(sizeof(struct waffle_msm_wait)==32,"MSM wait layout");
#endif
