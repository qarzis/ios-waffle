#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "waffle_audio_smmu_survey.h"
static uint32_t registers[0x100000/4];
static unsigned reads,fail_at,change_at;
static bool read32(void *context,uint32_t offset,uint32_t *value)
{
 assert(context==registers && offset<0x100000 && !(offset&3));
 if(++reads==fail_at)return false;
 *value=registers[offset/4];
 if(change_at && offset==0x800 && reads>change_at)*value^=1;
 return true;
}
static const struct waffle_audio_smmu_io io={registers,read32};
static void fixture(bool exids)
{
 memset(registers,0,sizeof(registers));reads=fail_at=change_at=0;
 registers[0x20/4]=(1u<<30)|(1u<<27)|(13u<<9)|4|(exids?1u<<8:0);
 registers[0x24/4]=(6u<<28)|96;
 registers[0x28/4]=0x1000;
 registers[0x800/4]=0x1001|(0x80u<<16)|(exids?0:1u<<31);
 registers[0xc00/4]=9|(exids?1u<<10:0);
 registers[0x804/4]=0x1061|(exids?0:1u<<31);
 registers[0xc04/4]=10|(exids?1u<<10:0);
 for(unsigned cb=9;cb<=10;cb++){
  unsigned b=0x80000+cb*0x1000;
  registers[(0x1000+cb*4)/4]=0x10000|cb;
  registers[b/4]=1;registers[(b+0x20)/4]=0x81234000;
  registers[(b+0x24)/4]=0x110000;registers[(b+0x30)/4]=0x80003519;
  registers[(b+0x60)/4]=0x10001000;
 }
}
int main(void)
{
 struct waffle_audio_smmu_snapshot out;
 for(unsigned exids=0;exids<2;exids++){
  fixture(exids);assert(waffle_audio_smmu_survey(&io,&out) && out.complete);
  assert(out.cb_base==0x80000 && out.page_shift==12 && out.groups==4 && out.banks==96);
  assert(out.stream[0].matches==1 && out.stream[1].matches==1 && out.stream[2].matches==1);
  assert(out.stream[0].cb==9 && out.stream[1].cb==9 && out.stream[2].cb==10);
  assert(out.stream[0].context_read && out.stream[0].ttbr0==0x11000081234000ULL);
  assert(out.stream[2].far==0x10001000 && out.stream[2].cbar==0x1000a);
  unsigned successful_reads=reads;
  for(unsigned failure=1;failure<=successful_reads;failure++){
   fixture(exids);fail_at=failure;
   assert(!waffle_audio_smmu_survey(&io,&out) && !out.complete);
  }
 }
 fixture(false);registers[0x808/4]=registers[0x800/4];registers[0xc08/4]=9;
 assert(waffle_audio_smmu_survey(&io,&out) && out.stream[0].matches==2 && !out.stream[0].context_read);
 fixture(false);registers[0xc00/4]=1u<<16; /* Bypass: no context interpretation. */
 assert(waffle_audio_smmu_survey(&io,&out) && !out.stream[0].translated && !out.stream[0].context_read);
 fixture(false);registers[0xc00/4]=96;assert(!waffle_audio_smmu_survey(&io,&out));
 fixture(false);registers[0x20/4]&=~(1u<<27);assert(!waffle_audio_smmu_survey(&io,&out));
 fixture(false);registers[0x20/4]&=~255u;assert(!waffle_audio_smmu_survey(&io,&out));
 fixture(false);registers[0x24/4]|=1u<<31;assert(!waffle_audio_smmu_survey(&io,&out));
 fixture(false);change_at=5;assert(!waffle_audio_smmu_survey(&io,&out));
 fixture(true);registers[0xc00/4]&=~(1u<<10);
 assert(waffle_audio_smmu_survey(&io,&out) && !out.stream[0].matches && !out.stream[1].matches);
 fixture(false);registers[0x800/4]&=~(1u<<31);
 assert(waffle_audio_smmu_survey(&io,&out) && !out.stream[0].matches);
 fixture(false);assert(!waffle_audio_smmu_read(&io,3,&out.id0));
 assert(!waffle_audio_smmu_read(&io,0x100000,&out.id0));
 assert(!waffle_audio_smmu_survey(NULL,&out) && !waffle_audio_smmu_survey(&io,NULL));
 puts("PASS read-only audio SMMU survey: native legacy/EXID validity,1001/1081 masked match,1061,CB geometry/registers,64bit values,all read failures,ambiguity/reroute/bypass guards. Mock MMIO; no mapping ownership or DMA claim.");
}
