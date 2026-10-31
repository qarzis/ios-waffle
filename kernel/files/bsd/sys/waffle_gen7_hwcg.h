/* Gen7.9.1 native HWCG on/off transaction. No CP or GPU command writes. */
#ifndef WAFFLE_GEN7_HWCG_H
#define WAFFLE_GEN7_HWCG_H
#include "waffle_gen7_config.h"
enum waffle_gen7_hwcg_phase {
    WAFFLE_GEN7_HWCG_EMPTY, WAFFLE_GEN7_HWCG_ACTIVE,
    WAFFLE_GEN7_HWCG_RELEASED, WAFFLE_GEN7_HWCG_RETAINED
};
enum { WAFFLE_GEN7_AO_COUNT=sizeof(waffle_gen7_ao_hwcg)/sizeof(waffle_gen7_ao_hwcg[0]) };
struct waffle_gen7_hwcg_state {
    enum waffle_gen7_hwcg_phase phase;
    uint32_t global,saved[WAFFLE_GEN7_AO_COUNT];
    unsigned written;
    bool loaded;
};
/* Leave native HWCG enabled for the CP boot; caller must finish or retain the
 * snapshot. No lifetime is inferred from a successful/failed command ACK. */
static inline int waffle_gen7_hwcg_begin(const struct waffle_gen7_io *io,
    struct waffle_gen7_hwcg_state *state,
    void (*delay_us)(void *,unsigned),uint32_t *tx_status,uint32_t *failed_index)
{
    if (!io || !io->read || !io->write || !delay_us || !tx_status || !failed_index || !state || state->phase!=WAFFLE_GEN7_HWCG_EMPTY) return -1;
    *tx_status=*failed_index=0;
    if (io->read(io->context,0x808)) return -1;
    uint32_t global=io->read(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL);
    /* Caller holds a fresh powered GX with CPdisabled. LOAD_CMD is a command,
     * not a readable state latch (target reads deafbead); native code only
     * writes it and uses P2S_STATUS/TXDONE to confirm the load operation. */
    if (global&~1u) return -1;
    state->global=global;
    state->written=0;state->loaded=false;
    for (unsigned i=0;i<WAFFLE_GEN7_AO_COUNT;++i)
        state->saved[i]=io->read(io->context,waffle_gen7_ao_hwcg[i].index);
    state->phase=WAFFLE_GEN7_HWCG_ACTIVE;
    int result=0;
    for (unsigned i=0;i<WAFFLE_GEN7_AO_COUNT;++i) {
        const struct waffle_gen7_write *r=&waffle_gen7_ao_hwcg[i];
        io->write(io->context,r->index,r->value);state->written=i+1;
        uint32_t actual=io->read(io->context,r->index);
        if (actual!=r->value) {
            *failed_index=r->index;result=-2;
            if (io->mismatch) io->mismatch(io->context,r->index,r->value,actual,false);
            break;
        }
    }
    if (!result) {
        io->write(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL,1);
        state->loaded=true;
        io->write(io->context,WAFFLE_GEN7_RBBM_CGC_GLOBAL_LOAD_CMD,1);
        io->write(io->context,WAFFLE_GEN7_RBBM_CGC_P2S_TRIG_CMD,1);
        for (unsigned i=0;i<3;++i) {
            delay_us(io->context,1);
            *tx_status=io->read(io->context,WAFFLE_GEN7_RBBM_CGC_P2S_STATUS);
            if (*tx_status&1u) break;
        }
        if (*tx_status&1u) io->write(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL,0);
        else { *failed_index=WAFFLE_GEN7_RBBM_CGC_P2S_STATUS;result=-2; }
    }
    return result;
}
/* Native off/rollback before submission, or AO-only restoration after full
 * collapse. Config must remain COLLAPSED until both snapshots are restored. */
static inline int waffle_gen7_hwcg_finish(const struct waffle_gen7_io *io,
    struct waffle_gen7_hwcg_state *state,const struct waffle_gen7_config_state *config,
    uint32_t *failed_index)
{
    if (!io || !io->read || !io->write || !state || !config || !failed_index) return -1;
    if (state->phase!=WAFFLE_GEN7_HWCG_ACTIVE) return -3;
    bool collapsed=config->phase==WAFFLE_GEN7_COLLAPSED;
    if (!collapsed && config->phase!=WAFFLE_GEN7_READY && config->phase!=WAFFLE_GEN7_CONFIGURING)
        return -3;
    if (!collapsed && io->read(io->context,0x808)) {
        *failed_index=0x808;state->phase=WAFFLE_GEN7_HWCG_RETAINED;return -3;
    }
    int result=0;
    if (state->loaded && !collapsed) {
        /* Exact native gen7_hwcg_set(false): AOzero, forced global clocks,
         * load0. Trigger/status are pulse/handshake registers, not RAM to undo. */
        for (unsigned i=0;i<WAFFLE_GEN7_AO_COUNT;++i)
            io->write(io->context,waffle_gen7_ao_hwcg[i].index,0);
        io->write(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL,1);
        io->write(io->context,WAFFLE_GEN7_RBBM_CGC_GLOBAL_LOAD_CMD,0);
    }
    for (unsigned n=state->written;n>0;--n) {
        unsigned i=n-1;
        uint32_t index=waffle_gen7_ao_hwcg[i].index;
        io->write(io->context,index,state->saved[i]);
        uint32_t actual=io->read(io->context,index);
        if (actual!=state->saved[i]) {
            *failed_index=index;result=-3;
            if (io->mismatch) io->mismatch(io->context,index,state->saved[i],actual,true);
        }
    }
    if (state->loaded && !collapsed) {
        io->write(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL,state->global);
        if (io->read(io->context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL)!=state->global) {
            *failed_index=WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL;result=-3;
        }
    }
    state->phase=result?WAFFLE_GEN7_HWCG_RETAINED:WAFFLE_GEN7_HWCG_RELEASED;
    return result;
}
/* Preserve the hardware-tested stage32 on/off transaction. */
static inline int waffle_gen7_hwcg_probe(const struct waffle_gen7_io *io,
    void (*delay_us)(void *,unsigned),uint32_t *tx_status,uint32_t *failed_index)
{
    struct waffle_gen7_hwcg_state state={0};
    const struct waffle_gen7_config_state config={.phase=WAFFLE_GEN7_READY};
    int result=waffle_gen7_hwcg_begin(io,&state,delay_us,tx_status,failed_index);
    if (state.phase==WAFFLE_GEN7_HWCG_EMPTY) return result;
    int cleanup=waffle_gen7_hwcg_finish(io,&state,&config,failed_index);
    return cleanup?cleanup:result;
}
#endif
