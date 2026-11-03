#ifndef WAFFLE_DISPLAY_FLIP_H
#define WAFFLE_DISPLAY_FLIP_H
#include "waffle_display_flush.h"
#include "waffle_display_smmu.h"
/* D03 bounded display control experiment: one reserved-buffer flip and restore.
 * Framebuffer range is reserved in live DT and the paired Waffle UEFI. */
#define WAFFLE_DISPLAY_FRONT 0xd5100000u
#define WAFFLE_DISPLAY_TEST  0xd6270000u
#define WAFFLE_DISPLAY_FRAME (5760u*3168u)
static inline bool waffle_display_flip_domain_valid(const struct waffle_display_smmu_snapshot *s)
{
 if(!s || !s->complete || s->id0!=0x4c017e6b || s->id1!=0x60000047 || (s->cr0&1))return false;
 for(unsigned i=0;i<2;i++){
  const struct waffle_display_smmu_route *r=&s->stream[i];
  if(r->sid!=0x1c00+2*i || r->matches!=1 || r->index!=4 || r->smr!=0x80021c00 || r->s2cr!=4 ||
     !r->context_read || r->cb!=4 || r->cbar!=0x1f000 || r->sctlr!=0xe0 || r->ttbr0 || r->ttbr1 || r->fsr!=0x400)return false;
 }
 return true;
}
struct waffle_display_flip_io {
 struct waffle_display_flush_io control;
 bool (*domain_ok)(void *);
 bool (*prepare)(void *,uint32_t,uint32_t);
};
struct waffle_display_flip_result {
 struct waffle_display_flush_result control;
 uint32_t stage,flip_frame,restore_frame;
 bool prepared,flipped,domain_after_flip,restore_attempted,restored,domain_after_restore;
};
static inline bool waffle_display_flip_wait(const struct waffle_display_flip_io *io,uint32_t address,uint32_t before,uint32_t *after)
{
 for(unsigned i=0;i<50;i++){
  uint32_t pending,a,b,auto_refresh;io->control.delay_ms(io->control.read.context,1);
  if(!waffle_display_read(&io->control.read,0x16018,&pending) || !waffle_display_read(&io->control.read,0x360a4,after) ||
     !waffle_display_read(&io->control.read,0x5014,&a) || !waffle_display_read(&io->control.read,0x7014,&b) ||
     !waffle_display_read(&io->control.read,0x362b4,&auto_refresh))return false;
  if(a!=address || b!=address || auto_refresh!=0x80000001)return false;
  uint32_t frames=*after-before;
  if(!pending && frames>=2 && frames<=8)return true;
 }
 return false;
}
static inline bool waffle_display_flip_test(const struct waffle_display_flip_io *io,struct waffle_display_flip_result *r)
{
 if(!r)return false;
 *r=(struct waffle_display_flip_result){0};
 if(!io || !io->domain_ok || !io->prepare || !io->control.write32 || !io->control.delay_ms)return false;
 void *context=io->control.read.context;
 uint32_t secure0,secure1;
 if(!io->domain_ok(context) || !waffle_display_read(&io->control.read,0x5070,&secure0) ||
    !waffle_display_read(&io->control.read,0x7070,&secure1) || secure0 || secure1 ||
    !waffle_display_flush_unchanged(&io->control,&r->control))return false;
 r->stage=1;
 if((uint64_t)WAFFLE_DISPLAY_TEST+WAFFLE_DISPLAY_FRAME>0xd7c00000ULL ||
    !io->prepare(context,WAFFLE_DISPLAY_TEST,WAFFLE_DISPLAY_FRAME))return false;
 r->prepared=true;
 uint32_t before;
 if(!io->domain_ok(context) || !waffle_display_read(&io->control.read,0x360a4,&before))return false;
 r->stage=2;
 bool a=io->control.write32(context,0x5014,WAFFLE_DISPLAY_TEST);
 bool b=a && io->control.write32(context,0x7014,WAFFLE_DISPLAY_TEST);
 bool c=a && b && io->control.write32(context,0x16018,3);
 r->flipped=c && waffle_display_flip_wait(io,WAFFLE_DISPLAY_TEST,before,&r->flip_frame);
 r->domain_after_flip=r->flipped && io->domain_ok(context);
 if(r->domain_after_flip){r->stage=3;io->control.delay_ms(context,5000);}
 /* Restoration is attempted even after partial address programming or a
  * read/flush fault. Never clear faults or invent recovery register writes. */
 r->restore_attempted=true;
 bool have_before=waffle_display_read(&io->control.read,0x360a4,&before);
 a=io->control.write32(context,0x5014,WAFFLE_DISPLAY_FRONT);
 b=io->control.write32(context,0x7014,WAFFLE_DISPLAY_FRONT);
 c=io->control.write32(context,0x16018,3);
 r->restored=have_before && a && b && c && waffle_display_flip_wait(io,WAFFLE_DISPLAY_FRONT,before,&r->restore_frame);
 r->domain_after_restore=r->restored && io->domain_ok(context);
 bool ok=r->flipped && r->domain_after_flip && r->restored && r->domain_after_restore;
 if(ok)r->stage=4;
 return ok;
}
#endif
