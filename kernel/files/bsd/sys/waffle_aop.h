#ifndef _BSD_SYS_WAFFLE_AOP_H_
#define _BSD_SYS_WAFFLE_AOP_H_

#include <stdint.h>
#include <stdbool.h>

/* Stock PJD110 DT: power-controller@c300000, qcom,aoss-qmp, 0x400 bytes. */
#define WAFFLE_AOP_QMP_BASE 0x0c300000u
#define WAFFLE_AOP_QMP_SIZE 0x400u
#define WAFFLE_AOP_QMP_MAP_SIZE 0x4000u
#define WAFFLE_AOP_QMP_MAGIC 0x4d41494cu
#define WAFFLE_AOP_QMP_UP 0x0000ffffu
#define WAFFLE_AOP_QMP_DOWN 0xffff0000u
#define WAFFLE_AOP_QMP_MESSAGE 64u

struct waffle_aop_qmp_snapshot {
    uint32_t magic, version, our_box_size, our_box;
    uint32_t their_link, their_link_ack, their_channel, their_channel_ack;
    uint32_t our_link, our_link_ack, our_channel, our_channel_ack;
};

static inline bool
waffle_aop_qmp_geometry_valid(const struct waffle_aop_qmp_snapshot *s)
{
    if (!s || s->magic != WAFFLE_AOP_QMP_MAGIC || s->version != 1)
        return false;
    if (s->our_box < 0x3c || (s->our_box & 3) ||
        s->our_box_size < WAFFLE_AOP_QMP_MESSAGE + 4)
        return false;
    return s->our_box <= WAFFLE_AOP_QMP_SIZE &&
        s->our_box_size <= WAFFLE_AOP_QMP_SIZE - s->our_box;
}

static inline bool
waffle_aop_qmp_channel_open(const struct waffle_aop_qmp_snapshot *s)
{
    return waffle_aop_qmp_geometry_valid(s) &&
        s->our_link == WAFFLE_AOP_QMP_UP &&
        s->our_link_ack == WAFFLE_AOP_QMP_UP &&
        s->our_channel == WAFFLE_AOP_QMP_UP &&
        s->their_channel == WAFFLE_AOP_QMP_UP &&
        s->our_channel_ack == WAFFLE_AOP_QMP_UP;
}

/* Offline transport primitive. Caller must hold the shared AOP mailbox lock.
 * wait() must have a bounded deadline. No message RAM payload is touched.
 * This diagnostic borrows an established link; it never takes that link down.
 */
struct waffle_aop_qmp_io {
    void *context;
    uint32_t (*read)(void *, uint32_t);
    void (*write)(void *, uint32_t, uint32_t);
    void (*kick)(void *);
    bool (*wait)(void *, uint32_t, uint32_t);
};
enum waffle_aop_qmp_result {
    WAFFLE_AOP_QMP_OK, WAFFLE_AOP_QMP_REFUSED,
    WAFFLE_AOP_QMP_TIMEOUT, WAFFLE_AOP_QMP_RESTORE_FAILED
};

/* Native gen7_gmu_aop_send_acd_state includes NUL and pads to four bytes. */
static inline unsigned
waffle_aop_acd_packet(uint32_t *words, unsigned capacity, bool enabled)
{
    const char text[] = "{class: gpu, res: acd, val: 0}";
    unsigned bytes = (sizeof(text) + 3u) & ~3u;
    if (!words || capacity < bytes / 4) return 0;
    for (unsigned i = 0; i < bytes / 4; ++i) words[i] = 0;
    for (unsigned i = 0; i < sizeof(text); ++i) {
        unsigned char ch = (unsigned char)text[i];
        if (i == sizeof(text) - 3) ch = enabled ? '1' : '0';
        words[i / 4] |= (uint32_t)ch << ((i & 3) * 8);
    }
    return bytes;
}

/* Caller owns the open channel and shared lock. A cleared length is only
 * transport receipt; it does not prove ACD applied or GPU execution. */
