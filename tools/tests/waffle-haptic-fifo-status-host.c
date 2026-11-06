#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_haptic_fifo_status.h"
struct bus {uint8_t cfg[256],ptn[256];unsigned reads,writes,fail_read,fail_write;bool ambiguous;};
static bool read8(void *context,uint16_t p,uint8_t a,uint8_t *v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_status_read_allowed(p,a));
 if(++b->reads==b->fail_read)return false;
 if(p==0x7f0 && (a==9 || a==10))assert(b->cfg[0x70]==5 && b->cfg[0x71]==0x80);
 *v=(p==0x7f0?b->cfg:b->ptn)[a];return true;
}
static bool write8(void *context,uint16_t p,uint8_t a,uint8_t v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_status_write_allowed(p,a));
 bool fail=++b->writes==b->fail_write;
 if(!fail || b->ambiguous)b->cfg[a]=v;
 return !fail;
}
static struct bus initial(void)
{
 struct bus b={0};b.cfg[1]=b.ptn[1]=4;b.cfg[0x46]=0x80;b.cfg[0x4c]=1;
 b.ptn[8]=1;b.ptn[0xa0]=0x8f;b.cfg[0x70]=0x33;b.cfg[0x71]=0x12;b.cfg[9]=0x40;
 return b;
}
static bool run(struct bus *b,struct waffle_haptic_fifo_status_result *r)
{
 const struct waffle_haptic_fifo_status_io io={b,read8,write8,true};
 return waffle_haptic_fifo_status(&io,r);
}
int main(void)
{
 struct bus b=initial();struct waffle_haptic_fifo_status_result r;
 assert(run(&b,&r)&&r.empty&&!r.full&&r.fill==0&&r.capacity==1920&&r.restored&&r.writes==4&&b.reads==14);
 assert(b.cfg[0x70]==0x33&&b.cfg[0x71]==0x12);
 for(unsigned failure=1;failure<=14;failure++){
  b=initial();b.fail_read=failure;assert(!run(&b,&r));
  assert(b.cfg[0x70]==0x33&&b.cfg[0x71]==0x12);
  if(failure<=10)assert(!b.writes&&!r.selection_attempted);
  else assert(b.writes==4);
 }
 for(unsigned failure=1;failure<=4;failure++)for(unsigned uncertain=0;uncertain<2;uncertain++){
  b=initial();b.fail_write=failure;b.ambiguous=uncertain;assert(!run(&b,&r));
  assert(!r.passed);
  if(failure<=2)assert(r.restored&&b.cfg[0x70]==0x33&&b.cfg[0x71]==0x12);
  else assert(!r.restored);
 }
 for(unsigned fill=0;fill<=1921;fill++){
  b=initial();b.cfg[9]=(fill>>8)|(fill==0?0x40:0)|(fill==1920?0x20:0);b.cfg[10]=fill;
  assert(run(&b,&r)==(fill<=1920));assert(r.fill==fill&&r.restored);
 }
 for(unsigned bad=0;bad<9;bad++){
  b=initial();
  switch(bad){case 0:b.cfg[1]=3;break;case 1:b.ptn[1]=3;break;
   case 2:b.cfg[0x46]=0;break;case 3:b.cfg[0x4c]=0x81;break;
   case 4:b.cfg[0x0b]=3;break;case 5:b.cfg[0x0c]=1;break;
   case 6:b.ptn[8]=0;break;case 7:b.ptn[0xa0]=0x0f;break;
   case 8:b.ptn[0xa0]=0x84;break;}
  assert(!run(&b,&r)&&!b.writes);
 }
 b=initial();b.cfg[9]=0;assert(run(&b,&r)&&r.fill==0&&!r.empty&&!r.full&&r.restored); /* actual H14 idle */
 for(unsigned flags=0;flags<4;flags++){
  b=initial();b.cfg[9]=((flags&1)?0x20:0)|((flags&2)?0x40:0);
  assert(run(&b,&r)&&r.fill==0&&r.restored);
 }
 const struct waffle_haptic_fifo_status_io denied={&b,read8,write8,false};
 b=initial();assert(!waffle_haptic_fifo_status(&denied,&r)&&!b.writes&&!b.reads);
 assert(!waffle_haptic_fifo_status(NULL,&r));
 puts("PASS native FIFO selector: idle/revision/ownership admission,14 read failures,8 ambiguous write failures,1922 fill counts,restore proof; no motor/FIFO/boost writes. Mock hardware only.");
}
