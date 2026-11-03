#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_display_smmu.h"
static uint32_t mem[0x100000/4],fail=~0u,maximum;
static bool rd(void *unused,uint32_t off,uint32_t *v){(void)unused;assert(!(off&3)&&off<sizeof(mem));if(off>maximum)maximum=off;if(off==fail)return false;*v=mem[off/4];return true;}
static void reset(void){memset(mem,0,sizeof(mem));mem[0x20/4]=(1u<<30)|(1u<<27)|(15u<<9)|4;mem[0x24/4]=(6u<<28)|71;fail=~0u;maximum=0;}
int main(void){
 struct waffle_display_smmu_io io={NULL,rd};struct waffle_display_smmu_snapshot s;
 reset();assert(waffle_display_smmu_capture(&io,&s)&&s.complete&&!s.stream[0].matches&&s.cb_base==0x80000);
 mem[0x800/4]=(1u<<31)|(2u<<16)|0x1c00;mem[0xc00/4]=1u<<16;
 assert(waffle_display_smmu_capture(&io,&s)&&s.stream[0].matches==1&&s.stream[1].matches==1&&!s.stream[0].context_read&&maximum<0x1000);
 mem[0xc00/4]=3;mem[0x83000/4]=1;mem[0x83020/4]=0x12345000;mem[0x83024/4]=2;
 assert(waffle_display_smmu_capture(&io,&s)&&s.stream[0].context_read&&s.stream[1].context_read&&s.stream[0].ttbr0==0x212345000ULL);
 mem[0x804/4]=(1u<<31)|0x1c00;mem[0xc04/4]=1u<<16;
 assert(waffle_display_smmu_capture(&io,&s)&&s.stream[0].matches==2&&!s.stream[0].context_read&&s.stream[1].context_read);
 mem[0x804/4]=(1u<<31)|0x1c01;assert(waffle_display_smmu_capture(&io,&s)&&s.stream[0].matches==1);
 const uint32_t failures[]={0,0x20,0x24,0x28,0x800,0xc00,0x100c,0x83000,0x83010,0x83020,0x83024,0x83028,0x8302c,0x83030,0x83058};
 for(unsigned i=0;i<sizeof(failures)/sizeof(*failures);i++){fail=failures[i];assert(!waffle_display_smmu_capture(&io,&s)&&!s.complete);}fail=~0u;
 mem[0xc00/4]=71;assert(!waffle_display_smmu_capture(&io,&s));
 reset();mem[0x24/4]=0xffffffff;assert(!waffle_display_smmu_capture(&io,&s));
 reset();mem[0x20/4]|=1u<<8;mem[0x800/4]=0x1c00|(2u<<16);mem[0xc00/4]=(1u<<10)|(1u<<16);
 assert(waffle_display_smmu_capture(&io,&s)&&s.exids&&s.stream[0].matches==1&&s.stream[1].matches==1);
 assert(!waffle_display_smmu_read(&io,3,&maximum)&&!waffle_display_smmu_read(&io,0x100000,&maximum));
 puts("PASS read-only display SMMU: native DT SID/mask, bypass/translation/secure exclusion, ambiguous routes,64bitTTBR, bounds and every selected register failure; no DMA mapping claim");
}
