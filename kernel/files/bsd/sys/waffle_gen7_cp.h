/* Cold HWSCHED CP initialization only. No ZAP/PAS, nonsecure switch or drawing.
 * Caller owns OOB/GX, native HWCG, SQE/AQE bases, IRQ and mapped restore list.
 * Experimental hardware probes33/35 retain resources through full collapse. */
#ifndef WAFFLE_GEN7_CP_H
#define WAFFLE_GEN7_CP_H
#include "waffle_gen7_config.h"
#include "waffle_hfi.h"
struct waffle_gen7_cp_io {
    const struct waffle_gen7_io *registers;
    /* Clean the normal-memory restore buffer and issue the publication barrier.
     * A failure here occurs before RAW is published; no CP command was sent. */
    bool (*prepare)(void *);
    /* Must match the whole request header, wait for ACK and use native RAW ACK
     * semantics (zero_ack=false accepts every value except ffffffff). */
    bool (*exchange)(void *,const uint32_t *,unsigned,bool);
    void (*delay_us)(void *,unsigned);
};
struct waffle_gen7_cp_result {
    uint32_t header,last_busy;
    unsigned polls;
    bool acknowledged;
};
/* 0: RAW ACK and CP idle, NOT proof of a rendered frame or safe reclamation.
 * -1: preflight/prepare rejected, -2: ACK missing/rejected, -3: busy timeout,
 * -4: CP unexpectedly live before submission (retain resources).
 * Once exchange can observe the packet, state remains SUBMITTED on ALL outcomes;
 * only verified full collapse allows config_finish to release the snapshot. */
enum waffle_gen7_cp_kind { WAFFLE_GEN7_CP_INIT, WAFFLE_GEN7_CP_THREAD_ONLY };
static inline int waffle_gen7_cp_submit_kind(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_config_state *state,unsigned sequence,uint64_t restore_va,
    struct waffle_gen7_cp_result *result,enum waffle_gen7_cp_kind kind)
{
    uint32_t packet[11];
    unsigned words=kind==WAFFLE_GEN7_CP_INIT ? waffle_hfi_cp_init_packet(packet,11,sequence,restore_va) :
        kind==WAFFLE_GEN7_CP_THREAD_ONLY ? waffle_hfi_cp_thread_packet(packet,11,sequence) : 0;
    if (!io || !io->registers || !io->registers->read || !io->prepare ||
        !io->exchange || !io->delay_us || !state || state->phase!=WAFFLE_GEN7_READY ||
        !result || !words) return -1;
    *result=(struct waffle_gen7_cp_result){0};
    const struct waffle_gen7_io *r=io->registers;
    if (r->read(r->context,0x808)) {
        state->phase=WAFFLE_GEN7_RETAINED;
        return -4;
    }
    if (!io->prepare(r->context)) return -1;
    if (!waffle_gen7_config_submitting(state)) return -1;
    result->header=packet[0];
    result->acknowledged=io->exchange(r->context,packet,words,false);
    if (!result->acknowledged) return -2;
    /* Native submit_raw_cmds polls AO_GPU_CX_BUSY_STATUS BIT23 for200ms.
     * Bounded polling here uses up to2000 waits of100us; unrelated bits do not
     * mean CP is busy. ACK success alone is insufficient. */
    for (unsigned elapsed=0;;++elapsed) {
        result->last_busy=r->read(r->context,0x23b0c);
        ++result->polls;
        if (!(result->last_busy&(1u<<23))) return 0;
        if (elapsed==2000) return -3;
        io->delay_us(r->context,100);
    }
}
static inline int waffle_gen7_cp_submit(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_config_state *state,unsigned sequence,uint64_t restore_va,
    struct waffle_gen7_cp_result *result)
{
    return waffle_gen7_cp_submit_kind(io,state,sequence,restore_va,result,WAFFLE_GEN7_CP_INIT);
}
static inline int waffle_gen7_cp_thread_submit(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_config_state *state,unsigned sequence,struct waffle_gen7_cp_result *result)
{
    return waffle_gen7_cp_submit_kind(io,state,sequence,0,result,WAFFLE_GEN7_CP_THREAD_ONLY);
}
#endif
