/* SPDX-License-Identifier: BSD-3-Clause */
#ifndef WAFFLE_SAHARA_RAMLOGS_H
#define WAFFLE_SAHARA_RAMLOGS_H
#include "waffle-ramlog-manifest.h"

struct waffle_sahara_log_io {
    void *context;
    int (*read)(void *, void *, unsigned);
    int (*write)(void *, const void *, unsigned);
    int (*save)(void *, unsigned, const void *, unsigned);
};
enum waffle_sahara_log_stage {
    WAFFLE_LOG_VALIDATE, WAFFLE_LOG_HELLO, WAFFLE_LOG_HELLO_REPLY,
    WAFFLE_LOG_DEBUG_HEADER, WAFFLE_LOG_TABLE_REQUEST, WAFFLE_LOG_TABLE_READ,
    WAFFLE_LOG_PAGE_REQUEST, WAFFLE_LOG_PAGE_READ, WAFFLE_LOG_PAGE_SAVE,
    WAFFLE_LOG_COMPLETE
};
static inline const char *waffle_sahara_log_stage_name(unsigned stage)
{
    const char *const names[] = {"validate", "hello", "hello_reply", "debug_header",
        "table_request", "table_read", "page_request", "page_read", "page_save", "complete"};
    return stage < sizeof(names)/sizeof(names[0]) ? names[stage] : "invalid";
}
/* stage retains the successful endpoint or the failed operation across RESET. */
struct waffle_sahara_log_result { unsigned pages, reset_sent, reset_ack, stage; };

static inline int waffle_sahara_log_read(const struct waffle_sahara_log_io *io,
    void *buffer, unsigned bytes)
{
    unsigned done = 0;
    for (unsigned calls = 0; done < bytes && calls < 256; ++calls) {
        int n = io->read(io->context, (unsigned char *)buffer + done, bytes - done);
        if (n < 0 || (unsigned)n > bytes - done) return 0;
        done += (unsigned)n;
    }
    return done == bytes;
}

/* Sahara only: HELLO_RESP(2), MEM_READ64(17), RESET(7). No image upload,
 * programmer, Firehose, flash, key region or device-supplied dump content.
 * Caller validates manifest before opening USB. Revalidate entries here too.
 */
static inline int waffle_sahara_logs(const struct waffle_sahara_log_io *io,
    const struct waffle_ramlog_entry entries[5], struct waffle_sahara_log_result *result)
{
    uint32_t packet[12] = {0}, request[12] = {0};
    unsigned char buffer[65536];
    unsigned seen = 0;
    if (!io || !io->read || !io->write || !io->save || !entries || !result) return 0;
    memset(result, 0, sizeof(*result));
    for (unsigned i = 0; i < 5; ++i) {
        if (entries[i].slot > 4 || (seen & (1u << entries[i].slot)) ||
            entries[i].address < 0x8c0000000ULL || entries[i].address > 0xbffffc000ULL ||
            (entries[i].address & 0x3fff)) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (entries[j].address == entries[i].address) return 0;
        seen |= 1u << entries[i].slot;
    }
    result->stage = WAFFLE_LOG_HELLO;
    if (!waffle_sahara_log_read(io, packet, 48) || packet[0] != 1 ||
        packet[1] != 48 || packet[2] < 2 || packet[3] > 2 || packet[5] != 2) goto reset;
    request[0] = 2; request[1] = 48; request[2] = 2; request[3] = 1; request[5] = 2;
    result->stage = WAFFLE_LOG_HELLO_REPLY;
    if (io->write(io->context, request, 48) != 48) goto reset;
    result->stage = WAFFLE_LOG_DEBUG_HEADER;
    if (!waffle_sahara_log_read(io, packet, 24) || packet[0] != 16 || packet[1] != 24)
        goto reset;
    uint64_t table_address = (uint64_t)packet[2] | (uint64_t)packet[3] << 32;
    uint64_t table_bytes = (uint64_t)packet[4] | (uint64_t)packet[5] << 32;
    if (!table_bytes || table_bytes > sizeof(buffer) || table_address >= (1ULL << 36) ||
        table_bytes > (1ULL << 36) - table_address) goto reset;
    /* Consume the standard device-provided region table, not its regions. */
    request[0] = 17; request[1] = 24;
    memcpy(request + 2, packet + 2, 16);
    result->stage = WAFFLE_LOG_TABLE_REQUEST;
    if (io->write(io->context, request, 24) != 24) goto reset;
    result->stage = WAFFLE_LOG_TABLE_READ;
    if (!waffle_sahara_log_read(io, buffer, (unsigned)table_bytes)) goto reset;
    for (unsigned i = 0; i < 5; ++i) {
        request[2] = (uint32_t)entries[i].address;
        request[3] = (uint32_t)(entries[i].address >> 32);
        request[4] = 0x4000; request[5] = 0;
        result->stage = WAFFLE_LOG_PAGE_REQUEST;
        if (io->write(io->context, request, 24) != 24) goto reset;
        result->stage = WAFFLE_LOG_PAGE_READ;
        if (!waffle_sahara_log_read(io, buffer, 0x4000)) goto reset;
        result->stage = WAFFLE_LOG_PAGE_SAVE;
        if (!io->save(io->context, entries[i].slot, buffer, 0x4000)) goto reset;
        result->pages++;
    }
    result->stage = WAFFLE_LOG_COMPLETE;
reset:
    request[0] = 7; request[1] = 8;
    result->reset_sent = io->write(io->context, request, 8) == 8;
    if (result->reset_sent && waffle_sahara_log_read(io, packet, 8))
        result->reset_ack = packet[0] == 8 && packet[1] == 8;
    return result->pages == 5 && result->reset_sent;
}
#endif
