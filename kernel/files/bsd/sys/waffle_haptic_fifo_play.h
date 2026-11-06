/* Private zero-wave FIFO engine qualification, called only while H16 owns a
 * loaded144-sample zero FIFO and SWR input is disabled. HAP525_HV native
 * F_24KHZ=10; use the owner's measured RC count, never a donor constant.
 * No data/flush/VMAX/HBST writes here. A successful run requires observed
 * intermediate consumption, STOP/HPWR disabled and full config restoration. */
#ifndef WAFFLE_HAPTIC_FIFO_PLAY_H
#define WAFFLE_HAPTIC_FIFO_PLAY_H
#include "waffle_haptic_pulse.h"
#include "waffle_haptic_fifo_status.h"
struct waffle_haptic_fifo_play_io {
 struct waffle_haptic_pulse_io pulse;
 uint16_t rc_count;
};
struct waffle_haptic_fifo_play_result {
 bool admitted,start_attempted,progress,drained,stopped,restored,emergency_disabled,passed;
 uint16_t initial_fill,last_fill;
 unsigned writes;
 uint64_t active_us;
 uint8_t swr,last_hpwr,last_play,last_ready;
 bool power_seen;
};
static inline bool waffle_haptic_fifo_play_read_allowed(uint16_t p,uint8_t a)
{
 return waffle_haptic_read_allowed(p,a) || waffle_haptic_fifo_status_read_allowed(p,a) ||
        (p==0x7f0 && (a==0x5e || a==0x5f));
}
static inline bool waffle_haptic_fifo_play_write_allowed(uint16_t p,uint8_t a)
{
 return p==0x7f0?(a==0x46 || a==0x4c || a==0x63 || a==0x72 ||
                  a==0x5e || a==0x5f || a==0x70 || a==0x71):p==0x7f1 && a==0x24;
}
static inline bool waffle_haptic_fifo_play_write(const struct waffle_haptic_fifo_play_io *io,
 struct waffle_haptic_fifo_play_result *r,uint16_t p,uint8_t a,uint8_t v)
{
 if(!waffle_haptic_fifo_play_write_allowed(p,a))return false;
 r->writes++;return io->pulse.write8(io->pulse.read.context,p,a,v);
}
static inline bool waffle_haptic_fifo_play(const struct waffle_haptic_fifo_play_io *io,
 struct waffle_haptic_fifo_play_result *r)
{
 if(!r)return false;
 *r=(struct waffle_haptic_fifo_play_result){0};
 if(!io || !io->pulse.read.read8 || !io->pulse.write8 || !io->pulse.now_us ||
    !io->pulse.wait_us || !io->pulse.exclusive_owned || !io->rc_count || io->rc_count>1023)return false;
 struct waffle_haptic_snapshot before;
 if(!waffle_haptic_capture(&io->pulse.read,&before) || before.boost_revision[0]!=2 ||
    before.boost_revision[1] || before.enable!=0x80 || before.play!=1 ||
    (before.hpwr&3) || before.fault || !before.vmax || before.vmax>0x30 ||
    (before.swr&0x40) || !(before.swr&0x20) || (before.vset&3) || (before.boost_enable&0x80) ||
    !(before.boost_follow&0x80))return false;
 void *ctx=io->pulse.read.context;bool (*read)(void *,uint16_t,uint8_t,uint8_t *)=io->pulse.read.read8;
 uint8_t rc_hi,rc_lo,selector,extension;
 if(!read(ctx,0x7f0,0x5e,&rc_hi) || !read(ctx,0x7f0,0x5f,&rc_lo) ||
    !read(ctx,0x7f0,0x70,&selector) || !read(ctx,0x7f0,0x71,&extension))return false;
 r->admitted=true;
 r->swr=before.swr;
 bool ok=true,rate_dirty=false,rc_dirty=false,cal_dirty=false,autores_dirty=false;
 uint64_t start=0;uint8_t hi=0,lo=0;
 /* Select FIFO count and keep this selection during execution. */
 if(!waffle_haptic_fifo_play_write(io,r,0x7f0,0x71,0x80) ||
    !waffle_haptic_fifo_play_write(io,r,0x7f0,0x70,5)){ok=false;goto cleanup;}
 if(!read(ctx,0x7f0,9,&hi) || !read(ctx,0x7f0,10,&lo)){ok=false;goto cleanup;}
 r->initial_fill=(uint16_t)(hi&15)*256+lo;r->last_fill=r->initial_fill;
 if(r->initial_fill!=144){ok=false;goto cleanup;}
 rate_dirty=true;
 if(!waffle_haptic_fifo_play_write(io,r,0x7f1,0x24,(before.fifo_rate&0xf0)|10)){ok=false;goto cleanup;}
 rc_dirty=true;
 if(!waffle_haptic_fifo_play_write(io,r,0x7f0,0x5e,(rc_hi&~3u)|(io->rc_count>>8)) ||
    !waffle_haptic_fifo_play_write(io,r,0x7f0,0x5f,io->rc_count&255)){ok=false;goto cleanup;}
 cal_dirty=true;
 if(!waffle_haptic_fifo_play_write(io,r,0x7f0,0x72,(before.cal&~0x0c)|8)){ok=false;goto cleanup;}
 autores_dirty=true;
 if(!waffle_haptic_fifo_play_write(io,r,0x7f0,0x63,before.autores&~0x80)){ok=false;goto cleanup;}
 start=io->pulse.now_us(ctx);r->start_attempted=true;
 if(!waffle_haptic_fifo_play_write(io,r,0x7f0,0x4c,0x80)){ok=false;goto cleanup;}
 for(unsigned n=0;n<31;n++){
  uint8_t fault,hpwr,play,ready;
  if(!read(ctx,0x7f0,0x0c,&fault) || fault || !read(ctx,0x7f0,9,&hi) ||
     !read(ctx,0x7f0,10,&lo) || !read(ctx,0x7f0,0x0b,&hpwr) ||
     !read(ctx,0x7f0,0x4c,&play) || !read(ctx,0x7f1,8,&ready)){ok=false;break;}
  r->last_hpwr=hpwr;r->last_play=play;r->last_ready=ready;
  if((hpwr&3)==3)r->power_seen=true;
  uint16_t fill=(uint16_t)(hi&15)*256+lo;
  if(fill>r->last_fill){ok=false;break;}
  if(fill && fill<144)r->progress=true;
  r->last_fill=fill;
  uint64_t elapsed=io->pulse.now_us(ctx)-start;
  if(!fill){r->drained=r->progress && elapsed>=4500 && elapsed<=30000;ok=r->drained;break;}
  if(elapsed>=30000){ok=false;break;}
  io->pulse.wait_us(ctx,1000);
 }
cleanup:
 if(r->start_attempted){
  r->active_us=io->pulse.now_us(ctx)-start;
  bool stop=waffle_haptic_fifo_play_write(io,r,0x7f0,0x4c,0);
  for(unsigned n=0;stop && n<21;n++){
   uint8_t hpwr,play;
   if(!read(ctx,0x7f0,0x0b,&hpwr) || !read(ctx,0x7f0,0x4c,&play))break;
   if(!(hpwr&3) && !(play&0x80)){r->stopped=true;break;}
   io->pulse.wait_us(ctx,1000);
  }
  if(!r->stopped){
   bool disabled=waffle_haptic_fifo_play_write(io,r,0x7f0,0x46,0);uint8_t enable;
   r->emergency_disabled=disabled&&read(ctx,0x7f0,0x46,&enable)&&!(enable&0x80);
   return false;
  }
 }else r->stopped=true;
 bool restored=true;
 if(autores_dirty)restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x63,before.autores)&&restored;
 if(cal_dirty)restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x72,before.cal)&&restored;
 if(rc_dirty){
  restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x5f,rc_lo)&&restored;
  restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x5e,rc_hi)&&restored;
 }
 if(rate_dirty)restored=waffle_haptic_fifo_play_write(io,r,0x7f1,0x24,before.fifo_rate)&&restored;
 restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x70,selector)&&restored;
 restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x71,extension)&&restored;
 if(r->start_attempted)restored=waffle_haptic_fifo_play_write(io,r,0x7f0,0x4c,before.play)&&restored;
 r->restored=restored;r->passed=ok&&r->drained&&r->stopped&&restored;return r->passed;
}
#endif
