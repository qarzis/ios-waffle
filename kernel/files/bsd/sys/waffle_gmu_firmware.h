#ifndef WAFFLE_GMU_FIRMWARE_H
#define WAFFLE_GMU_FIRMWARE_H
#include <stddef.h>
#include <stdint.h>
struct waffle_fw_block {
    uint32_t address, size, type, value;
    const uint8_t *payload;
};
static inline uint32_t waffle_fw_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
/* 1=block, 0=end, -1=malformed. Never advance on malformed input. */
static inline int waffle_fw_next(const uint8_t *data, size_t length, size_t *cursor,
    struct waffle_fw_block *block)
{
    size_t at = *cursor;
    if (at > length) return -1;
    if (at == length) return 0;
    if (length - at < 16) return -1;
    const uint8_t *p = data + at;
    block->address = waffle_fw_u32(p); block->size = waffle_fw_u32(p + 4);
    block->type = waffle_fw_u32(p + 8); block->value = waffle_fw_u32(p + 12);
    if ((block->address & 3) || (block->size & 3) || block->size > length - at - 16 ||
        (uint64_t)block->address + block->size > (1ULL << 32)) return -1;
    block->payload = p + 16;
    *cursor = at + 16 + block->size;
    return 1;
}
/* Vendor Gen7 VMA ranges. Return 1=ITCM, 2=DTCM, 3=cache, 4=noncache.
 * Reject an entire block crossing a boundary, not just its first address.
 */
static inline unsigned waffle_fw_region(uint32_t address, uint32_t size)
{
    uint64_t end = (uint64_t)address + size;
    if (!size || end > (1ULL << 32)) return 0;
    if (address < 0x4000 && end <= 0x4000) return 1;
    if (address >= 0x10004000 && end <= 0x10008000) return 2;
    if (address >= 0x4000 && end <= 0x1000000) return 3;
    if ((address >= 0x60000000 && end <= 0x80000000) ||
        (address >= 0xc0000000 && end <= 0xe0000000)) return 4;
    return 0;
}
#endif
