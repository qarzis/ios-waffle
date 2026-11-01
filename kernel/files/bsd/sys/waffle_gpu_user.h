#ifndef WAFFLE_GPU_USER_H
#define WAFFLE_GPU_USER_H
#include <stdint.h>
#include <sys/ioccom.h>
/* New diagnostic ABI: fixed inline pixels, no embedded user/GPU addresses. */
#define WAFFLE_GPU_USER_VERSION 1u
struct waffle_gpu_user_copy {
    uint32_t version,words,fence,reserved;
    uint32_t input[256],output[256];
};
struct waffle_gpu_user_report {
    uint32_t version,checks,wrong,last_fence,negative_checks;
};
#define WAFFLE_GPU_USER_COPY _IOWR('W',0x40,struct waffle_gpu_user_copy)
#define WAFFLE_GPU_USER_REPORT _IOW('W',0x41,struct waffle_gpu_user_report)
_Static_assert(sizeof(struct waffle_gpu_user_copy)==2064,"copy ABI size");
_Static_assert(sizeof(struct waffle_gpu_user_report)==20,"report ABI size");
#endif
