/* Native observed S1 table-register profile, DISABLED bank only.
 * Does not enable translation, bind a SID, issue ATOS/TLB, or start DSP.
 * All eight table/config words must be restored and read back before release. */
#ifndef WAFFLE_AUDIO_CB_CONFIG_H
#define WAFFLE_AUDIO_CB_CONFIG_H
#include "waffle_audio_cb_access.h"
#include "waffle_audio_page_tables.h"
struct waffle_audio_cb_config_result {
 bool admitted,configured,restored,passed;
 uint32_t bank,base,saved[8],target[8],actual[8],read_mask,mismatch_mask;
 unsigned writes;
};
static inline uint32_t waffle_audio_cb_config_offset(unsigned n)
{
 const uint32_t offsets[]={0x10,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c};
 return n<8?offsets[n]:0xffffffff;
}
static inline bool waffle_audio_cb_config(const struct waffle_audio_cb_access_io *io,
 const struct waffle_audio_cb_access_result *access,uint64_t root_pa,
 struct waffle_audio_cb_config_result *r)
{
 if(!r)return false;
 *r=(struct waffle_audio_cb_config_result){0};
 if(!io || !io->isolated || !io->write32 || !access || !access->passed ||
    !access->restored || (access->original&1) || access->bank>=71 ||
    access->offset!=0x80000+access->bank*4096 || !waffle_audio_table_pa(root_pa))return false;
 r->bank=access->bank;r->base=access->offset;
 uint32_t cbar,cba2r;
 if(!waffle_audio_smmu_read(&io->read,0x1000+4*r->bank,&cbar) ||
    !waffle_audio_smmu_read(&io->read,0x1800+4*r->bank,&cba2r) ||
    ((cbar>>16)&3)!=1 || !(cba2r&1))return false;

 uint32_t sctlr;
 if(!waffle_audio_smmu_read(&io->read,r->base,&sctlr) || sctlr!=access->original)return false;
 for(unsigned n=0;n<8;n++)if(!waffle_audio_smmu_read(&io->read,r->base+waffle_audio_cb_config_offset(n),&r->saved[n]))return false;
 uint64_t ttbr=root_pa|((uint64_t)r->bank<<48);
 const uint32_t values[]={0x38011,(uint32_t)ttbr,(uint32_t)(ttbr>>32),0,r->bank<<16,0x80351c,0xf404ff44,0xefe4};
 for(unsigned n=0;n<8;n++)r->target[n]=values[n];
 r->admitted=true;bool ok=true;unsigned dirty=0;
 for(unsigned n=0;n<8;n++){
  dirty=n+1;r->writes++;
  if(!io->write32(io->read.context,r->base+waffle_audio_cb_config_offset(n),r->target[n])){ok=false;break;}
 }
 for(unsigned n=0;n<8;n++){
  uint32_t value=0;
  bool read=waffle_audio_smmu_read(&io->read,r->base+waffle_audio_cb_config_offset(n),&value);
  r->actual[n]=value;if(read)r->read_mask|=1u<<n;
  if(!read || value!=r->target[n]){r->mismatch_mask|=1u<<n;ok=false;}
 }
 r->configured=ok;
 bool restored=true;
 while(dirty){unsigned n=--dirty;r->writes++;bool done=io->write32(io->read.context,r->base+waffle_audio_cb_config_offset(n),r->saved[n]);restored=restored&&done;}
 for(unsigned n=0;n<8;n++){
  uint32_t value;bool same=waffle_audio_smmu_read(&io->read,r->base+waffle_audio_cb_config_offset(n),&value)&&value==r->saved[n];restored=restored&&same;
 }
 bool disabled=waffle_audio_smmu_read(&io->read,r->base,&sctlr)&&sctlr==access->original;
 r->restored=restored&&disabled;r->passed=r->configured&&r->restored;return r->passed;
}
#endif
