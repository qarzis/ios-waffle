#ifndef WAFFLE_GPU_BUFFER_H
#define WAFFLE_GPU_BUFFER_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_GPU_USER_TEST_VA 0x100000000ULL
struct waffle_gpu_buffer {
    uint64_t gpu_va;
    uintptr_t memory;
    uint32_t bytes;
    bool readonly;
};
/* Bounded first general-VA allocation: a single16KiB BO in lower39bitVA,
 * outside all32bitfirmware/global bootstrap ranges. Not an allocator heap ABI. */
static inline bool waffle_gpu_user_buffer_valid(uint64_t address,uint32_t bytes)
{
    return bytes==16384 && !(address&16383) && address>=WAFFLE_GPU_USER_TEST_VA &&
        address<=(1ULL<<39)-bytes;
}
#endif
