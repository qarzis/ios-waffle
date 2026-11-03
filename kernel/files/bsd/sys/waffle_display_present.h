#ifndef WAFFLE_DISPLAY_PRESENT_H
#define WAFFLE_DISPLAY_PRESENT_H
#include "waffle_display_flip.h"
struct waffle_display_present_io {struct waffle_display_flip_io flip;bool (*copy_to)(void *,uint32_t);};
struct waffle_display_present_state {uint32_t active,completed;bool initialized,failed;};
struct waffle_display_present_result {uint32_t target,frame;bool copied,committed,rollback_attempted,rollback_ok;};
static inline bool waffle_display_present_init(const struct waffle_display_present_io *io,struct waffle_display_present_state *s)
{
 if(!s)return false;
 *s=(struct waffle_display_present_state){0};
 if(!io || !io->copy_to || !io->flip.domain_ok)return false;
 void *c=io->flip.control.read.context;uint32_t a,b;
 struct waffle_display_flush_result control;
 if(!io->flip.domain_ok(c) || !waffle_display_read(&io->flip.control.read,0x5070,&a) ||
    !waffle_display_read(&io->flip.control.read,0x7070,&b) || a || b ||
    !waffle_display_flush_unchanged(&io->flip.control,&control))return false;
 s->active=WAFFLE_DISPLAY_FRONT;s->initialized=true;return true;
}
static inline bool waffle_display_present_address(const struct waffle_display_present_io *io,uint32_t address,uint32_t *frame)
{
 void *c=io->flip.control.read.context;uint32_t before;
 if(!waffle_display_read(&io->flip.control.read,0x360a4,&before))return false;
 bool a=io->flip.control.write32(c,0x5014,address);
 bool b=io->flip.control.write32(c,0x7014,address);
 bool f=io->flip.control.write32(c,0x16018,3);
 return a && b && f && waffle_display_flip_wait(&io->flip,address,before,frame) && io->flip.domain_ok(c);
}
static inline bool waffle_display_present_frame(const struct waffle_display_present_io *io,struct waffle_display_present_state *s,struct waffle_display_present_result *r)
{
 if(!r)return false;
 *r=(struct waffle_display_present_result){0};
 if(!io || !s || !s->initialized || s->failed)return false;
 void *c=io->flip.control.read.context;uint32_t a,b,pending,auto_refresh;
 if(!io->flip.domain_ok(c) || !waffle_display_read(&io->flip.control.read,0x5014,&a) ||
    !waffle_display_read(&io->flip.control.read,0x7014,&b) ||
    !waffle_display_read(&io->flip.control.read,0x16018,&pending) ||
    !waffle_display_read(&io->flip.control.read,0x362b4,&auto_refresh) ||
    a!=s->active || b!=a || pending || auto_refresh!=0x80000001){s->failed=true;return false;}
 r->target=s->active==WAFFLE_DISPLAY_FRONT?WAFFLE_DISPLAY_TEST:WAFFLE_DISPLAY_FRONT;
 if(!io->copy_to(c,r->target)){s->failed=true;return false;}
 r->copied=true;
 if(!waffle_display_present_address(io,r->target,&r->frame)){
  r->rollback_attempted=true;r->rollback_ok=waffle_display_present_address(io,s->active,&r->frame);
  s->failed=true;return false;
 }
 r->committed=true;s->active=r->target;s->completed++;return true;
}
static inline bool waffle_display_present_restore(const struct waffle_display_present_io *io,struct waffle_display_present_state *s)
{
 if(!io || !s || !s->initialized)return true;
 s->failed=true; /* No new submissions after restoration starts. */
 uint32_t a,b,pending,frame;
 if(waffle_display_read(&io->flip.control.read,0x5014,&a) &&
    waffle_display_read(&io->flip.control.read,0x7014,&b) &&
    waffle_display_read(&io->flip.control.read,0x16018,&pending) &&
    a==WAFFLE_DISPLAY_FRONT && b==a && !pending && io->flip.domain_ok(io->flip.control.read.context)){
  s->active=WAFFLE_DISPLAY_FRONT;return true;
 }
 if(!waffle_display_present_address(io,WAFFLE_DISPLAY_FRONT,&frame))return false;
 s->active=WAFFLE_DISPLAY_FRONT;return true;
}
#endif
