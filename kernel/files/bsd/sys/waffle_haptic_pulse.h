/* HAP525_HV bounded diagnostic transaction. Not an iOS service.
 * Native OnePlus qcom-hv-haptics.c e39bf703: DIRECT_PLAY=1, autores
 * disabled for constant effects, stop then poll HPWR_DISABLED.
 * Adapter must provide exclusive CFG/PTN ownership across the entire call,
 * checked PMIC writes, and a monotonic clock. No HBST writes are exposed. */
#ifndef WAFFLE_HAPTIC_PULSE_H
#define WAFFLE_HAPTIC_PULSE_H
#include "waffle_haptic_readonly.h"
struct waffle_haptic_pulse_io {
 struct waffle_haptic_read_io read;
 bool (*write8)(void *,uint16_t,uint8_t,uint8_t);
 uint64_t (*now_us)(void *);
 void (*wait_us)(void *,uint32_t);
 bool exclusive_owned;
};
struct waffle_haptic_pulse_result {
 bool admitted,start_attempted,stopped,restored,emergency_disabled,passed;
 uint32_t writes;
 uint64_t active_us;
};
static inline bool waffle_haptic_pulse_write_allowed(uint16_t p,uint8_t r)
{
 return (p==0x7f0 && (r==0x46 || r==0x4c || r==0x63)) ||
        (p==0x7f1 && r==0x26);
}
static inline bool waffle_haptic_pulse_write(const struct waffle_haptic_pulse_io *io,
 struct waffle_haptic_pulse_result *r,uint16_t p,uint8_t a,uint8_t v)
{
 if(!waffle_haptic_pulse_write_allowed(p,a))return false;
 r->writes++;
 return io->write8(io->read.context,p,a,v);
}
/* Caller must establish fresh fault-free, autonomous hardware-follow power
 * before admission. Inherited firmware-driven/open-loop boost is refused.
 * This is a narrow test policy, not general PM8550B initialization. */
static inline bool waffle_haptic_pulse(const struct waffle_haptic_pulse_io *io,
 struct waffle_haptic_pulse_result *r)
{
 if(!r)return false;
 *r=(struct waffle_haptic_pulse_result){0};
 if(!io || !io->read.read8 || !io->write8 || !io->now_us || !io->wait_us ||
    !io->exclusive_owned)return false;
 struct waffle_haptic_snapshot before;
 if(!waffle_haptic_capture(&io->read,&before) ||
    before.boost_revision[0]!=2 || before.boost_revision[1]!=0 ||
    before.enable!=0x80 || before.play!=1 || (before.hpwr&3) ||
    before.fault || before.vmax>0x30 || !before.vmax ||
    (before.vset&3) || (before.boost_enable&0x80) ||
    !(before.boost_follow&0x80))return false;
 r->admitted=true;
 bool ok=true,autores_dirty=false,direct_dirty=false;
 uint64_t start=0;
 /* Dirty before each write: transport failure may mean the byte arrived. */
 autores_dirty=true;
 if(!waffle_haptic_pulse_write(io,r,0x7f0,0x63,before.autores&~0x80)) {ok=false;goto cleanup;}
 direct_dirty=true;
 if(!waffle_haptic_pulse_write(io,r,0x7f1,0x26,0x20)) {ok=false;goto cleanup;}
 start=io->now_us(io->read.context);
 r->start_attempted=true;
 if(!waffle_haptic_pulse_write(io,r,0x7f0,0x4c,0x81)) {ok=false;goto cleanup;}
 /* Fixed16ms and at most16 waits: even a stalled clock cannot extend the loop. */
 for(unsigned i=0;i<16;i++) {
  uint8_t fault;
  if(!waffle_haptic_read(&io->read,0x7f0,0x0c,&fault) || fault) {ok=false;break;}
  if(io->now_us(io->read.context)-start>=16000)break;
  io->wait_us(io->read.context,1000);
 }
cleanup:
 /* Once PLAY_EN may have reached hardware, always send STOP, including an
  * ambiguous failed START. No restoration of amplitude while motor may run. */
 if(r->start_attempted) {
  r->active_us=io->now_us(io->read.context)-start;
  ok=ok && r->active_us>=16000 && r->active_us<=30000;
  bool stop_written=waffle_haptic_pulse_write(io,r,0x7f0,0x4c,0x01);
  uint64_t stop=io->now_us(io->read.context);
  if(stop_written)for(unsigned i=0;i<21;i++) {
   uint8_t hpwr,play;
   if(!waffle_haptic_read(&io->read,0x7f0,0x0b,&hpwr) ||
      !waffle_haptic_read(&io->read,0x7f0,0x4c,&play))break;
   if(!(hpwr&3) && !(play&0x80)){r->stopped=true;break;}
   if(io->now_us(io->read.context)-stop>=20000)break;
   io->wait_us(io->read.context,1000);
  }
  if(!r->stopped) {
   /* Bounded emergency quiesce, no restart/restore on uncertain stop. */
   bool disabled=waffle_haptic_pulse_write(io,r,0x7f0,0x46,before.enable&~0x80);
   uint8_t enable;
   r->emergency_disabled=disabled && waffle_haptic_read(&io->read,0x7f0,0x46,&enable) && !(enable&0x80);
   return false;
  }
 } else r->stopped=true;
 bool restore=true;
 if(direct_dirty)restore=waffle_haptic_pulse_write(io,r,0x7f1,0x26,before.direct)&&restore;
 if(autores_dirty)restore=waffle_haptic_pulse_write(io,r,0x7f0,0x63,before.autores)&&restore;
 if(r->start_attempted)restore=waffle_haptic_pulse_write(io,r,0x7f0,0x4c,before.play)&&restore;
 uint8_t final_fault=0xff;
 bool fault_free=waffle_haptic_read(&io->read,0x7f0,0x0c,&final_fault) && !final_fault;
 r->restored=restore;r->passed=ok && r->stopped && restore && fault_free;
 return r->passed;
}
#endif
