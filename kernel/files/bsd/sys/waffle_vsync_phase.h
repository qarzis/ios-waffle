#ifndef WAFFLE_VSYNC_PHASE_H
#define WAFFLE_VSYNC_PHASE_H
#include <stdint.h>
#include <stdbool.h>
struct waffle_vsync_clock {void *context; bool (*read32)(void *,uint32_t,uint32_t *);};
/* V01/V02 qualify INTF1 panel-TE timestamp, CTRL=0x21, in CNTVCT units.
 * A high/low/high retry prevents mixing the high word across a rollover. */
static inline bool waffle_vsync_timestamp(const struct waffle_vsync_clock *io,uint64_t *stamp)
{
 if(!io || !io->read32 || !stamp)return false;
 for(unsigned i=0;i<3;i++){
  uint32_t h0,lo,h1;
  if(!io->read32(io->context,0x36218,&h0) || !io->read32(io->context,0x36214,&lo) || !io->read32(io->context,0x36218,&h1))return false;
  if(h0==h1){*stamp=((uint64_t)h1<<32)|lo;return true;}
 }
 return false;
}
static inline uint32_t waffle_vsync_divider(uint64_t frequency,uint64_t period,uint32_t requested_hz)
{
 if(!frequency || !period || !requested_hz || requested_hz>240 || period>UINT64_MAX/requested_hz)return 0;
 uint64_t product=period*requested_hz;
 uint64_t ratio=frequency/product,rem=frequency%product;
 if(rem>=product-rem)ratio++;
 if(!ratio || ratio>4 || product>UINT64_MAX/ratio)return 0;
 uint64_t expected=product*ratio;
 uint64_t error=expected>frequency?expected-frequency:frequency-expected;
 return error<=frequency/20?(uint32_t)ratio:0;
}
struct waffle_vsync_phase {uint64_t seen,sent,progress;uint32_t pending;bool initialized;};
enum waffle_vsync_result {WAFFLE_VSYNC_WAIT,WAFFLE_VSYNC_EDGE,WAFFLE_VSYNC_FAULT};
static inline enum waffle_vsync_result waffle_vsync_observe(struct waffle_vsync_phase *p,uint64_t stamp,uint64_t now,uint64_t period,uint32_t divider)
{
 if(!p || !period || period>UINT64_MAX/8 || !divider || divider>4 || !stamp || stamp>now || now-stamp>period*3)return WAFFLE_VSYNC_FAULT;
 if(!p->initialized){p->seen=p->sent=stamp;p->progress=now;p->pending=0;p->initialized=true;return WAFFLE_VSYNC_WAIT;}
 if(now<p->progress || stamp<p->seen)return WAFFLE_VSYNC_FAULT;
 if(stamp==p->seen)return now-p->progress>period*3?WAFFLE_VSYNC_FAULT:WAFFLE_VSYNC_WAIT;
 uint64_t delta=stamp-p->seen,steps=delta/period,rem=delta%period;
 if(rem>=period-rem)steps++;
 if(!steps || steps>8)return WAFFLE_VSYNC_FAULT;
 uint64_t expected=steps*period,error=expected>delta?expected-delta:delta-expected;
 if(error>period/8)return WAFFLE_VSYNC_FAULT;
 p->seen=stamp;p->progress=now;p->pending+=(uint32_t)steps;
 if(p->pending<divider)return WAFFLE_VSYNC_WAIT;
 p->pending%=divider;p->sent=stamp;return WAFFLE_VSYNC_EDGE;
}
#endif
