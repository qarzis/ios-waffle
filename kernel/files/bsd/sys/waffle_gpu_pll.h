/* PJD110 PLL1 diagnostic implementation; isolated92 and GMU-clock93/94 callers.
 * Caller must own verified CX>=128/MX>=192 votes throughout this session.
 * All callbacks access GPUCC PLL1 only. wait() has a microsecond deadline.
 * begin/restore require every PLL1 consumer to be detached. On any failure
 * keep power votes held until restore succeeds or the platform is reset.
 */
#ifndef WAFFLE_GPU_PLL_H
#define WAFFLE_GPU_PLL_H
#include <stdbool.h>
#include <stdint.h>

struct waffle_pll1_io {
    void *context;
    uint32_t (*read)(void *,unsigned);
    bool (*write)(void *,unsigned,uint32_t);
    bool (*wait)(void *,unsigned,uint32_t,uint32_t,unsigned);
    void (*barrier)(void *);
    void (*delay_us)(void *,unsigned);
    bool (*power_held)(void *,unsigned,unsigned);
    bool (*unused)(void *);
};
struct waffle_pll1_state {
    uint32_t saved[13];
    bool owned;
};
static const unsigned waffle_pll1_offsets[13]={
    0x1000,0x1004,0x1010,0x1014,0x1018,0x101c,0x1020,
    0x1024,0x1028,0x102c,0x1030,0x1034,0x1038
};
static inline bool waffle_pll1_valid(const struct waffle_pll1_io *io)
{
    return io && io->read && io->write && io->wait && io->barrier &&
        io->delay_us && io->power_held && io->unused;
}
static inline bool waffle_pll1_write(const struct waffle_pll1_io *io,
    unsigned offset,uint32_t value,uint32_t mask)
{
    return io->power_held(io->context,128,192) &&
        io->write(io->context,offset,value) &&
        (io->read(io->context,offset)&mask)==(value&mask);
}
static inline bool waffle_pll1_update(const struct waffle_pll1_io *io,
    unsigned offset,uint32_t mask,uint32_t value)
{
    uint32_t old=io->read(io->context,offset);
    uint32_t next=(old&~mask)|(value&mask);
    return old==next || waffle_pll1_write(io,offset,next,mask);
}
static inline bool waffle_pll1_enable(const struct waffle_pll1_io *io)
{
    if (!waffle_pll1_update(io,0x1000,4,4) ||
        !waffle_pll1_write(io,0x1004,1,~0u) ||
        !io->wait(io->context,0x1000,1u<<31,1u<<31,200) ||
        !waffle_pll1_update(io,0x1000,1,1)) return false;
    io->barrier(io->context);
    return true;
}
static inline bool waffle_pll1_standby(const struct waffle_pll1_io *io)
{
    return waffle_pll1_update(io,0x1000,1,0) &&
        waffle_pll1_write(io,0x1004,0,~0u);
}
/* Same 16-bit fractional arithmetic as pinned alpha_pll_round_rate: floor
 * the fraction; Linux reports its result rounded to kHz. Only native rates.
 */
static inline bool waffle_pll1_rate(const struct waffle_pll1_io *io,
    const struct waffle_pll1_state *state,unsigned long rate)
{
    if (!waffle_pll1_valid(io) || !state || !state->owned ||
        !io->power_held(io->context,128,192) ||
        (rate!=1250000000ul && rate!=520000000ul)) return false;
    uint32_t l=(uint32_t)(rate/19200000ul);
    uint32_t alpha=(uint32_t)(((uint64_t)(rate%19200000ul)<<16)/19200000ul);
    if (!waffle_pll1_update(io,0x1010,0xffff,l) ||
        !waffle_pll1_write(io,0x1014,alpha,~0u)) return false;
    if (io->read(io->context,0x1000)&4) {
        if (!waffle_pll1_update(io,0x1000,1u<<14,1u<<14)) return false;
        io->delay_us(io->context,1);
        if (!(io->read(io->context,0x1000)&(1u<<13)) ||
            !waffle_pll1_update(io,0x1000,1u<<14,0)) return false;
    }
    if ((io->read(io->context,0x1004)&1) &&
        (io->read(io->context,0x1000)&1))
        return io->wait(io->context,0x1000,1u<<31,1u<<31,200);
    return true;
}
static inline bool waffle_pll1_begin(const struct waffle_pll1_io *io,
    struct waffle_pll1_state *state)
{
    if (!waffle_pll1_valid(io) || !state || state->owned ||
        !io->power_held(io->context,128,192) || !io->unused(io->context)) return false;
    /* Refuse an active/FSM PLL or an existing rate owned by firmware. */
    if ((io->read(io->context,0x1000)&(1u|(1u<<14))) ||
        io->read(io->context,0x1004)!=0 ||
        (io->read(io->context,0x1018)&(1u<<25)) ||
        (io->read(io->context,0x1010)&0xffff)) return false;
    for (unsigned i=0;i<13;i++) state->saved[i]=io->read(io->context,waffle_pll1_offsets[i]);
    state->owned=true;
    /* Native gpu_cc_pll1_config + clk_lucid_evo_pll_configure. */
    if (!waffle_pll1_update(io,0x1018,7,7) ||
        !waffle_pll1_update(io,0x1010,0xffff,0x1b) ||
        !waffle_pll1_update(io,0x1010,0xff0000,0x440000) ||
        !waffle_pll1_update(io,0x1010,0xff000000,0x44000000) ||
        !waffle_pll1_write(io,0x1014,0x1555,~0u)) return false;
    const uint32_t config[][2]={
        {0x1020,0x20485699},{0x1024,0x00182261},{0x1028,0x82aa299c},
        {0x101c,5},{0x1030,3},{0x1034,0x9000},{0x1038,0x34}
    };
    for (unsigned i=0;i<sizeof(config)/sizeof(config[0]);i++)
        if (!waffle_pll1_write(io,config[i][0],config[i][1],~0u)) return false;
    if (!waffle_pll1_standby(io)) return false;
    io->barrier(io->context);
    if (!waffle_pll1_update(io,0x1000,4,4) ||
        !waffle_pll1_rate(io,state,1250000000ul)) return false;
    /* Native prepare self-calibrates before enable if PCAL_NOT_DONE. */
    if (io->read(io->context,0x1000)&(1u<<8)) {
        if (!waffle_pll1_enable(io) || !waffle_pll1_standby(io)) return false;
    }
    return waffle_pll1_enable(io);
}
static inline bool waffle_pll1_restore(const struct waffle_pll1_io *io,
    struct waffle_pll1_state *state)
{
    if (!waffle_pll1_valid(io) || !state) return false;
    if (!state->owned) return true;
    if (!io->power_held(io->context,128,192) || !io->unused(io->context) ||
        !waffle_pll1_standby(io) || !waffle_pll1_update(io,0x1000,4|(1u<<14),0)) return false;
    /* Restore scalar configuration only after the output is off, in RESET.
     * MODE status bits (lock/calibration/ACK) are hardware-owned, not saved.
     */
    for (unsigned i=13;i>2;i--)
        if (!waffle_pll1_write(io,waffle_pll1_offsets[i-1],state->saved[i-1],~0u)) return false;
    if (!waffle_pll1_update(io,0x1000,1|4|(1u<<14),state->saved[0])) return false;
    state->owned=false;
    return true;
}
#endif
