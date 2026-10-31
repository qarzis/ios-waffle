/* Bounded reversible native Gen7.9.1 configuration with CP disabled.
 * No command submission, clock-gating handshake or protected CPU access. */
#ifndef WAFFLE_GEN7_CONFIG_H
#define WAFFLE_GEN7_CONFIG_H
#include <stdbool.h>
#include <stdint.h>
#include "waffle_gen7_tables.h"
struct waffle_gen7_io {
    void *context;
    uint32_t (*read)(void *,uint32_t);
    void (*write)(void *,uint32_t,uint32_t);
    void (*mismatch)(void *,uint32_t,uint32_t,uint32_t,bool);
    int (*exercise)(void *);
};
static inline bool waffle_gen7_index_allowed(uint32_t index)
{
    return index<0x10000u || (index>=0x1a000u && index<0x27c00u);
}
/* The snapshot must outlive command submission and all power-collapse waits.
 * Zero-initialize it once; a retained snapshot must never be reused. */
enum waffle_gen7_phase {
    WAFFLE_GEN7_EMPTY, WAFFLE_GEN7_CONFIGURING, WAFFLE_GEN7_READY,
    WAFFLE_GEN7_SUBMITTED, WAFFLE_GEN7_COLLAPSED,
    WAFFLE_GEN7_RELEASED, WAFFLE_GEN7_RETAINED
};
enum {
    WAFFLE_GEN7_SETUP_COUNT=sizeof(waffle_gen7_disabled_setup)/sizeof(waffle_gen7_disabled_setup[0]),
    WAFFLE_GEN7_IFPC_COUNT=sizeof(waffle_gen7_ifpc_restore)/sizeof(waffle_gen7_ifpc_restore[0]),
    WAFFLE_GEN7_PREEMPT_COUNT=sizeof(waffle_gen7_preemption_restore)/sizeof(waffle_gen7_preemption_restore[0]),
    WAFFLE_GEN7_RESTORE_WORDS=4+2*(WAFFLE_GEN7_IFPC_COUNT+WAFFLE_GEN7_PREEMPT_COUNT)
};
struct waffle_gen7_config_state {
    enum waffle_gen7_phase phase;
    unsigned written;
    bool native_trusted_window;
    uint32_t saved[WAFFLE_GEN7_SETUP_COUNT];
};
/* Ordered evidence from the caller's hardware waits, not just an ACK to RAW.
 * Only the full sequence permits restoration of always-on registers/reclaim. */
enum waffle_gen7_stop_evidence {
    WAFFLE_GEN7_STOP_SLUMBER=1u,
    WAFFLE_GEN7_STOP_CM3_RESET=2u,
    WAFFLE_GEN7_STOP_RSC_ASLEEP=4u,
    WAFFLE_GEN7_STOP_GX_OFF=8u,
    WAFFLE_GEN7_STOP_GBIF_DRAINED=16u,
    WAFFLE_GEN7_STOP_QTB_DRAINED=32u
};
static inline int waffle_gen7_config_begin(const struct waffle_gen7_io *io,
    struct waffle_gen7_config_state *state,uint32_t *restore_words,
    unsigned capacity,uint32_t *failed_index)
{
    if (!io || !io->read || !io->write || !state || state->phase!=WAFFLE_GEN7_EMPTY ||
        !restore_words || !failed_index || capacity<WAFFLE_GEN7_RESTORE_WORDS) return -1;
    *failed_index=0;
    for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i)
        if (!waffle_gen7_index_allowed(waffle_gen7_disabled_setup[i].index)) return -1;
    for (unsigned i=0;i<WAFFLE_GEN7_IFPC_COUNT+WAFFLE_GEN7_PREEMPT_COUNT;++i) {
        uint32_t index=i<WAFFLE_GEN7_IFPC_COUNT?waffle_gen7_ifpc_restore[i]:
            waffle_gen7_preemption_restore[i-WAFFLE_GEN7_IFPC_COUNT];
        if (!waffle_gen7_index_allowed(index)) return -1;
    }
    if (io->read(io->context,0x808) || io->read(io->context,0x806) ||
        io->read(io->context,0x807)) return -1;
    state->written=0;
    for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i)
        state->saved[i]=io->read(io->context,waffle_gen7_disabled_setup[i].index);
    state->phase=WAFFLE_GEN7_CONFIGURING;
    int result=0;
    for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i) {
        const struct waffle_gen7_write *r=&waffle_gen7_disabled_setup[i];
        uint32_t selected=r->value;
        if (state->native_trusted_window && r->index==0xf800) selected=0xf0000000u;
        if (state->native_trusted_window && r->index==0xf802) selected=0xfffff000u;
        uint32_t value=(state->saved[i]&~r->mask)|(selected&r->mask);
        io->write(io->context,r->index,value);
        state->written=i+1;
        uint32_t actual=io->read(io->context,r->index);
        if ((actual&r->readback_mask)!=(value&r->readback_mask)) {
            if (io->mismatch) io->mismatch(io->context,r->index,value,actual,false);
            *failed_index=r->index;result=-2;break;
        }
    }
    if (io->read(io->context,0x808)) {
        *failed_index=0x808;state->phase=WAFFLE_GEN7_RETAINED;return -3;
    }
    if (!result && io->exercise) {
        int exercise=io->exercise(io->context);
        if (exercise==-3) { state->phase=WAFFLE_GEN7_RETAINED;return -3; }
        if (exercise) result=-4;
    }
    /* Even a failing exercise may have enabled CP: never roll back live GX. */
    if (io->read(io->context,0x808)) {
        *failed_index=0x808;state->phase=WAFFLE_GEN7_RETAINED;return -3;
    }
    if (!result) {
        /* Native cpu_gpu_lock: three32-bit lock words and packed u8/u8/u16
         * counts. Static lists are offset/value pairs, no dynamic triplets. */
        restore_words[0]=restore_words[1]=restore_words[2]=0;
        restore_words[3]=WAFFLE_GEN7_IFPC_COUNT|(WAFFLE_GEN7_PREEMPT_COUNT<<8);
        for (unsigned i=0;i<WAFFLE_GEN7_IFPC_COUNT+WAFFLE_GEN7_PREEMPT_COUNT;++i) {
            uint32_t index=i<WAFFLE_GEN7_IFPC_COUNT?waffle_gen7_ifpc_restore[i]:
                waffle_gen7_preemption_restore[i-WAFFLE_GEN7_IFPC_COUNT];
            restore_words[4+2*i]=index;
            restore_words[5+2*i]=io->read(io->context,index);
        }
        if (io->read(io->context,0x808)) {
            *failed_index=0x808;state->phase=WAFFLE_GEN7_RETAINED;return -3;
        }
        state->phase=WAFFLE_GEN7_READY;
    }
    return result;
}
/* Call BEFORE publishing RAW131 to the command queue, even if its ACK later
 * times out. A timeout does not prove the firmware never consumed the command. */
