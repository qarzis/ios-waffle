#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "waffle_display_survey.h"
static unsigned calls,fail_at;static uint32_t offsets[256];
static bool rd(void *ctx,uint32_t off,uint32_t *v){assert(ctx==offsets && off<0x84000 && !(off&3));assert(calls<256);offsets[calls++]=off;if(calls==fail_at)return false;*v=off?off^0x12345678:0x90000000;return true;}
int main(void){
 struct waffle_display_snapshot s;memset(&s,0,sizeof(s));struct waffle_display_io io={offsets,rd};
 assert(waffle_display_capture(&io,&s,true));unsigned full=calls;assert(full==1+4*16+6*4+10*8);
 assert(s.intf[1].tear_out==(0x362ac^0x12345678));assert(s.sspp[9].address==(0x2f014^0x12345678));assert(s.ctl[5].intf_active==(0x1b0f4^0x12345678));
 for(unsigned i=1;i<=full;i++){calls=0;fail_at=i;assert(!waffle_display_capture(&io,&s,true));assert(calls==i);}
 calls=0;fail_at=0;assert(waffle_display_capture(&io,&s,false));assert(calls==65);for(unsigned i=0;i<calls;i++)assert(!offsets[i] || (offsets[i]>=0x35000 && offsets[i]<0x39000));
 uint32_t v;assert(!waffle_display_read(&io,3,&v));assert(!waffle_display_read(&io,0x84000,&v));assert(!waffle_display_read(NULL,0,&v));assert(!waffle_display_capture(&io,NULL,true));
 puts("PASS read-only actual DPU snapshot: native INTF/CTL/SSPP offsets,0x84000-region bounds,all read failures,sample-only excludes CTL/SSPP,no write callback. Mock MMIO; not hardware sync proof.");
}
