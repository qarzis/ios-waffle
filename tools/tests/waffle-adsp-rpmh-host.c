#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_adsp_rpmh.h"

static uint32_t regs[0x10000/4], original[0x10000/4];
static unsigned writes, polls, triggers, failure, expected_count;
static bool locked;
static uint32_t read_reg(void *unused, unsigned offset)
{
 (void)unused; assert(offset < sizeof(regs) && !(offset & 3));
 return regs[offset/4];
}
static void write_reg(void *unused, unsigned offset, uint32_t value)
{
 (void)unused; assert(locked); writes++;
 bool allowed = offset==0xd00 || offset==0xd08 || offset==0xd20 || offset==0xd24 || offset==0xd2c;
 for (unsigned i=0;i<expected_count;i++)
  allowed |= offset==0xd34+i*24 || offset==0xd38+i*24 || offset==0xd3c+i*24;
 assert(allowed);
 regs[offset/4]=value;
 if (offset==0xd08) { assert(value==1); regs[0xd04/4]&=~1u; }
 if (offset==0xd24 && (value & (1u<<24))) {
  triggers++;
  unsigned wait=expected_count==8?0xf5:7;
  assert(regs[0xd20/4]==wait);
  assert(regs[0xd2c/4]==(1u<<expected_count)-1);
  for (unsigned i=0;i<expected_count;i++) {
   assert(regs[(0xd34+i*24)/4]==0x10108);
   regs[(0xd40+i*24)/4]=0x100 | ((wait & (1u<<i))?0x10000:0);
  }
  if (failure==2) regs[0xd40/4]=0x100;
  if (failure==3) regs[0xd58/4]=0;
  if (failure!=1) regs[0xd04/4]|=1;
  if (failure==1 || failure==4) regs[0xd28/4]=0;
 }
}
static void pause_poll(void *unused) { (void)unused; polls++; }
static void reset(unsigned count)
{
 memset(regs,0,sizeof(regs)); writes=polls=triggers=failure=0; expected_count=count;locked=true;
 regs[0]=3u<<16;regs[3]=(3u<<12)|(16u<<27);
 for(unsigned i=0;i<3;i++) regs[(0xd28+i*672)/4]=1;
 regs[0xd00/4]=0x6;regs[0xd20/4]=0x55;regs[0xd24/4]=(1u<<24)|(1u<<16);regs[0xd2c/4]=0x100;
 for(unsigned i=0;i<count;i++) for(unsigned j=0;j<3;j++) regs[(0xd34+i*24+j*4)/4]=0xab000+i*3+j;
 memcpy(original,regs,sizeof(regs));original[0xd24/4]&=~(1u<<24);
}
static void restored(void)
{
 const unsigned fixed[]={0xd00,0xd20,0xd24,0xd2c};
 for(unsigned i=0;i<4;i++) assert(regs[fixed[i]/4]==original[fixed[i]/4]);
 for(unsigned i=0;i<expected_count;i++) for(unsigned j=0;j<3;j++)
  assert(regs[(0xd34+i*24+j*4)/4]==original[(0xd34+i*24+j*4)/4]);
 assert(!(regs[0xd04/4]&1));
}
int main(void)
{
 uint32_t bcm_addr[]={0x50000,0x50004,0x50008,0x50010,0x5001c,0x50034,0x50050,0x50068};
 uint32_t bcm_data[]={0x6fffffff,0x2fffffff,0x60000001,0x2fffffff,0x6fffffff,0x6fffffff,0x6fffffff,0x60000003};
 uint32_t arc_addr[]={0x30030,0x30040,0x300d0},arc_data[]={7,4,3};
 struct waffle_adsp_rpmh_io io;
#define RESET(n) do { reset(n);io=(struct waffle_adsp_rpmh_io){.read=read_reg,.write=write_reg,.pause=pause_poll}; } while(0)
 RESET(8);assert(waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5)==1);assert(triggers==1);restored();
 RESET(3);assert(waffle_adsp_rpmh_batch(&io,arc_addr,arc_data,3,7)==1);assert(triggers==1);restored();
 for(unsigned version=3;version<=4;version++) { RESET(8);regs[0]=version<<16;assert(waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5)==1); }
 RESET(8);regs[0]=2u<<16;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes);
 RESET(8);regs[3]=(3u<<12)|(3u<<27);assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes);
 for(unsigned i=0;i<3;i++) { RESET(8);regs[(0xd28+i*672)/4]=0;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes); }
 RESET(8);regs[0xd04/4]=1;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes);
 RESET(8);bcm_data[7]=0x60000001;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes);bcm_data[7]=0x60000003;
 assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xff) && !writes);
 bcm_addr[4]=0x50018;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && !writes);bcm_addr[4]=0x5001c;
 RESET(8);failure=1;assert(waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5)==-2);assert(polls==2000 && io.failed && triggers==1);
 unsigned before=writes;assert(!waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5) && writes==before);
 RESET(8);failure=4;assert(waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5)==-2 && polls==2000);
 for(unsigned f=2;f<=3;f++) { RESET(8);failure=f;assert(waffle_adsp_rpmh_batch(&io,bcm_addr,bcm_data,8,0xf5)==-1 && io.failed);restored(); }
 puts("PASS: actual ADSP RPMh transaction: native masks, strict whitelist, idle/pending guards, command status checks, register restoration, bounded timeout and no retry after fault; mocked MMIO only");
}
