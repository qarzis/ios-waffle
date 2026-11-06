#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_haptic_fifo_buffer.h"
struct bus {uint8_t cfg[256],ptn[256],source;unsigned fill,reads,writes,data,fail_read,fail_write,fail_data;bool ambiguous;};
static bool read8(void *context,uint16_t p,uint8_t a,uint8_t *v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_buffer_read_allowed(p,a));
 if(++b->reads==b->fail_read)return false;
 *v=(p==0x7f0?b->cfg:b->ptn)[a];
 if(p==0x7f0 && (a==9 || a==10)){
  assert(b->cfg[0x70]==5);
  if(b->cfg[0x71]==0x80)*v=a==9?b->fill>>8:b->fill;
  else {assert(b->cfg[0x71]==0);*v=a==10?b->source:0;}
 }
 return true;
}
static bool write8(void *context,uint16_t p,uint8_t a,uint8_t v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_buffer_write_allowed(p,a));
 bool failed=++b->writes==b->fail_write;
 if(!failed || b->ambiguous){
  if(p==0x7f0){if(a==0x4e && (v&0xe0))assert(!b->fill);b->cfg[a]=v;}
  else {assert(a==0x2d && v<=1);if(b->ptn[a]==1 && v==0)b->fill=0;b->ptn[a]=v;}
 }
 return !failed;
}
static bool write4(void *context,uint16_t p,uint8_t a,const uint8_t *v)
{
 struct bus *b=context;assert(p==0x7f1&&a==0x20&&!b->ptn[0x2d]&&!(b->cfg[0x4e]&0xe0));
 assert(!v[0]&&!v[1]&&!v[2]&&!v[3]);bool failed=++b->data==b->fail_data;
 if(!failed || b->ambiguous)b->fill+=4;
 return !failed;
}
static struct bus initial(void)
{
 struct bus b={0};b.cfg[1]=b.ptn[1]=4;b.cfg[0x46]=0x80;b.cfg[0x4c]=1;
 b.cfg[0x4e]=0xe0;b.cfg[0x70]=0x33;b.cfg[0x71]=0x12;b.ptn[8]=1;b.ptn[0xa0]=0x8f;b.source=1;return b;
}
static bool run(struct bus *b,struct waffle_haptic_fifo_buffer_result *r)
{
 const struct waffle_haptic_fifo_buffer_io io={{b,read8,write8,true},write4};return waffle_haptic_fifo_buffer(&io,r);
}
int main(void)
{
 struct bus b=initial();struct waffle_haptic_fifo_buffer_result r;
 assert(run(&b,&r)&&r.loaded_fill==144&&r.final_fill==0&&r.data_commands==36&&r.swr_restored&&r.selectors_restored);
 unsigned reads=b.reads,writes=b.writes;assert(b.cfg[0x4e]==0xe0&&b.cfg[0x70]==0x33&&b.cfg[0x71]==0x12&&!b.fill);
 for(unsigned n=1;n<=reads;n++){
  b=initial();b.fail_read=n;assert(!run(&b,&r));
  if(b.fill)assert(!(b.cfg[0x4e]&0xe0));
 }
 for(unsigned n=1;n<=writes;n++)for(unsigned uncertain=0;uncertain<2;uncertain++){
  b=initial();b.fail_write=n;b.ambiguous=uncertain;assert(!run(&b,&r));
  if(b.fill)assert(!(b.cfg[0x4e]&0xe0));
 }
 for(unsigned n=1;n<=36;n++)for(unsigned uncertain=0;uncertain<2;uncertain++){
  b=initial();b.fail_data=n;b.ambiguous=uncertain;assert(!run(&b,&r));
  assert(b.data==n&&!b.fill&&r.cleared&&r.swr_restored);
 }
 b=initial();b.source=4;assert(!run(&b,&r)&&!b.data&&b.cfg[0x4e]==0xe0);
 b=initial();b.fill=12;assert(!run(&b,&r)&&!b.data&&b.fill==12);
 b=initial();b.ptn[0x2d]=0x80;assert(!run(&b,&r)&&!b.data&&b.ptn[0x2d]==0x80);
 b=initial();const struct waffle_haptic_fifo_buffer_io denied={{&b,read8,write8,false},write4};
 assert(!waffle_haptic_fifo_buffer(&denied,&r)&&!b.reads&&!b.writes&&!b.data);
 printf("PASS zero FIFO transport: %u read faults,%u write faults x2 ambiguity,72 partial data failures; active SWR/nonempty/PAT access refused; no motor/rate/voltage/boost writes. Mock only.\n",reads,writes);
}