static inline enum waffle_aop_qmp_result
waffle_aop_qmp_send_acd(const struct waffle_aop_qmp_io *io, bool enabled)
{
    if (!io || !io->read || !io->write || !io->kick || !io->wait)
        return WAFFLE_AOP_QMP_REFUSED;
    void *c = io->context;
    struct waffle_aop_qmp_snapshot s = {
        .magic=io->read(c,0), .version=io->read(c,4),
        .our_box=io->read(c,0x38), .our_box_size=io->read(c,0x34),
        .our_link=io->read(c,0x24), .our_link_ack=io->read(c,0x28),
        .our_channel=io->read(c,0x2c), .our_channel_ack=io->read(c,0x30),
        .their_channel=io->read(c,0x14),
    };
    if (!waffle_aop_qmp_channel_open(&s) || io->read(c,s.our_box))
        return WAFFLE_AOP_QMP_REFUSED;
    uint32_t words[16];
    unsigned bytes=waffle_aop_acd_packet(words,16,enabled);
    for (unsigned i=0; i<bytes/4; ++i)
        io->write(c,s.our_box+4+i*4,words[i]);
    io->write(c,s.our_box,bytes);
    io->kick(c);
    if (io->wait(c,s.our_box,0)) return WAFFLE_AOP_QMP_OK;
    io->write(c,s.our_box,0);
    return WAFFLE_AOP_QMP_TIMEOUT;
}

static inline enum waffle_aop_qmp_result
waffle_aop_qmp_transaction_run(const struct waffle_aop_qmp_io *io, bool acd,
    void (*task)(void *), void *task_context)
{
    if (!io || !io->read || !io->write || !io->kick || !io->wait)
        return WAFFLE_AOP_QMP_REFUSED;
    void *c = io->context;
    struct waffle_aop_qmp_snapshot s = {
        .magic = io->read(c, 0), .version = io->read(c, 4),
        .our_box_size = io->read(c, 0x34), .our_box = io->read(c, 0x38),
    };
    if (!waffle_aop_qmp_geometry_valid(&s)) return WAFFLE_AOP_QMP_REFUSED;
    /* Refuse busy, partially open or unknown states before the first write. */
    if (io->read(c, 0x0c) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x10) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x14) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x18) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x24) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x28) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x2c) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, 0x30) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, s.our_box) != 0) return WAFFLE_AOP_QMP_REFUSED;

    io->write(c, 0x2c, WAFFLE_AOP_QMP_UP);
    io->kick(c);
    bool opened = io->wait(c, 0x14, WAFFLE_AOP_QMP_UP);
    if (opened) {
        /* Remote channel was already acknowledged; publish that ACK again
         * before waiting for AOP to acknowledge our channel, as native does. */
        io->write(c, 0x18, WAFFLE_AOP_QMP_UP);
        io->kick(c);
        opened = io->wait(c, 0x30, WAFFLE_AOP_QMP_UP);
    }
    enum waffle_aop_qmp_result payload = WAFFLE_AOP_QMP_OK;
    bool off_failed = false;
    if (opened && acd) {
        payload = waffle_aop_qmp_send_acd(io, true);
        if (payload == WAFFLE_AOP_QMP_OK && task) task(task_context);
        /* Even an unacknowledged on may have been consumed. Always send off. */
        off_failed = waffle_aop_qmp_send_acd(io, false) != WAFFLE_AOP_QMP_OK;
    }
    io->write(c, 0x2c, WAFFLE_AOP_QMP_DOWN);
    io->kick(c);
    if (!io->wait(c, 0x30, WAFFLE_AOP_QMP_DOWN) ||
        io->read(c, 0x2c) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, 0x24) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x28) != WAFFLE_AOP_QMP_UP)
        return WAFFLE_AOP_QMP_RESTORE_FAILED;
    if (off_failed) return WAFFLE_AOP_QMP_RESTORE_FAILED;
    return opened ? payload : WAFFLE_AOP_QMP_TIMEOUT;
}

static inline enum waffle_aop_qmp_result
waffle_aop_qmp_transaction(const struct waffle_aop_qmp_io *io, bool acd)
{
    return waffle_aop_qmp_transaction_run(io,acd,0,0);
}
static inline enum waffle_aop_qmp_result
waffle_aop_qmp_channel_roundtrip(const struct waffle_aop_qmp_io *io)
{
    return waffle_aop_qmp_transaction(io, false);
}
#endif