static inline bool waffle_gen7_config_submitting(struct waffle_gen7_config_state *state)
{
    if (!state || state->phase!=WAFFLE_GEN7_READY) return false;
    state->phase=WAFFLE_GEN7_SUBMITTED;
    return true;
}
static inline bool waffle_gen7_config_stopped(struct waffle_gen7_config_state *state,
    unsigned evidence)
{
    const unsigned complete=WAFFLE_GEN7_STOP_SLUMBER|WAFFLE_GEN7_STOP_CM3_RESET|
        WAFFLE_GEN7_STOP_RSC_ASLEEP|WAFFLE_GEN7_STOP_GX_OFF|
        WAFFLE_GEN7_STOP_GBIF_DRAINED|WAFFLE_GEN7_STOP_QTB_DRAINED;
    if (!state || state->phase!=WAFFLE_GEN7_SUBMITTED || evidence!=complete) return false;
    state->phase=WAFFLE_GEN7_COLLAPSED;
    return true;
}
/* Before submission, restore all touched registers with CP disabled. After a
 * verified collapse, GX has lost state: ONLY restore GMU/AO registers. Never
 * touch GX MMIO to read CP, clocks or saved configuration after GXoff. */
static inline int waffle_gen7_config_finish(const struct waffle_gen7_io *io,
    struct waffle_gen7_config_state *state,uint32_t *failed_index)
{
    if (!io || !io->read || !io->write || !state || !failed_index) return -1;
    bool collapsed=state->phase==WAFFLE_GEN7_COLLAPSED;
    if (!collapsed && state->phase!=WAFFLE_GEN7_CONFIGURING && state->phase!=WAFFLE_GEN7_READY)
        return -3;
    if (!collapsed && io->read(io->context,0x808)) {
        *failed_index=0x808;state->phase=WAFFLE_GEN7_RETAINED;return -3;
    }
    int result=0;
    for (unsigned n=state->written;n>0;--n) {
        unsigned i=n-1;
        const struct waffle_gen7_write *r=&waffle_gen7_disabled_setup[i];
        if (collapsed && r->index<0x10000u) continue;
        uint32_t current=io->read(io->context,r->index);
        io->write(io->context,r->index,(current&~r->mask)|(state->saved[i]&r->mask));
        uint32_t actual=io->read(io->context,r->index);
        if ((actual&r->readback_mask)!=(state->saved[i]&r->readback_mask)) {
            if (io->mismatch) io->mismatch(io->context,r->index,state->saved[i],actual,true);
            *failed_index=r->index;result=-3;
        }
    }
    state->phase=result?WAFFLE_GEN7_RETAINED:WAFFLE_GEN7_RELEASED;
    return result;
}
/* Existing stages31/32 keep the reversible, CP-disabled probe interface. */
static inline int waffle_gen7_config_probe(const struct waffle_gen7_io *io,
    uint32_t *restore_words,unsigned capacity,uint32_t *failed_index)
{
    struct waffle_gen7_config_state state={0};
    int result=waffle_gen7_config_begin(io,&state,restore_words,capacity,failed_index);
    if (state.phase==WAFFLE_GEN7_EMPTY || state.phase==WAFFLE_GEN7_RETAINED) return result;
    int cleanup=waffle_gen7_config_finish(io,&state,failed_index);
    return cleanup?cleanup:result;
}
#endif
