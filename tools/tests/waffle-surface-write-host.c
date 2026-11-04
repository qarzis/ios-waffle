#include <assert.h>
#include <string.h>
#include "waffle_gpu_surface_write.h"
static uint32_t pixels[8],original[8];static unsigned mode,cleans,execs,invalidates;
static bool to_gpu(void *c){assert(c==pixels);cleans++;if(cleans==1){assert(!memcmp(pixels,original,sizeof(pixels)));return mode!=1;}assert(!memcmp(pixels,original,sizeof(pixels)));return mode!=6;}
static bool execute(void *c,uint32_t *f){assert(c==pixels && cleans==1 && !invalidates);execs++;for(unsigned i=0;i<4;i++)pixels[i]=waffle_writeback_values[i];if(mode==5)pixels[2]^=1;*f=mode==3?0:7;return mode!=2;}
static bool to_cpu(void *c){assert(c==pixels && execs==1 && cleans==1);invalidates++;return mode!=4;}
int main(void){
 const struct waffle_surface_write_ops ops={pixels,to_gpu,execute,to_cpu};struct waffle_surface_write_result r;
 assert(!waffle_surface_write_check(NULL,pixels,&r));
 for(mode=0;mode<=6;mode++){
  for(unsigned i=0;i<8;i++)original[i]=pixels[i]=0xdead0000+i;
  cleans=execs=invalidates=0;
  bool ok=waffle_surface_write_check(&ops,pixels,&r);assert(ok==(mode==0));assert(r.saved);
  if(mode==1){assert(!r.attempted && !r.uncertain && cleans==1 && !execs && !memcmp(pixels,original,sizeof(pixels)));continue;}
  assert(r.attempted && execs==1);
  if(mode==2 || mode==3){assert(r.uncertain && !r.completed && !r.restored && cleans==1 && !invalidates);continue;}
  assert(r.completed);
  if(mode==4){assert(r.uncertain && !r.restored && cleans==1 && invalidates==1);continue;}
  assert(cleans==2 && invalidates==1 && !memcmp(pixels,original,sizeof(pixels)));
  assert(r.wrong==(mode==5));
  if(mode==6)assert(r.uncertain && !r.restored);else assert(!r.uncertain && r.restored);
  for(unsigned i=0;i<4;i++)assert(r.actual[i]==(waffle_writeback_values[i]^((mode==5 && i==2)?1:0)));
 }
}
