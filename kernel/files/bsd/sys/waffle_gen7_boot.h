/* Bounded polled CP-init diagnostic, not a graphics driver submission queue.
 * No host GPU IRQ enable, ZAP load, unsecure switch, LPAC or drawing. */
#ifndef WAFFLE_GEN7_BOOT_H
#define WAFFLE_GEN7_BOOT_H
#include "waffle_gen7_cp.h"
#include "waffle_gen7_hwcg.h"
static const uint32_t waffle_gen7_ucode_indices[]={0x830,0x831,0xb70,0xb71};
struct waffle_gen7_boot_state {
    struct waffle_gen7_config_state config;
    struct waffle_gen7_hwcg_state clocks;
    struct waffle_gen7_cp_result cp;
    uint32_t ucode_saved[4],failed_index,clock_status;
    unsigned ucode_written;
    int detail;
};
/* Caller verifies firmware mapping permissions/sizes before entry, holds OOB
 * through return, and preserves this state through full native collapse.
 * IRQ mask must be zero: results are polled from HFI, no XNU GPU ISR exists. */
static inline int waffle_gen7_boot_prepare(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_boot_state *state,uint32_t *restore_words,unsigned capacity,
    uint64_t sqe_va,uint64_t aqe_va,uint64_t restore_va,unsigned sequence)
{
    uint32_t packet[11];
    if (!io || !io->registers || !io->registers->read || !io->registers->write ||
        !io->prepare || !io->exchange || !io->delay_us || !state ||
        state->config.phase!=WAFFLE_GEN7_EMPTY || state->clocks.phase!=WAFFLE_GEN7_HWCG_EMPTY ||
        !restore_words || capacity<WAFFLE_GEN7_RESTORE_WORDS ||
        !sqe_va || !aqe_va || ((sqe_va|aqe_va)&4095) || !waffle_gpu_va_valid(sqe_va) || !waffle_gpu_va_valid(aqe_va) ||
        waffle_hfi_cp_init_packet(packet,11,sequence,restore_va)!=11) return -1;
    const struct waffle_gen7_io *r=io->registers;
    if (r->read(r->context,0x38)) return -1;
    state->detail=waffle_gen7_config_begin(r,&state->config,restore_words,capacity,&state->failed_index);
    if (state->detail) return -2;
    state->detail=waffle_gen7_hwcg_begin(r,&state->clocks,io->delay_us,&state->clock_status,&state->failed_index);
    if (state->detail) return -3;
    if (r->read(r->context,0x808)) {
        state->config.phase=WAFFLE_GEN7_RETAINED;state->failed_index=0x808;return -4;
    }
    uint32_t values[]={(uint32_t)sqe_va,(uint32_t)(sqe_va>>32),(uint32_t)aqe_va,(uint32_t)(aqe_va>>32)};
    for (unsigned i=0;i<4;++i) state->ucode_saved[i]=r->read(r->context,waffle_gen7_ucode_indices[i]);
    for (unsigned i=0;i<4;++i) {
        uint32_t index=waffle_gen7_ucode_indices[i];
        r->write(r->context,index,values[i]);state->ucode_written=i+1;
        uint32_t actual=r->read(r->context,index);
        if (actual!=values[i]) {
            if (r->mismatch) r->mismatch(r->context,index,values[i],actual,false);
            state->failed_index=index;return -4;
        }
    }
    return 0;
}
static inline int waffle_gen7_boot_start(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_boot_state *state,uint32_t *restore_words,unsigned capacity,
    uint64_t sqe_va,uint64_t aqe_va,uint64_t restore_va,unsigned sequence)
{
    int result=waffle_gen7_boot_prepare(io,state,restore_words,capacity,sqe_va,aqe_va,restore_va,sequence);
    if (result) return result;
    state->detail=waffle_gen7_cp_submit(io,&state->config,sequence,restore_va,&state->cp);
    return state->detail?-5:0;
}
static inline int waffle_gen7_boot_thread_start(const struct waffle_gen7_cp_io *io,
    struct waffle_gen7_boot_state *state,uint32_t *restore_words,unsigned capacity,
    uint64_t sqe_va,uint64_t aqe_va,uint64_t restore_va,unsigned sequence)
{
    int result=waffle_gen7_boot_prepare(io,state,restore_words,capacity,sqe_va,aqe_va,restore_va,sequence);
    if (result) return result;
    state->detail=waffle_gen7_cp_thread_submit(io,&state->config,sequence,&state->cp);
    return state->detail?-5:0;
}
/* Before submission unwind the bases/HWCG/config with CP disabled. After
 * submission, caller must first record actual stop evidence using stopped().
 * Restore clock AO BEFORE config, and never read/write gated GX after collapse.
 * A nonzero return means retain all mappings/resources and reset Android. */
static inline int waffle_gen7_boot_finish(const struct waffle_gen7_io *io,
    struct waffle_gen7_boot_state *state)
{
    if (!io || !io->read || !io->write || !state) return -1;
    enum waffle_gen7_phase phase=state->config.phase;
    if (phase==WAFFLE_GEN7_EMPTY) return state->clocks.phase==WAFFLE_GEN7_HWCG_EMPTY?0:-3;
    if (phase!=WAFFLE_GEN7_CONFIGURING && phase!=WAFFLE_GEN7_READY && phase!=WAFFLE_GEN7_COLLAPSED) return -3;
    bool collapsed=phase==WAFFLE_GEN7_COLLAPSED;
    if (!collapsed && io->read(io->context,0x808)) {
        state->config.phase=WAFFLE_GEN7_RETAINED;state->failed_index=0x808;return -3;
    }
    if (!collapsed) {
        for (unsigned n=state->ucode_written;n>0;--n) {
            unsigned i=n-1;uint32_t index=waffle_gen7_ucode_indices[i];
            io->write(io->context,index,state->ucode_saved[i]);
            uint32_t actual=io->read(io->context,index);
            if (actual!=state->ucode_saved[i]) {
                if (io->mismatch) io->mismatch(io->context,index,state->ucode_saved[i],actual,true);
                state->failed_index=index;state->config.phase=WAFFLE_GEN7_RETAINED;return -3;
            }
        }
    }
    state->ucode_written=0;
    if (state->clocks.phase==WAFFLE_GEN7_HWCG_ACTIVE &&
        waffle_gen7_hwcg_finish(io,&state->clocks,&state->config,&state->failed_index)) {
        state->config.phase=WAFFLE_GEN7_RETAINED;return -3;
    }
    return waffle_gen7_config_finish(io,&state->config,&state->failed_index);
}
#endif
