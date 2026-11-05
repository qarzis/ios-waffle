#include <assert.h>
#include <stddef.h>
#include "waffle_display_irq_probe.h"
static uint32_t mem[0x84000/4];static unsigned writes,reads,fail_read;static bool write_fail,uncleared;
static bool rd(void *c,uint32_t off,uint32_t *v){assert(c==mem);if(++reads==fail_read)return false;*v=mem[off/4];return true;}
static bool wr(void *c,uint32_t off,uint32_t value){assert(c==mem && off==0x1018 && value==0x100);if(write_fail)return false;writes++;if(!uncleared)mem[0x1014/4]&=~value;return true;}
static struct waffle_display_completion_sample sample;
static struct waffle_display_irq_probe_state state;
static const struct waffle_display_irq_probe_io io={{mem,rd},wr};
static void setup(void){
 for(unsigned i=0;i<sizeof(mem)/sizeof(mem[0]);i++)mem[i]=0;
 writes=reads=fail_read=0;write_fail=uncleared=false;
 sample=(struct waffle_display_completion_sample){.frame_before=9,.frame_after=9,.address0=WAFFLE_DISPLAY_TEST,.address1=WAFFLE_DISPLAY_TEST,.irq_top=0x100,.ctl_active=2,.auto_status=1};
 waffle_display_irq_probe_begin(&state,1,&sample);waffle_display_irq_probe_commit(&state,1,&sample);sample.frame_before=sample.frame_after=10;
 mem[0]=0xa0000000;mem[0x362c0/4]=1;mem[0x5014/4]=mem[0x7014/4]=WAFFLE_DISPLAY_TEST;mem[0x360a4/4]=10;mem[0x1014/4]=0x101;
}
int main(void){
 setup();struct waffle_display_irq_probe_result r=waffle_display_irq_probe_step(&io,&state,1,&sample);
 assert(r.action==1 && r.wrote && writes==1 && state.armed && mem[0x1014/4]==1); /* Other flags preserved. */
 sample.irq_top=0;assert(!waffle_display_irq_probe_step(&io,&state,1,&sample).action && writes==1);
 sample.irq_top=0x100;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==2 && state.fresh && !r.wrote && writes==1);
 assert(!waffle_display_irq_probe_step(&io,&state,1,&sample).action && writes==1);
 for(unsigned n=0;n<9;n++){setup();switch(n){case 0:sample.flush=3;break;case 1:sample.frame_before=sample.frame_after=9;break;case 2:sample.frame_before=sample.frame_after=11;break;case 3:sample.frame_after++;break;case 4:sample.auto_status=0;break;case 5:sample.ctl_active=4;break;case 6:sample.irq_top_enable=1;break;case 7:sample.address1=WAFFLE_DISPLAY_FRONT;break;case 8:sample.irq_top=0;break;}
  r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(!writes && !r.wrote && !state.armed);
 }
 const uint32_t offsets[]={0,0x3625c,0x1010,0x362c0,0x16018,0x5014,0x7014,0x360a4};
 for(unsigned n=0;n<8;n++){setup();uint32_t off=offsets[n],saved=mem[off/4];mem[off/4]=off==0x362c0?0:saved+1;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==3 && !writes);}
 for(unsigned n=1;n<=9;n++){setup();fail_read=n;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==4 && !state.armed && writes==(n==9));}
 setup();mem[0x3625c/4]=0xf0000;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==1 && writes==1 && r.mux==0xf0000);
 setup();write_fail=true;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==4 && !writes && !state.armed);
 setup();uncleared=true;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==4 && writes==1 && !state.armed);
 setup();state.baseline=UINT32_MAX;sample.frame_before=sample.frame_after=0;mem[0x360a4/4]=0;r=waffle_display_irq_probe_step(&io,&state,1,&sample);assert(r.action==1);
 setup();r=waffle_display_irq_probe_step(&io,&state,2,&sample);assert(!r.action && !writes);
}
