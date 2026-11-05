#ifndef WAFFLE_DISPLAY_COMPLETION_H
#define WAFFLE_DISPLAY_COMPLETION_H
#include "waffle_display_survey.h"
/* Observation only. Raw status is not a completion/fence decision.
 * Offsets from pinned SM8650 sde_hw_intf.c/sde_hw_ctl.c. No IRQ ack/enable. */
struct waffle_display_completion_sample {
 uint32_t frame_before,frame_after,flush,scheduler,auto_status,write_line,read_line,address0,address1;
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
     waffle_display_read(io,0x360a4,&s->frame_after);
}
#endif
