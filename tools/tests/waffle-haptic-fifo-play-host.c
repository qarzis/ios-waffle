#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_haptic_fifo_play.h"
#include "waffle_haptic_fifo_buffer.h"
struct bus {uint8_t reg[3][256];unsigned reads,writes,waits,fail_read,fail_write,queued,data;uint64_t us,start;bool playing,ambiguous,stuck_stop,freeze,no_progress,instant_empty,refill,fault,buffer_mode;};
static unsigned fill(struct bus *b){unsigned used=(unsigned)(b->us-b->start)*24/1000;unsigned size=b->buffer_mode?b->queued:144;return !b->playing?size:b->instant_empty?0:b->refill?148:b->no_progress?size:used>=size?0:size-used;}
static bool read8(void *context,uint16_t p,uint8_t a,uint8_t *v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_play_read_allowed(p,a)||(b->buffer_mode&&waffle_haptic_fifo_buffer_read_allowed(p,a)));assert(p>=0x7f0&&p<=0x7f2);
 if(++b->reads==b->fail_read)return false;
 *v=b->reg[p-0x7f0][a];
 if(p==0x7f0){
  if(a==0x0b)*v=b->playing?3:0;
  if(a==0x0c && b->fault && b->playing)*v=1;
  if(a==9 || a==10){
   assert(b->reg[0][0x70]==5);
   if(b->buffer_mode&&b->reg[0][0x71]==0)*v=a==10?7:0;
   else {assert(b->reg[0][0x71]==0x80);unsigned count=fill(b);*v=a==9?count>>8:count;}
  }
 }
 return true;
}
static bool write8(void *context,uint16_t p,uint8_t a,uint8_t v)
{
 struct bus *b=context;assert(waffle_haptic_fifo_play_write_allowed(p,a)||(b->buffer_mode&&waffle_haptic_fifo_buffer_write_allowed(p,a)));
 bool fail=++b->writes==b->fail_write;
 if(!fail || b->ambiguous){
  if(p==0x7f0&&a==0x4c){
   if(v==0x80){assert(b->reg[1][0x24]==0xea&&b->reg[0][0x5e]==2&&b->reg[0][0x5f]==0x3e&&b->reg[0][0x72]==8&&b->reg[0][0x63]==9);b->playing=true;b->start=b->us;}
   else if(!b->stuck_stop){if(b->playing&&b->buffer_mode)b->queued=fill(b);b->playing=false;}
  }
  if(p==0x7f0&&a==0x46&&!(v&0x80))b->playing=false;
  if(b->buffer_mode&&p==0x7f0&&a==0x4e&&(v&0x40))assert(!b->queued&&!b->playing);
  if(b->buffer_mode&&p==0x7f1&&a==0x2d&&b->reg[1][a]==1&&v==0)b->queued=0;
  b->reg[p-0x7f0][a]=v;
 }
 return !fail;
}
static uint64_t now(void *context){struct bus *b=context;return b->freeze?0:b->us;}
static void wait(void *context,uint32_t us){struct bus *b=context;assert(us<=1000&&++b->waits<=52);b->us+=us;}
static struct bus initial(void)
{
 struct bus b={0};b.reg[0][1]=b.reg[1][1]=4;b.reg[2][0]=2;
 b.reg[0][0x46]=0x80;b.reg[0][0x4c]=1;b.reg[0][0x48]=0x30;
 b.reg[0][0x4e]=0xa0;b.reg[0][0x63]=0x89;b.reg[0][0x72]=4;b.reg[2][0x41]=0xe0;
 b.reg[1][8]=1;b.reg[1][0xa0]=0x8f;b.reg[1][0x24]=0xe0;
 b.reg[0][0x5e]=1;b.reg[0][0x5f]=2;b.reg[0][0x70]=0x33;b.reg[0][0x71]=0x12;
 return b;
}
static bool run(struct bus *b,struct waffle_haptic_fifo_play_result *r)
{
 const struct waffle_haptic_fifo_play_io io={{{b,read8},write8,now,wait,true},574};
 return waffle_haptic_fifo_play(&io,r);
}
struct consumer {struct bus *bus;struct waffle_haptic_fifo_play_result result;};
static bool consume(void *context){struct consumer *c=context;return run(c->bus,&c->result);}
static bool write4(void *context,uint16_t p,uint8_t a,const uint8_t *v){struct bus *b=context;assert(b->buffer_mode&&p==0x7f1&&a==0x20&&!b->playing&&!(b->reg[0][0x4e]&0x40)&&!v[0]&&!v[1]&&!v[2]&&!v[3]);b->queued+=4;b->data++;return true;}
static void restored(struct bus *b){struct bus old=initial();assert(!memcmp(b->reg,old.reg,sizeof(b->reg))&&!b->playing);}
int main(void)
{
 struct bus b=initial();struct waffle_haptic_fifo_play_result r;
 assert(run(&b,&r)&&r.admitted&&r.start_attempted&&r.progress&&r.drained&&r.stopped&&r.restored&&r.initial_fill==144&&!r.last_fill&&r.active_us==6000);restored(&b);
 unsigned reads=b.reads,writes=b.writes;
 for(unsigned n=1;n<=reads;n++){
  b=initial();b.fail_read=n;assert(!run(&b,&r));assert(!b.playing);
  if(r.restored)restored(&b);
 }
 for(unsigned n=1;n<=writes;n++)for(unsigned uncertain=0;uncertain<2;uncertain++){
  b=initial();b.fail_write=n;b.ambiguous=uncertain;assert(!run(&b,&r));assert(!b.playing);
  if(r.restored)restored(&b);
 }
 for(unsigned mode=0;mode<6;mode++){
  b=initial();b.freeze=mode==0;b.no_progress=mode==1;b.instant_empty=mode==2;b.refill=mode==3;b.fault=mode==4;b.stuck_stop=mode==5;
  assert(!run(&b,&r)&&!b.playing);
  if(mode==5)assert(r.emergency_disabled&&!r.restored);
 }
 b=initial();b.reg[0][0x4e]=0xe0;assert(!run(&b,&r)&&!b.writes);
 b=initial();b.reg[0][0x4e]=0;assert(!run(&b,&r)&&!b.writes);
 b=initial();const struct waffle_haptic_fifo_play_io denied={{{&b,read8},write8,now,wait,false},574};assert(!waffle_haptic_fifo_play(&denied,&r)&&!b.reads&&!b.writes);
 for(unsigned mode=0;mode<3;mode++){
  b=initial();b.buffer_mode=true;b.reg[0][0x4e]=0xe0;b.no_progress=mode==1;b.stuck_stop=mode==2;
  const struct waffle_haptic_fifo_buffer_io io={{&b,read8,write8,true},write4};
  struct waffle_haptic_fifo_buffer_result buffer;struct consumer c={.bus=&b};
  assert(waffle_haptic_fifo_buffer_consume(&io,&buffer,consume,&c)==(mode==0));
  assert(b.data==36&&!b.playing&&!b.queued);
  if(mode==0)assert(buffer.cleared&&buffer.swr_restored&&b.reg[0][0x4e]==0xe0);
  else {assert(!buffer.swr_restored&&!(b.reg[0][0x4e]&0x40));if(mode==2)assert(c.result.emergency_disabled);}
 }
 printf("PASS zero FIFO execution: %u read faults,%u writes x2 ambiguity; actual progress/time/drain required; stalled clock/FIFO/instant empty/refill/fault/stuck stop handled, config restored or emergency disabled. Mock only.\n",reads,writes);
}
