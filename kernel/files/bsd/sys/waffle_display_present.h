#ifndef WAFFLE_DISPLAY_PRESENT_H
#define WAFFLE_DISPLAY_PRESENT_H
#include "waffle_display_flip.h"
struct waffle_display_present_io {struct waffle_display_flip_io flip;bool (*copy_to)(void *,uint32_t);};
struct waffle_display_present_state {uint32_t active,completed;bool initialized,failed;uint32_t pending_target,pending_before;bool pending;};
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
 if(!io || !s || !s->initialized || s->failed || s->pending)return false;
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
/* Split only the final completion wait, not the two-frame reuse guard.
 * The presenter may compose into private working RAM while this immutable
 * scanout copy is pending. It must complete before copying either A/B again. */
static inline bool waffle_display_present_pending_wait(const struct waffle_display_present_io *io,uint32_t target,uint32_t before,uint32_t *after)
{
 /* Completion may be observed after an arbitrarily idle UI interval. The
  * old synchronous <=8-frame window is not a deadline for this caller.
  * Require at least two forward frames, with half-range wrap protection. */
 for(unsigned i=0;i<50;i++){
  uint32_t pending,a,b,auto_refresh;
  if(!waffle_display_read(&io->flip.control.read,0x16018,&pending) ||
     !waffle_display_read(&io->flip.control.read,0x360a4,after) ||
     !waffle_display_read(&io->flip.control.read,0x5014,&a) ||
     !waffle_display_read(&io->flip.control.read,0x7014,&b) ||
     !waffle_display_read(&io->flip.control.read,0x362b4,&auto_refresh))return false;
  uint32_t frames=*after-before;
  if(a!=target || b!=target || auto_refresh!=0x80000001 || frames>=0x80000000u)return false;
  if(!pending && frames>=2)return true;
  io->flip.control.delay_ms(io->flip.control.read.context,1);
 }
 return false;
}
static inline bool waffle_display_present_complete(const struct waffle_display_present_io *io,struct waffle_display_present_state *s,struct waffle_display_present_result *r)
{
 if(!r)return false;
 *r=(struct waffle_display_present_result){0};
 if(!io || !s || !s->initialized || s->failed)return false;
 if(!s->pending)return true;
 r->target=s->pending_target;r->copied=true;
 bool ok=waffle_display_present_pending_wait(io,r->target,s->pending_before,&r->frame) &&
     io->flip.domain_ok(io->flip.control.read.context);
 if(!ok){
  r->rollback_attempted=true;r->rollback_ok=waffle_display_present_address(io,s->active,&r->frame);
  s->failed=true;s->pending=false;return false;
 }
 s->active=r->target;s->completed++;s->pending=false;r->committed=true;return true;
}
static inline bool waffle_display_present_begin(const struct waffle_display_present_io *io,struct waffle_display_present_state *s,struct waffle_display_present_result *r)
{
 if(!r)return false;
 *r=(struct waffle_display_present_result){0};
 if(!io || !s || !s->initialized || s->failed || s->pending)return false;
 void *c=io->flip.control.read.context;uint32_t a,b,pending,auto_refresh;
 if(!io->flip.domain_ok(c) || !waffle_display_read(&io->flip.control.read,0x5014,&a) ||
    !waffle_display_read(&io->flip.control.read,0x7014,&b) ||
    !waffle_display_read(&io->flip.control.read,0x16018,&pending) ||
    !waffle_display_read(&io->flip.control.read,0x362b4,&auto_refresh) ||
    a!=s->active || b!=a || pending || auto_refresh!=0x80000001){s->failed=true;return false;}
 r->target=s->active==WAFFLE_DISPLAY_FRONT?WAFFLE_DISPLAY_TEST:WAFFLE_DISPLAY_FRONT;
 if(!io->copy_to(c,r->target)){s->failed=true;return false;}
 r->copied=true;
 if(!waffle_display_read(&io->flip.control.read,0x360a4,&s->pending_before)){s->failed=true;return false;}
 bool wa=io->flip.control.write32(c,0x5014,r->target);
 bool wb=io->flip.control.write32(c,0x7014,r->target);
 bool wf=io->flip.control.write32(c,0x16018,3);
 if(!wa || !wb || !wf){
  r->rollback_attempted=true;r->rollback_ok=waffle_display_present_address(io,s->active,&r->frame);
  s->failed=true;return false;
 }
 s->pending_target=r->target;s->pending=true;return true;
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
  s->active=WAFFLE_DISPLAY_FRONT;s->pending=false;return true;
 }
 if(!waffle_display_present_address(io,WAFFLE_DISPLAY_FRONT,&frame))return false;
 s->active=WAFFLE_DISPLAY_FRONT;s->pending=false;return true;
}
#endif
