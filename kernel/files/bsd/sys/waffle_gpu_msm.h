#ifndef WAFFLE_GPU_MSM_H
#define WAFFLE_GPU_MSM_H
#include <stdint.h>
#include <sys/ioccom.h>
/* Exact legacy MSM UAPI layouts used by MacanGPU.cpp and Mesa drm-shim.
 * E31 supports two owned16KiB BOs and one audited191word compute IB only.
 * Upload/download is a diagnostic extension, not GEM mmap or a full DRM fd. */
/* Existing Darwin Mesa selector0x7e ABI, not Linux PRIME or a new iOS API.
 * This first stage describes native backing only; importing is unsupported. */
struct waffle_msm_surface {
 uint32_t surface,handle;
 uint64_t size;
 uint32_t offset,row_bytes,width,height,pixel_format,planes;
};
#define WAFFLE_MSM_SURFACE_DESCRIBE UINT32_MAX
#ifdef __cplusplus
extern "C" {
#endif
int waffle_gpu_surface_describe(struct waffle_msm_surface *);
#ifdef __cplusplus
}
#endif
struct waffle_msm_param { uint32_t pipe,param; uint64_t value; uint32_t len,pad; };
struct waffle_msm_cpu_prep { uint32_t handle,op; int64_t seconds,nanoseconds; };
struct waffle_msm_cpu_fini { uint32_t handle; };
struct waffle_msm_madvise { uint32_t handle,madv,retained; };
struct waffle_msm_queue { uint32_t flags,prio,id; };
struct waffle_msm_queue_query { uint64_t data; uint32_t id,param,len,pad; };
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
struct waffle_msm_map { uint64_t address; uint32_t handle,bytes,flags,pad; };
struct waffle_msm_report { uint32_t version,checks,wrong,fence,negative; };
#define WAFFLE_MSM_SURFACE _IOWR('d',0x7e,struct waffle_msm_surface)
/* Private isolated PID1 map/unmap audit, not a Mesa import request. */
#define WAFFLE_MSM_SURFACE_IMPORT_TEST _IOWR('W',0x58,struct waffle_msm_surface)
#define WAFFLE_MSM_SURFACE_READ_TEST _IOWR('W',0x57,struct waffle_msm_surface)
#define WAFFLE_MSM_SURFACE_WRITE_TEST _IOWR('W',0x56,struct waffle_msm_surface)
#define WAFFLE_MSM_SURFACE_MAP_TEST _IOWR('W',0x55,struct waffle_msm_surface)
#define WAFFLE_MSM_PARAM _IOWR('d',0x40,struct waffle_msm_param)
#define WAFFLE_MSM_CPU_PREP _IOW('d',0x44,struct waffle_msm_cpu_prep)
#define WAFFLE_MSM_CPU_FINI _IOW('d',0x45,struct waffle_msm_cpu_fini)
#define WAFFLE_MSM_MADVISE _IOWR('d',0x48,struct waffle_msm_madvise)
#define WAFFLE_MSM_QUEUE_NEW _IOWR('d',0x4a,struct waffle_msm_queue)
#define WAFFLE_MSM_QUEUE_CLOSE _IOW('d',0x4b,uint32_t)
#define WAFFLE_MSM_QUEUE_QUERY _IOW('d',0x4c,struct waffle_msm_queue_query)
#define WAFFLE_MSM_NEW _IOWR('d',0x42,struct waffle_msm_gem_new)
#define WAFFLE_MSM_INFO _IOWR('d',0x43,struct waffle_msm_gem_info)
#define WAFFLE_MSM_SUBMIT _IOWR('d',0x46,struct waffle_msm_submit)
#define WAFFLE_MSM_WAIT _IOW('d',0x47,struct waffle_msm_wait)
#define WAFFLE_MSM_CLOSE _IOW('d',0x09,struct waffle_msm_close)
#define WAFFLE_MSM_UPLOAD _IOW('W',0x50,struct waffle_msm_transfer)
#define WAFFLE_MSM_DOWNLOAD _IOW('W',0x51,struct waffle_msm_transfer)
#define WAFFLE_MSM_MAP _IOWR('W',0x53,struct waffle_msm_map)
#define WAFFLE_MSM_UNMAP _IOW('W',0x54,struct waffle_msm_map)
#define WAFFLE_MSM_REPORT _IOW('W',0x52,struct waffle_msm_report)
_Static_assert(sizeof(struct waffle_msm_surface)==40,"Darwin IOSurface ABI");
_Static_assert(sizeof(struct waffle_msm_submit)==72,"MSM submit layout");
_Static_assert(sizeof(struct waffle_msm_submit_cmd)==32,"MSM command layout");
_Static_assert(sizeof(struct waffle_msm_wait)==32,"MSM wait layout");
#endif
