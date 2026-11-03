#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_display_flip.h"
static uint32_t mem[0x84000/4],writes,prepared,holds,domain_calls,fail_write;
static bool bad_domain,bad_prepare,stuck_flip,post_fault;
static bool rd(void *p,uint32_t off,uint32_t *v){(void)p;assert(!(off&3)&&off<sizeof(mem));*v=mem[off/4];return true;}
static bool wr(void *p,uint32_t off,uint32_t v){(void)p;writes++;assert(writes<=4096);if(writes==fail_write)return false;
 assert((off==0x16018&&v==3)||((off==0x5014||off==0x7014)&&(v==WAFFLE_DISPLAY_FRONT||v==WAFFLE_DISPLAY_TEST)));
 if(off!=0x16018)assert(prepared);
 mem[off/4]=v;return true;}
static void delay(void *p,unsigned ms){(void)p;assert(ms==1||ms==5000);if(ms==5000){holds++;assert(mem[0x5014/4]==WAFFLE_DISPLAY_TEST&&mem[0x7014/4]==WAFFLE_DISPLAY_TEST);mem[0x360a4/4]+=600;return;}
 if(stuck_flip&&mem[0x5014/4]==WAFFLE_DISPLAY_TEST)return;
 mem[0x16018/4]=0;mem[0x360a4/4]++;}
static bool domain(void *p){(void)p;domain_calls++;return !bad_domain&&!(post_fault&&mem[0x5014/4]==WAFFLE_DISPLAY_TEST);}
static bool prepare(void *p,uint32_t addr,uint32_t bytes){(void)p;assert(addr==0xd6270000&&bytes==18247680&&addr+bytes<=0xd7c00000);if(bad_prepare)return false;prepared++;return true;}
static void reset(void){memset(mem,0,sizeof(mem));writes=prepared=holds=domain_calls=fail_write=0;bad_domain=bad_prepare=stuck_flip=post_fault=false;mem[0]=0xa0000000;mem[0x160f4/4]=2;mem[0x160fc/4]=0x30000;mem[0x36284/4]=9;mem[0x362b4/4]=0x80000001;
 for(unsigned i=0;i<2;i++){unsigned b=i?0x7000:0x5000;mem[(b+0x0)/4]=0x0c6002d0;mem[(b+0x8)/4]=i*720;mem[(b+0xc)/4]=0x0c6002d0;mem[(b+0x10)/4]=i*720;mem[(b+0x14)/4]=WAFFLE_DISPLAY_FRONT;mem[(b+0x24)/4]=5760;mem[(b+0x30)/4]=0x237ff;mem[(b+0x38)/4]=0x80000000;}}
int main(void){
 struct waffle_display_smmu_snapshot s={.complete=true,.id0=0x4c017e6b,.id1=0x60000047};
 for(unsigned i=0;i<2;i++)s.stream[i]=(struct waffle_display_smmu_route){.sid=0x1c00+2*i,.matches=1,.index=4,.smr=0x80021c00,.s2cr=4,.cb=4,.cbar=0x1f000,.sctlr=0xe0,.fsr=0x400,.context_read=true};
 assert(waffle_display_flip_domain_valid(&s));s.stream[0].sctlr|=1;assert(!waffle_display_flip_domain_valid(&s));s.stream[0].sctlr&=~1u;
 s.stream[1].ttbr0=4096;assert(!waffle_display_flip_domain_valid(&s));s.stream[1].ttbr0=0;
 s.stream[1].fsr|=2;assert(!waffle_display_flip_domain_valid(&s));s.stream[1].fsr=0x400;s.stream[1].matches=2;assert(!waffle_display_flip_domain_valid(&s));
 struct waffle_display_flip_io io={{{NULL,rd},wr,delay},domain,prepare};struct waffle_display_flip_result r;
 reset();assert(waffle_display_flip_test(&io,&r)&&r.stage==4&&r.flipped&&r.restored&&writes==7&&prepared==1&&holds==1&&domain_calls==4);
 reset();mem[0x5070/4]=15;assert(!waffle_display_flip_test(&io,&r)&&!writes&&!prepared);
 reset();mem[0x7070/4]=15;assert(!waffle_display_flip_test(&io,&r)&&!writes&&!prepared);
 reset();bad_domain=true;assert(!waffle_display_flip_test(&io,&r)&&!writes&&!prepared&&!r.restore_attempted);
 reset();bad_prepare=true;assert(!waffle_display_flip_test(&io,&r)&&writes==1&&!r.restore_attempted);
 for(unsigned i=2;i<=4;i++){reset();fail_write=i;assert(!waffle_display_flip_test(&io,&r)&&r.restore_attempted&&r.restored&&!holds&&mem[0x5014/4]==WAFFLE_DISPLAY_FRONT&&mem[0x7014/4]==WAFFLE_DISPLAY_FRONT);}
 reset();stuck_flip=true;assert(!waffle_display_flip_test(&io,&r)&&r.restore_attempted&&r.restored&&!holds);
 reset();post_fault=true;assert(!waffle_display_flip_test(&io,&r)&&r.flipped&&!r.domain_after_flip&&r.restored&&!holds);
 reset();fail_write=5;assert(!waffle_display_flip_test(&io,&r)&&r.restore_attempted&&!r.restored);
 puts("PASS bounded reserved-buffer flip: preflight/domain/layout before preparation, exact addresses and7writes,5second hold, restoration after partial/fault/stall, restoration failure retained; hardware mocked");return 0;}
