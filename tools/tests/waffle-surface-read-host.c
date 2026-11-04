#include <assert.h>
#include <string.h>
#include "waffle_gpu_surface_read.h"
static uint32_t source[8],destination[8],original[8];static unsigned mode,cleans,execs,invalidates;
static bool to_gpu(void *c){assert(c==source);cleans++;if(cleans==1){for(unsigned i=0;i<4;i++)assert(source[i]==waffle_writeback_values[i] && destination[i]==0xbad00000u+i);return mode!=1;}assert(!memcmp(source,original,sizeof(source)));return mode!=6;}
static bool execute(void *c,uint32_t *f){assert(c==source && cleans==1 && !invalidates);execs++;for(unsigned i=0;i<4;i++)destination[i]=source[i];if(mode==5)destination[2]^=1;*f=mode==3?0:7;return mode!=2;}
static bool to_cpu(void *c){assert(c==source && execs==1);invalidates++;return mode!=4;}
int main(void){
 uint32_t packet[27];memset(packet,0xcc,sizeof(packet));
 assert(waffle_surface_read_packet(packet,25,0x123456780ULL,0x234567890ULL)==25);
 for(unsigned i=0;i<4;i++){assert(packet[i*6]==0x70738005 && packet[i*6+1]==0);assert(packet[i*6+2]==0x34567890+4*i && packet[i*6+3]==2);assert(packet[i*6+4]==0x23456780+4*i && packet[i*6+5]==1);}
 assert(packet[24]==0x70928000 && packet[25]==0xcccccccc && packet[26]==0xcccccccc);
 assert(!waffle_surface_read_packet(packet,24,0x10000,0x20000));
 assert(!waffle_surface_read_packet(packet,25,0x10000,0x1000c));
 assert(!waffle_surface_read_packet(packet,25,0x10001,0x20000));
 assert(!waffle_surface_read_packet(packet,25,UINT64_MAX-3,0x20000));
 assert(!waffle_surface_read_packet(packet,25,(1ULL<<39)-4,0x20000));
 const struct waffle_surface_write_ops ops={source,to_gpu,execute,to_cpu};struct waffle_surface_write_result r;
 for(mode=0;mode<=6;mode++){
  for(unsigned i=0;i<8;i++){source[i]=original[i]=0x12340000+i;destination[i]=0xabcd0000+i;}
  cleans=execs=invalidates=0;bool ok=waffle_surface_read_check(&ops,source,destination,&r);assert(ok==(mode==0));
  if(mode==1){assert(r.restored && !r.attempted && !memcmp(source,original,sizeof(source)));continue;}
  if(mode==2 || mode==3 || mode==4){assert(r.uncertain && !r.restored);continue;}
  assert(!memcmp(source,original,sizeof(source)) && r.wrong==(mode==5));
  assert(r.restored==(mode!=6) && r.uncertain==(mode==6));
  for(unsigned i=4;i<8;i++)assert(destination[i]==0xabcd0000+i);
 }
}
