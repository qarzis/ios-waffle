#ifndef WAFFLE_MEMORY_H
#define WAFFLE_MEMORY_H
#include <stdint.h>
#include <stddef.h>
#include "waffle-memory-map.h"

static inline int waffle_range_allowed(uint64_t lo, uint64_t bytes)
{
    if (!bytes || lo >= (1ULL << 40) || bytes > (1ULL << 40) - lo) return 0;
    uint64_t hi = lo + bytes;
    int in_ram = 0;
    for (size_t i = 0; i < sizeof(waffle_ram) / sizeof(waffle_ram[0]); i++)
        if (lo >= waffle_ram[i].lo && hi <= waffle_ram[i].hi) in_ram = 1;
    if (!in_ram) return 0;
    for (size_t i = 0; i < sizeof(waffle_reserved) / sizeof(waffle_reserved[0]); i++)
        if (lo < waffle_reserved[i].hi && hi > waffle_reserved[i].lo) return 0;
    return 1;
}

/* Intersect one EFI conventional descriptor with actual Android RAM banks,
 * then subtract all stock/live reserved ranges, including reusable regions.
 */
static inline void waffle_largest_gap(uint64_t lo, uint64_t hi, uint64_t alignment,
    uint64_t *best_lo, uint64_t *best_size)
{
    if (!alignment || (alignment & (alignment - 1)) || alignment > (1ULL << 40)) return;
    for (size_t bank = 0; bank < sizeof(waffle_ram) / sizeof(waffle_ram[0]); bank++) {
        uint64_t begin = lo > waffle_ram[bank].lo ? lo : waffle_ram[bank].lo;
        uint64_t limit = hi < waffle_ram[bank].hi ? hi : waffle_ram[bank].hi;
        if (begin >= limit) continue;
        for (size_t i = 0; i <= sizeof(waffle_reserved) / sizeof(waffle_reserved[0]); i++) {
            uint64_t end = limit;
            if (i < sizeof(waffle_reserved) / sizeof(waffle_reserved[0])) {
                if (waffle_reserved[i].hi <= begin) continue;
                if (waffle_reserved[i].lo < end) end = waffle_reserved[i].lo;
            }
            uint64_t aligned = (begin + alignment - 1) & ~(alignment - 1);
            end &= ~(alignment - 1);
            if (end > aligned && end - aligned > *best_size) {
                *best_lo = aligned;
                *best_size = end - aligned;
            }
            if (i == sizeof(waffle_reserved) / sizeof(waffle_reserved[0]) || waffle_reserved[i].hi >= limit) break;
            if (waffle_reserved[i].hi > begin) begin = waffle_reserved[i].hi;
        }
    }
}
#endif
