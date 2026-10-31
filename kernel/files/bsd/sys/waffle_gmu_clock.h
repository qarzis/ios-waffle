/* Diagnostic GMU625->260 clock session. Firmware owns CX/MX NOMINAL votes.
 * Keep PLL ownership until CM3 is reset, GX is off and its root is detached.
 * Callers must retain power and stop the test if finish cannot prove this.
 */
#ifndef WAFFLE_GMU_CLOCK_H
#define WAFFLE_GMU_CLOCK_H
#include <sys/waffle_gpu_pll.h>
struct waffle_gmu_clock_io {
    const struct waffle_pll1_io *pll;
    void *context;
    uint32_t (*root)(void *);
    bool (*set_root)(void *,uint32_t);
    bool (*cm3_reset)(void *);
    bool (*gx_off)(void *);
};
struct waffle_gmu_clock_state {
    struct waffle_pll1_state pll;
    uint32_t saved_root;
    bool active,runtime;
};
static inline bool waffle_gmu_clock_valid(const struct waffle_gmu_clock_io *io)
{
    return io && waffle_pll1_valid(io->pll) && io->root && io->set_root &&
        io->cm3_reset && io->gx_off;
}
static inline bool waffle_gmu_clock_start(const struct waffle_gmu_clock_io *io,
    struct waffle_gmu_clock_state *state)
{
    if(!waffle_gmu_clock_valid(io) || !state || state->active || state->pll.owned ||
        !io->cm3_reset(io->context) || !io->gx_off(io->context) ||
        (io->root(io->context)&0x71f)!=0x505) return false;
    state->saved_root=0x505;state->runtime=false;
    if(!waffle_pll1_begin(io->pll,&state->pll))return false;
    /* SRC3=PLL1, divider2/HID3, preserve HW_CLK_CTRL and unrelated bits. */
    if(!io->set_root(io->context,0x303) || (io->root(io->context)&0x71f)!=0x303)return false;
    state->active=true;
    return true;
}
static inline bool waffle_gmu_clock_runtime(const struct waffle_gmu_clock_io *io,
    struct waffle_gmu_clock_state *state)
{
    if(!waffle_gmu_clock_valid(io) || !state || !state->active || state->runtime ||
        io->cm3_reset(io->context) || (io->root(io->context)&0x71f)!=0x303 ||
        !waffle_pll1_rate(io->pll,&state->pll,520000000ul)) return false;
    state->runtime=true;
    return true;
}
static inline bool waffle_gmu_clock_finish(const struct waffle_gmu_clock_io *io,
    struct waffle_gmu_clock_state *state)
{
    if(!waffle_gmu_clock_valid(io) || !state)return false;
    if(!state->pll.owned && !state->active)return true;
    if(!io->pll->power_held(io->pll->context,128,192) ||
        !io->cm3_reset(io->context) || !io->gx_off(io->context))return false;
    /* Even a failed attach may have written the selector before timing out. */
    if(!io->set_root(io->context,state->saved_root) ||
        (io->root(io->context)&0x71f)!=state->saved_root ||
        !waffle_pll1_restore(io->pll,&state->pll)) return false;
    state->active=false;
    return true;
}
#endif
