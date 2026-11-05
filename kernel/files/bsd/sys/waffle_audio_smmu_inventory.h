/* Read-only inherited Apps SMMUv2 inventory. A candidate is NOT ownership.
 * Native arm-smmu.h: ID1.NUMS2CB[23:16], S2CR.TYPE[17:16], SCTLR.M[0].
 * Caller supplies storage; no allocation, writes, TLB or reset operations. */
#ifndef WAFFLE_AUDIO_SMMU_INVENTORY_H
#define WAFFLE_AUDIO_SMMU_INVENTORY_H
#include "waffle_audio_smmu_survey.h"
struct waffle_audio_smmu_inventory {
 uint32_t id0,id1,id2,groups,banks,s2_banks,page_shift,cb_base;
 uint32_t smr[256],s2cr[256],sctlr[256];
 bool referenced[256],candidate[256],complete;
 uint32_t candidates;
};
static inline bool waffle_audio_smmu_inventory_read(
 const struct waffle_audio_smmu_io *io,struct waffle_audio_smmu_inventory *out)
{
 if(!out)return false;
 *out=(struct waffle_audio_smmu_inventory){0};
 if(!waffle_audio_smmu_read(io,0x20,&out->id0) ||
    !waffle_audio_smmu_read(io,0x24,&out->id1) ||
    !waffle_audio_smmu_read(io,0x28,&out->id2))return false;
 if(!(out->id0&(1u<<30)) || !(out->id0&(1u<<27)))return false;
 out->groups=out->id0&255;out->banks=out->id1&255;
 out->s2_banks=(out->id1>>16)&255;
 out->page_shift=(out->id1>>31)?16:12;
 out->cb_base=(1u<<(((out->id1>>28)&7)+1))<<out->page_shift;
 if(!out->groups || !out->banks || out->s2_banks>out->banks ||
    out->cb_base>0x100000 ||
    (uint64_t)out->cb_base+((uint64_t)out->banks<<out->page_shift)>0x100000)return false;
 bool exids=(out->id0&(1u<<8))!=0;
 for(uint32_t i=0;i<out->groups;i++) {
  if(!waffle_audio_smmu_read(io,0x800+4*i,&out->smr[i]) ||
     !waffle_audio_smmu_read(io,0xc00+4*i,&out->s2cr[i]))return false;
  bool valid=exids?(out->s2cr[i]&(1u<<10)):(out->smr[i]&(1u<<31));
  if(!valid)continue;
  uint32_t type=(out->s2cr[i]>>16)&3;
  if(type==3)return false; /* Reserved encoding: no candidate conclusion. */
  if(type!=0)continue; /* Bypass/fault routes do not select a context. */
  uint32_t cb=out->s2cr[i]&255;
  if(cb>=out->banks)return false;
  out->referenced[cb]=true;
 }
 for(uint32_t cb=0;cb<out->banks;cb++)
  if(!waffle_audio_smmu_read(io,out->cb_base+(cb<<out->page_shift),&out->sctlr[cb]))return false;
 /* A second pass detects observed changes; not an atomic ownership claim. */
 for(uint32_t i=0;i<out->groups;i++) {
  uint32_t a,b;
  if(!waffle_audio_smmu_read(io,0x800+4*i,&a) ||
     !waffle_audio_smmu_read(io,0xc00+4*i,&b) ||
     a!=out->smr[i] || b!=out->s2cr[i])return false;
 }
 for(uint32_t cb=0;cb<out->banks;cb++) {
  uint32_t v;
  if(!waffle_audio_smmu_read(io,out->cb_base+(cb<<out->page_shift),&v) || v!=out->sctlr[cb])return false;
 }
 for(uint32_t offset=0x20;offset<=0x28;offset+=4) {
  uint32_t v,expected=offset==0x20?out->id0:offset==0x24?out->id1:out->id2;
  if(!waffle_audio_smmu_read(io,offset,&v) || v!=expected)return false;
 }
 for(uint32_t cb=out->s2_banks;cb<out->banks;cb++)
  if(!out->referenced[cb] && !(out->sctlr[cb]&1)) {
   out->candidate[cb]=true;out->candidates++;
  }
 out->complete=true;return true;
}
#endif
