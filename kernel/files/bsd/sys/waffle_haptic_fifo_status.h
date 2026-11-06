/* Native HAP525_HV FIFO status selector transaction. Never starts, flushes,
 * fills or drains the motor FIFO. Caller serializes exclusive CFG/PTN access.
 * qcom-hv-haptics.c e39bf703: status selector 0x8005, 12-bit fill count. */
#ifndef WAFFLE_HAPTIC_FIFO_STATUS_H
#define WAFFLE_HAPTIC_FIFO_STATUS_H
#include <stdbool.h>
#include <stdint.h>
struct waffle_haptic_fifo_status_io {
 void *context;
 bool (*read8)(void *,uint16_t,uint8_t,uint8_t *);
 bool (*write8)(void *,uint16_t,uint8_t,uint8_t);
 bool exclusive_owned;
};
struct waffle_haptic_fifo_status_result {
 bool admitted,selection_attempted,sampled,restored,empty,full,passed;
 uint16_t fill,capacity;
 uint8_t selector,extension;
 uint8_t status_high,status_low;
 unsigned writes;
};
static inline bool waffle_haptic_fifo_status_read_allowed(uint16_t p,uint8_t a)
{
 return p==0x7f0?(a==1 || a==9 || a==10 || a==0x0b || a==0x0c ||
                  a==0x46 || a==0x4c || a==0x70 || a==0x71):
        p==0x7f1 && (a==1 || a==8 || a==0xa0);
}
static inline bool waffle_haptic_fifo_status_write_allowed(uint16_t p,uint8_t a)
{
 return p==0x7f0 && (a==0x70 || a==0x71);
}
static inline bool waffle_haptic_fifo_status_read(
 const struct waffle_haptic_fifo_status_io *io,uint16_t p,uint8_t a,uint8_t *v)
{
 return waffle_haptic_fifo_status_read_allowed(p,a) && io->read8(io->context,p,a,v);
}
static inline bool waffle_haptic_fifo_status_write(
 const struct waffle_haptic_fifo_status_io *io,
 struct waffle_haptic_fifo_status_result *r,uint8_t a,uint8_t v)
{
 if(!waffle_haptic_fifo_status_write_allowed(0x7f0,a))return false;
 r->writes++;
 return io->write8(io->context,0x7f0,a,v);
}
static inline bool waffle_haptic_fifo_status(
 const struct waffle_haptic_fifo_status_io *io,
 struct waffle_haptic_fifo_status_result *r)
{
 if(!r)return false;
 *r=(struct waffle_haptic_fifo_status_result){0};
 if(!io || !io->read8 || !io->write8 || !io->exclusive_owned)return false;
 uint8_t cfg,ptn,enable,play,hpwr,fault,ready,map,hi=0,lo=0;
 if(!waffle_haptic_fifo_status_read(io,0x7f0,1,&cfg) || cfg!=4 ||
    !waffle_haptic_fifo_status_read(io,0x7f1,1,&ptn) || ptn!=4 ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x46,&enable) || enable!=0x80 ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x4c,&play) || play!=1 ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x0b,&hpwr) || (hpwr&3) ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x0c,&fault) || fault ||
    !waffle_haptic_fifo_status_read(io,0x7f1,8,&ready) || !(ready&1) ||
    !waffle_haptic_fifo_status_read(io,0x7f1,0xa0,&map) || !(map&0x80) ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x70,&r->selector) ||
    !waffle_haptic_fifo_status_read(io,0x7f0,0x71,&r->extension))return false;
 r->capacity=(uint16_t)(map&15)*128;
 if(r->capacity<640)return false;
 r->admitted=true;
 /* Mark dirty BEFORE transport: a failed return may still have written. */
 r->selection_attempted=true;
 bool ok=waffle_haptic_fifo_status_write(io,r,0x71,0x80);
 if(ok)ok=waffle_haptic_fifo_status_write(io,r,0x70,5);
 if(ok)ok=waffle_haptic_fifo_status_read(io,0x7f0,9,&hi) &&
          waffle_haptic_fifo_status_read(io,0x7f0,10,&lo);
 if(ok){
  r->status_high=hi;r->status_low=lo;
  r->sampled=true;r->fill=(uint16_t)(hi&15)*256+lo;
  r->empty=!!(hi&0x40);r->full=!!(hi&0x20);
  /* Native haptics_get_available_fifo_memory validates the fill count only.
   * H14 observed fill0 with both flags0 while idle: flags are diagnostic,
   * not a required equality with the count. Preserve their raw values. */
  ok=r->fill<=r->capacity;
 }
 /* Always try both restores; never short-circuit on the first failure. */
 bool low=waffle_haptic_fifo_status_write(io,r,0x70,r->selector);
 bool high=waffle_haptic_fifo_status_write(io,r,0x71,r->extension);
 uint8_t restored_low=0,restored_high=0;
 bool check_low=waffle_haptic_fifo_status_read(io,0x7f0,0x70,&restored_low);
 bool check_high=waffle_haptic_fifo_status_read(io,0x7f0,0x71,&restored_high);
 r->restored=low && high && check_low && check_high &&
             restored_low==r->selector && restored_high==r->extension;
 r->passed=ok && r->restored;return r->passed;
}
#endif
