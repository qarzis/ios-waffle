#ifndef WAFFLE_DISPLAY_FLUSH_H
#define WAFFLE_DISPLAY_FLUSH_H
#include "waffle_display_survey.h"
/* D02 only: commit UNCHANGED VIG0/VIG1 state. Native sspp_tbl entries0/1
 * select CTL_FLUSH bits0/1. No address, START, TE, IRQ or mode writes. */
struct waffle_display_flush_io {
 struct waffle_display_io read;
 bool (*write32)(void *,uint32_t,uint32_t);
 void (*delay_ms)(void *,unsigned);
};
struct waffle_display_flush_result {uint32_t stage,mask,pending,before_frame,after_frame,pre_polls,polls,writes;};
static inline bool waffle_display_flush_unchanged(const struct waffle_display_flush_io *io,struct waffle_display_flush_result *r)
{
 if(!r)return false;
 *r=(struct waffle_display_flush_result){0};
 if(!io || !io->write32 || !io->delay_ms)return false;
 struct waffle_display_snapshot s={0};uint32_t pending,mask;
 if(!waffle_display_capture(&io->read,&s,true) ||
    !waffle_display_read(&io->read,0x16018,&pending) || !waffle_display_read(&io->read,0x16090,&mask))return false;
 r->stage=1;r->mask=mask;r->pending=pending;r->before_frame=s.intf[1].mdp_frame;
 if(s.version!=0xa0000000 || s.ctl[0].intf_active!=2 || s.ctl[0].sspp_active!=0x30000 ||
    s.intf[1].tear_en!=9 || s.intf[1].auto_refresh!=0x80000001 || pending || mask)return false;
 for(unsigned i=0;i<2;i++){
  const struct waffle_display_sspp *p=&s.sspp[i];
  if(p->size!=0x0c6002d0 || p->out_size!=0x0c6002d0 || p->xy!=i*720 || p->out_xy!=i*720 ||
     p->address!=0xd5100000 || p->stride!=5760 || p->format!=0x237ff || p->op_mode!=0x80000000)return false;
 }
 bool progressing=false;
 for(unsigned i=0;i<32;i++){
  uint32_t frame;io->delay_ms(io->read.context,1);r->pre_polls++;
  if(!waffle_display_read(&io->read,0x360a4,&frame))return false;
  uint32_t steps=frame-r->before_frame;
  if(steps && steps<=4){r->before_frame=frame;progressing=true;break;}
  if(steps>4)return false;
 }
 if(!progressing)return false;
 r->stage=2;
 if(!io->write32(io->read.context,0x16018,3))return false;
 r->writes=1;r->stage=3;
 for(unsigned i=0;i<50;i++){
  uint32_t a,b,auto_refresh;
  io->delay_ms(io->read.context,1);r->polls++;
  if(!waffle_display_read(&io->read,0x16018,&pending) || !waffle_display_read(&io->read,0x360a4,&r->after_frame) ||
     !waffle_display_read(&io->read,0x5014,&a) || !waffle_display_read(&io->read,0x7014,&b) ||
     !waffle_display_read(&io->read,0x362b4,&auto_refresh))return false;
  r->pending=pending;
  if(a!=0xd5100000 || b!=a || auto_refresh!=0x80000001)return false;
  uint32_t frames=r->after_frame-r->before_frame;
  if(!pending && frames>=2 && frames<=8){r->stage=4;return true;}
 }
 return false;
}
#endif
