#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_display_flush.h"
static uint32_t mem[0x84000/4],writes,delays,fail=~0u;static bool stuck,stall_after_write,write_fail,changed;
static bool rd(void *p,uint32_t off,uint32_t *v){(void)p;assert(!(off&3)&&off<sizeof(mem));if(off==fail)return false;*v=mem[off/4];return true;}
static bool wr(void *p,uint32_t off,uint32_t v){(void)p;assert(off==0x16018&&v==3&&!writes);if(write_fail)return false;writes++;mem[off/4]=v;return true;}
static void delay(void *p,unsigned ms){(void)p;assert(ms==1);delays++;if(!stuck && !(stall_after_write && writes)){mem[0x16018/4]=0;mem[0x360a4/4]++;}if(changed)mem[0x7014/4]+=4096;}
static void reset(void){memset(mem,0,sizeof(mem));writes=delays=0;fail=~0u;stuck=stall_after_write=write_fail=changed=false;mem[0]=0xa0000000;mem[0x160f4/4]=2;mem[0x160fc/4]=0x30000;mem[0x36284/4]=9;mem[0x362b4/4]=0x80000001;
 for(unsigned i=0;i<2;i++){unsigned b=i?0x7000:0x5000;mem[(b+0x0)/4]=0x0c6002d0;mem[(b+0x8)/4]=i*720;mem[(b+0xc)/4]=0x0c6002d0;mem[(b+0x10)/4]=i*720;mem[(b+0x14)/4]=0xd5100000;mem[(b+0x24)/4]=5760;mem[(b+0x30)/4]=0x237ff;mem[(b+0x38)/4]=0x80000000;}}
int main(void){struct waffle_display_flush_io io={{NULL,rd},wr,delay};struct waffle_display_flush_result r;
 reset();assert(waffle_display_flush_unchanged(&io,&r)&&r.stage==4&&writes==1&&r.polls==2&&r.pre_polls==1&&r.after_frame-r.before_frame==2);
 const unsigned gates[]={0,0x160f4,0x160fc,0x36284,0x362b4,0x16018,0x16090,0x5000,0x5008,0x500c,0x5010,0x5014,0x5024,0x5030,0x5038,0x7000,0x7008,0x700c,0x7010,0x7014,0x7024,0x7030,0x7038};
 for(unsigned i=0;i<sizeof(gates)/sizeof(*gates);i++){reset();mem[gates[i]/4]^=1;assert(!waffle_display_flush_unchanged(&io,&r)&&!writes);}
 reset();stuck=true;assert(!waffle_display_flush_unchanged(&io,&r)&&!writes&&delays==32);
 reset();stall_after_write=true;assert(!waffle_display_flush_unchanged(&io,&r)&&writes==1&&r.polls==50);
 reset();write_fail=true;assert(!waffle_display_flush_unchanged(&io,&r)&&!writes&&delays==1);
 reset();changed=true;assert(!waffle_display_flush_unchanged(&io,&r)&&writes==1);
 reset();fail=0x16090;assert(!waffle_display_flush_unchanged(&io,&r)&&!writes);
 reset();fail=0x360a4;assert(!waffle_display_flush_unchanged(&io,&r)&&writes==0);
 puts("PASS unchanged-frame flush: exact native layout gates; one CTL_FLUSH write only; no address/START/IRQ/TE writes; bounded completion/frame progress and refusal paths; hardware mocked");}
