#ifndef WAFFLE_DISPLAY_COMPLETION_H
#define WAFFLE_DISPLAY_COMPLETION_H
#include "waffle_display_survey.h"
/* Observation only. Raw status is not a completion/fence decision.
 * Offsets from pinned SM8650 sde_hw_intf.c/sde_hw_ctl.c/sde_hw_interrupts.c, sde_hwio.h and
 * live DT top=0x1000/INTF1 tear IRQ=0x36800. No IRQ ack/enable writes. */
struct waffle_display_completion_sample {
 uint32_t frame_before,frame_after,flush,scheduler,auto_status,write_line,read_line,address0,address1;
 uint32_t irq_top,irq_top_enable,irq_ctl,irq_ctl_enable,irq_tear,irq_tear_enable,ctl_active;
};
static inline bool waffle_display_completion_capture(const struct waffle_display_io *io,struct waffle_display_completion_sample *s)
{
 if(!s)return false;
 *s=(struct waffle_display_completion_sample){0};
 return waffle_display_read(io,0x360a4,&s->frame_before) &&
     waffle_display_read(io,0x16018,&s->flush) &&
     waffle_display_read(io,0x16064,&s->scheduler) &&
     waffle_display_read(io,0x362c0,&s->auto_status) &&
     waffle_display_read(io,0x362b0,&s->write_line) &&
     waffle_display_read(io,0x362ac,&s->read_line) &&
     waffle_display_read(io,0x5014,&s->address0) &&
     waffle_display_read(io,0x7014,&s->address1) &&
     waffle_display_read(io,0x1014,&s->irq_top) &&
     waffle_display_read(io,0x1010,&s->irq_top_enable) &&
     waffle_display_read(io,0x100c,&s->irq_ctl) &&
     waffle_display_read(io,0x1008,&s->irq_ctl_enable) &&
     waffle_display_read(io,0x36804,&s->irq_tear) &&
     waffle_display_read(io,0x36800,&s->irq_tear_enable) &&
     waffle_display_read(io,0x160f4,&s->ctl_active) &&
     waffle_display_read(io,0x360a4,&s->frame_after);
}
#endif
