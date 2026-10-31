/* Native kgsl_iommu.c split-table address windows (39-bit TTBR0/TTBR1). */
#ifndef WAFFLE_GPU_VA_H
#define WAFFLE_GPU_VA_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_GPU_GLOBAL_BASE 0x0001ff8000000000ULL
#define WAFFLE_GPU_LOWER_LIMIT (1ULL<<39)
#define WAFFLE_GPU_GLOBAL_LIMIT (1ULL<<49)
#define WAFFLE_GPU_NATIVE_GLOBAL_BYTES (20u*1024u*1024u)
#define WAFFLE_GPU_COMPACT_POOL_BYTES (15u*1024u*1024u)
static inline bool waffle_gpu_va_valid(uint64_t address)
{
    return address<WAFFLE_GPU_LOWER_LIMIT ||
        (address>=WAFFLE_GPU_GLOBAL_BASE && address<WAFFLE_GPU_GLOBAL_LIMIT);
}
static inline uint64_t waffle_gpu_global_alias(uint64_t address)
{
    return address<WAFFLE_GPU_LOWER_LIMIT ? WAFFLE_GPU_GLOBAL_BASE|address : 0;
}
/* Compact probe layout; probes1..53 retain global_alias above.
 * Keep all GPU globals inside native KGSL's 20MiB allocation window.
 * The 15MiB pool starts at offset5MiB, disjoint from ucode/ring/test pages.
 */
static inline uint64_t waffle_gpu_compact_alias(uint64_t address)
{
    uint64_t offset;
    if (address>=0x80000000ULL && address<0x80080000ULL)
        offset=0x400000ULL+address-0x80000000ULL;
    else if (address>=0x61000000ULL && address<0x61f00000ULL)
        offset=0x500000ULL+address-0x61000000ULL;
    else return 0;
    return WAFFLE_GPU_GLOBAL_BASE+offset;
}
#endif
