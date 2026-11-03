#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_vsync_phase.h"
static unsigned reads,mode;static bool rd(void *ctx,uint32_t off,uint32_t *v){(void)ctx;assert(off==0x36214 || off==0x36218);reads++;if(mode==3)return false;if(off==0x36214)*v=0x12345678;else *v=mode==1 && reads<=3?reads==1?1:2:mode==2?reads:2;return true;}
int main(void){
 struct waffle_vsync_clock c={NULL,rd};uint64_t s=0;assert(waffle_vsync_timestamp(&c,&s) && s==0x212345678ULL && reads==3);
 mode=1;reads=0;assert(waffle_vsync_timestamp(&c,&s) && reads==6 && s==0x212345678ULL);
 mode=2;reads=0;assert(!waffle_vsync_timestamp(&c,&s) && reads==9);mode=3;reads=0;assert(!waffle_vsync_timestamp(&c,&s));assert(!waffle_vsync_timestamp(NULL,&s));
 assert(waffle_vsync_divider(19200000,158930,60)==2);assert(waffle_vsync_divider(19200000,320000,60)==1);assert(!waffle_vsync_divider(19200000,213333,60));assert(!waffle_vsync_divider(0,1,60));assert(!waffle_vsync_divider(1,UINT64_MAX,240));
 struct waffle_vsync_phase p={0};uint64_t period=160000,ts=1000000;assert(waffle_vsync_observe(&p,ts,ts+100,period,2)==WAFFLE_VSYNC_WAIT);
 for(unsigned i=1;i<=60;i++){assert(waffle_vsync_observe(&p,ts,ts+1000,period,2)==WAFFLE_VSYNC_WAIT);ts+=period;int r=waffle_vsync_observe(&p,ts,ts+100,period,2);assert(r==(i%2?WAFFLE_VSYNC_WAIT:WAFFLE_VSYNC_EDGE));}
 assert(p.sent==ts);assert(waffle_vsync_observe(&p,ts,ts+period*3+1,period,2)==WAFFLE_VSYNC_FAULT);
 struct waffle_vsync_phase base=p;assert(waffle_vsync_observe(&p,ts-1,ts+1,period,2)==WAFFLE_VSYNC_FAULT);assert(!memcmp(&p,&base,sizeof(p)));
 assert(waffle_vsync_observe(&p,ts+1,ts,period,2)==WAFFLE_VSYNC_FAULT);assert(waffle_vsync_observe(&p,ts+period/2,ts+period/2,period,2)==WAFFLE_VSYNC_FAULT);
 p=(struct waffle_vsync_phase){0};ts=0xffffffffULL-10;assert(waffle_vsync_observe(&p,ts,ts,period,1)==WAFFLE_VSYNC_WAIT);ts+=period;assert(waffle_vsync_observe(&p,ts,ts,period,1)==WAFFLE_VSYNC_EDGE);
 assert(waffle_vsync_observe(&p,ts+9*period,ts+9*period,period,1)==WAFFLE_VSYNC_FAULT);
 puts("PASS hardware timestamp phase: high/low/high rollover retry/read failures; measured120.8Hz->60Hz divider; duplicates/monotonicity/stall/reset/skipped-edge/64bit-rollover guards. No MMIO writes; host only.");
}
