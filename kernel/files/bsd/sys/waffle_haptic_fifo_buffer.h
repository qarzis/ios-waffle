/* Isolated HAP525_HV memory transport experiment. Zeros only, no PLAY,
 * calibration, rate, voltage, module-enable or HBST writes. The native
 * e39bf703 non-refill flush is PTN2d=1,0; DIN20 takes four bytes. */
#ifndef WAFFLE_HAPTIC_FIFO_BUFFER_H
#define WAFFLE_HAPTIC_FIFO_BUFFER_H
#include "waffle_haptic_fifo_status.h"
struct waffle_haptic_fifo_buffer_io {
 struct waffle_haptic_fifo_status_io status;
 bool (*write4)(void *,uint16_t,uint8_t,const uint8_t *);
};
struct waffle_haptic_fifo_buffer_result {
 bool admitted,loaded,cleared,selectors_restored,swr_restored,passed;
 uint8_t source,saved_swr;
 unsigned data_commands;
 uint16_t loaded_fill,final_fill;
};
static inline bool waffle_haptic_fifo_buffer_read_allowed(uint16_t p,uint8_t a)
{
 return waffle_haptic_fifo_status_read_allowed(p,a) ||
        (p==0x7f0 && a==0x4e) || (p==0x7f1 && a==0x2d);
}
static inline bool waffle_haptic_fifo_buffer_write_allowed(uint16_t p,uint8_t a)
{
 return waffle_haptic_fifo_status_write_allowed(p,a) ||
        (p==0x7f0 && a==0x4e) || (p==0x7f1 && a==0x2d);
}
static inline bool waffle_haptic_fifo_buffer(
 const struct waffle_haptic_fifo_buffer_io *io,
 struct waffle_haptic_fifo_buffer_result *r)
{
 if(!r)return false;
 *r=(struct waffle_haptic_fifo_buffer_result){0};
 if(!io || !io->write4 || !io->status.read8 || !io->status.write8 ||
    !io->status.exclusive_owned)return false;
 const struct waffle_haptic_fifo_status_io *s=&io->status;
 struct waffle_haptic_fifo_status_result before,after;
 if(!waffle_haptic_fifo_status(s,&before) || before.fill || before.capacity<144)return false;
 uint8_t mem=0,source=0;
 if(!s->read8(s->context,0x7f0,0x4e,&r->saved_swr) ||
    !s->read8(s->context,0x7f1,0x2d,&mem) || mem)return false;
 /* Native is_swr_play_enabled uses HAP_DRV_STS selector0x0005.
  * Read failure is NOT evidence that the autonomous producer is idle. */
 bool selected=s->write8(s->context,0x7f0,0x71,0);
 if(selected)selected=s->write8(s->context,0x7f0,0x70,5);
 if(selected)selected=s->read8(s->context,0x7f0,10,&source);
 bool low=s->write8(s->context,0x7f0,0x70,before.selector);
 bool high=s->write8(s->context,0x7f0,0x71,before.extension);
 r->selectors_restored=low&&high;
 r->source=source&7;
 if(!selected || !r->selectors_restored || r->source==4)return false;
 r->admitted=true;
 /* Native swr_slave_reg_disable masks all three input/config/reset bits.
  * Mark the attempt dirty even if transport reports failure. */
 bool ok=s->write8(s->context,0x7f0,0x4e,r->saved_swr&~0xe0);
 bool fifo_touched=false,known_clear=true;
 if(ok){
  fifo_touched=true;known_clear=false;
  ok=s->write8(s->context,0x7f1,0x2d,1);
  if(ok)ok=s->write8(s->context,0x7f1,0x2d,0);
 }
 static const uint8_t zero[4]={0};
 for(unsigned i=0;ok && i<36;i++){
  r->data_commands++;
  /* No retries/readback on data ports: a failed return may have enqueued. */
  ok=io->write4(s->context,0x7f1,0x20,zero);
 }
 if(ok){
  ok=waffle_haptic_fifo_status(s,&after);
  r->loaded_fill=after.fill;r->loaded=ok && after.fill==144;
  r->selectors_restored=r->selectors_restored&&after.restored;
  ok=ok&&r->loaded;
 }
 if(fifo_touched){
  /* Always attempt both flush edges after an ambiguous partial upload. */
  bool set=s->write8(s->context,0x7f1,0x2d,1);
  bool clear=s->write8(s->context,0x7f1,0x2d,0);
  bool sampled=waffle_haptic_fifo_status(s,&after);
  r->final_fill=after.fill;
  known_clear=set&&clear&&sampled&&after.fill==0;
  r->selectors_restored=r->selectors_restored&&after.restored;
 }
 r->cleared=known_clear;
 bool final_low=s->write8(s->context,0x7f0,0x70,before.selector);
 bool final_high=s->write8(s->context,0x7f0,0x71,before.extension);
 r->selectors_restored=final_low&&final_high;
 /* Never re-enable an inherited SWR producer onto an uncertain FIFO. */
 if(known_clear)r->swr_restored=s->write8(s->context,0x7f0,0x4e,r->saved_swr);
 r->passed=ok&&r->loaded&&r->cleared&&r->selectors_restored&&r->swr_restored;
 return r->passed;
}
#endif
