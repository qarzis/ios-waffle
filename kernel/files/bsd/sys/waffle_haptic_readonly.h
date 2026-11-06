/* OnePlus 12 live DT: PM8550B SID7, CFG f000/PTN f100/HBST f200.
 * Pinned native qcom-hv-haptics.c e39bf703: HAP525 CFG/PTN revision4.
 * Read-only identity/configuration survey. No motor, reset, IRQ or RAM writes. */
#ifndef WAFFLE_HAPTIC_READONLY_H
#define WAFFLE_HAPTIC_READONLY_H
#include <stdint.h>
#include <stdbool.h>
struct waffle_haptic_read_io {void *context;bool (*read8)(void *,uint16_t,uint8_t,uint8_t *);};
struct waffle_haptic_snapshot {
 uint8_t cfg_revision,ptn_revision,boost_revision[2];
 uint8_t enable,play,swr,vmax,drive,tlra[2],direct,period[4];
 uint8_t hpwr,fault,brake,cl_brake,autores,cal;
 uint8_t vset,boost_follow,boost_enable,boost_clamp;
 uint8_t fifo_ready,fifo_rate,fifo_empty,fifo_depth,fifo_map;
 bool complete;
};
static inline bool waffle_haptic_read_allowed(uint16_t ppid,uint8_t reg)
{
 if(ppid==0x7f0)return reg==0x68 || reg==0x0b || reg==0x0c || reg==0x50 || reg==0x51 || reg==0x63 || reg==0x72 || reg==1 || reg==0x46 || reg==0x47 || reg==0x48 || reg==0x4c || reg==0x4e || reg==0x5c || reg==0x5d;
 if(ppid==0x7f1)return reg==0x08 || reg==0x24 || reg==0x2a || reg==0x2b || reg==0xa0 || reg==1 || reg==0x26 || (reg>=0x30 && reg<=0x33);
 return ppid==0x7f2 && (reg<=1 || reg==0x41 || reg==0x46 || reg==0x70);
}
static inline bool waffle_haptic_read(const struct waffle_haptic_read_io *io,uint16_t ppid,uint8_t reg,uint8_t *v)
{
 return io && io->read8 && v && waffle_haptic_read_allowed(ppid,reg) && io->read8(io->context,ppid,reg,v);
}
static inline bool waffle_haptic_capture(const struct waffle_haptic_read_io *io,struct waffle_haptic_snapshot *s)
{
 if(!s)return false;
 *s=(struct waffle_haptic_snapshot){0};
 if(!waffle_haptic_read(io,0x7f0,1,&s->cfg_revision) ||
    !waffle_haptic_read(io,0x7f1,1,&s->ptn_revision) ||
    !waffle_haptic_read(io,0x7f2,0,&s->boost_revision[0]) ||
    !waffle_haptic_read(io,0x7f2,1,&s->boost_revision[1]))return false;
 if(s->cfg_revision!=4 || s->ptn_revision!=4)return false;
 if(!waffle_haptic_read(io,0x7f0,0x46,&s->enable) ||
    !waffle_haptic_read(io,0x7f0,0x4c,&s->play) ||
    !waffle_haptic_read(io,0x7f0,0x4e,&s->swr) ||
    !waffle_haptic_read(io,0x7f0,0x48,&s->vmax) ||
    !waffle_haptic_read(io,0x7f0,0x47,&s->drive) ||
    !waffle_haptic_read(io,0x7f0,0x5c,&s->tlra[0]) ||
    !waffle_haptic_read(io,0x7f0,0x5d,&s->tlra[1]) ||
    !waffle_haptic_read(io,0x7f1,0x26,&s->direct))return false;
 for(unsigned i=0;i<4;i++)if(!waffle_haptic_read(io,0x7f1,0x30+i,&s->period[i]))return false;
 /* Native enable/stop prerequisites; observational only, never clear faults.
  * qcom-hv-haptics.c: haptics_enable_play/wait_brake_complete/load_constant_effect. */
 if(!waffle_haptic_read(io,0x7f0,0x0b,&s->hpwr) ||
    !waffle_haptic_read(io,0x7f0,0x0c,&s->fault) ||
    !waffle_haptic_read(io,0x7f0,0x50,&s->brake) ||
    !waffle_haptic_read(io,0x7f0,0x51,&s->cl_brake) ||
    !waffle_haptic_read(io,0x7f0,0x63,&s->autores) ||
    !waffle_haptic_read(io,0x7f0,0x72,&s->cal))return false;
 /* Native is_boost_vreg_enabled_in_open_loop and force_vreg_ready inputs.
  * HBST belongs to firmware: these observer reads never grant write ownership. */
 if(!waffle_haptic_read(io,0x7f0,0x68,&s->vset) ||
    !waffle_haptic_read(io,0x7f2,0x41,&s->boost_follow) ||
    !waffle_haptic_read(io,0x7f2,0x46,&s->boost_enable) ||
    !waffle_haptic_read(io,0x7f2,0x70,&s->boost_clamp))return false;
 /* Read configuration/status only; never read FIFO data ports or flush it. */
 if(!waffle_haptic_read(io,0x7f1,0x08,&s->fifo_ready) ||
    !waffle_haptic_read(io,0x7f1,0x24,&s->fifo_rate) ||
    !waffle_haptic_read(io,0x7f1,0x2a,&s->fifo_empty) ||
    !waffle_haptic_read(io,0x7f1,0x2b,&s->fifo_depth) ||
    !waffle_haptic_read(io,0x7f1,0xa0,&s->fifo_map))return false;
 s->complete=true;return true;
}
#endif
