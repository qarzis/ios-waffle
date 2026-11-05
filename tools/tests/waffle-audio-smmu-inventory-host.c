#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_audio_smmu_inventory.h"
static uint32_t regs[0x100000/4];
static unsigned reads,fail_at,mutate_at;
static bool rd(void *ctx,uint32_t off,uint32_t *v){assert(ctx==regs);if(++reads==fail_at)return false;*v=regs[off/4];if(reads==mutate_at)*v^=1;return true;}
static const struct waffle_audio_smmu_io io={regs,rd};
static struct waffle_audio_smmu_inventory out;
static void fixture(bool ex){memset(regs,0,sizeof(regs));reads=fail_at=mutate_at=0;regs[0x20/4]=(1u<<30)|(1u<<27)|(13u<<9)|4|(ex?1u<<8:0);regs[0x24/4]=(6u<<28)|(2u<<16)|8;regs[0x800/4]=0x1801|(ex?0:1u<<31);regs[0xc00/4]=3|(ex?1u<<10:0);regs[(0x80000+4*0x1000)/4]=1;}
int main(void){
 for(unsigned ex=0;ex<2;ex++){
  fixture(ex);assert(waffle_audio_smmu_inventory_read(&io,&out));assert(out.complete && out.s2_banks==2 && out.referenced[3]);assert(!out.candidate[0]&&!out.candidate[1]&&!out.candidate[3]&&!out.candidate[4]);assert(out.candidates==4 && out.candidate[2] && out.candidate[7]);unsigned n=reads;
  for(unsigned i=1;i<=n;i++){fixture(ex);fail_at=i;assert(!waffle_audio_smmu_inventory_read(&io,&out)&&!out.complete&&!out.candidates);}
  for(unsigned i=1;i<=n;i++){fixture(ex);mutate_at=i;assert(!waffle_audio_smmu_inventory_read(&io,&out)&&!out.complete&&!out.candidates);}
 }
 fixture(false);regs[0xc00/4]=8;assert(!waffle_audio_smmu_inventory_read(&io,&out));
 fixture(false);regs[0xc00/4]=3u<<16;assert(!waffle_audio_smmu_inventory_read(&io,&out));
 fixture(false);regs[0xc00/4]=(1u<<16)|255;assert(waffle_audio_smmu_inventory_read(&io,&out)&&!out.referenced[3]&&out.candidate[3]);
 fixture(false);regs[0x24/4]|=9u<<16;assert(!waffle_audio_smmu_inventory_read(&io,&out));
 assert(!waffle_audio_smmu_inventory_read(NULL,&out));assert(!waffle_audio_smmu_inventory_read(&io,NULL));
 puts("PASS audio inventory: all routes/banks, legacy/EXID, stage2 exclusion, enabled orphan exclusion, every read failure/change; read only, no ownership/DMA claim");
}
