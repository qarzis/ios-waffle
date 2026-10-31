/* SPDX-License-Identifier: BSD-3-Clause */
#ifndef WAFFLE_RAMLOG_MANIFEST_H
#define WAFFLE_RAMLOG_MANIFEST_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct waffle_ramlog_entry { uint64_t address; unsigned slot; };

/* Fixed diagnostic format: four GMU log pages and one HFI page, all 16KiB.
 * The live DT permits RAM throughout [0x8c0000000,0xc00000000). Require this
 * high XNU heap bank; do not accept MMIO, secure carveouts or arbitrary sizes.
 */
static inline int waffle_ramlog_hex(const char *s, uint64_t *value)
{
    uint64_t v = 0;
    unsigned n = 0;
    for (; *s; ++s, ++n) {
        unsigned d = *s >= '0' && *s <= '9' ? (unsigned)(*s - '0') :
            *s >= 'a' && *s <= 'f' ? (unsigned)(*s - 'a' + 10) : 16;
        if (n == 16 || d == 16) return 0;
        v = (v << 4) | d;
    }
    if (!n) return 0;
    *value = v;
    return 1;
}

static inline int waffle_ramlog_manifest(FILE *f, struct waffle_ramlog_entry out[5])
{
    char line[128], kind[16], index[16], pa[32], length[32], extra;
    struct waffle_ramlog_entry entries[5];
    unsigned count = 0, seen = 0;
    while (fgets(line, sizeof(line), f)) {
        uint64_t address, bytes;
        unsigned slot;
        if (!strchr(line, '\n') || count == 5 ||
            sscanf(line, "%15s %15s %31s %31s %c", kind, index, pa, length, &extra) != 4 ||
            strlen(index) != 1 || strlen(pa) != 16 ||
            !waffle_ramlog_hex(pa, &address) || !waffle_ramlog_hex(length, &bytes)) return 0;
        if (!strcmp(kind, "GMU_LOG") && index[0] >= '0' && index[0] <= '3')
            slot = (unsigned)(index[0] - '0');
        else if (!strcmp(kind, "HFI") && index[0] == '0') slot = 4;
        else return 0;
        if (bytes != 0x4000 || (address & 0x3fff) || address < 0x8c0000000ULL ||
            address > 0xc00000000ULL - bytes || (seen & (1u << slot))) return 0;
        for (unsigned i = 0; i < count; ++i)
            if (entries[i].address == address) return 0;
        entries[count++] = (struct waffle_ramlog_entry){address, slot};
        seen |= 1u << slot;
    }
    if (ferror(f) || seen != 31 || count != 5) return 0;
    memcpy(out, entries, sizeof(entries));
    return 1;
}
#endif
