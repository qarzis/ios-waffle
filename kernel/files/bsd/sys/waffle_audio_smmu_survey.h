/* Read-only Apps SMMU survey, pinned native arm-smmu.h/arm-smmu.c.
 * DT: 0x15000000, 1 MiB; streams1001(mask80),1061(mask0).
 * Observing a context never grants ownership or permission to replace it. */
#ifndef WAFFLE_AUDIO_SMMU_SURVEY_H
#define WAFFLE_AUDIO_SMMU_SURVEY_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

struct waffle_audio_smmu_io {
 void *context;
 bool (*read32)(void *,uint32_t,uint32_t *);
};
struct waffle_audio_smmu_match {
 uint32_t sid,matches,index,smr,s2cr,cb,cbar,sctlr,tcr,tcr2,fsr;
 uint64_t ttbr0,ttbr1,far;
 bool translated,context_read;
};
struct waffle_audio_smmu_snapshot {
 uint32_t id0,id1,id2,page_shift,groups,banks,cb_base;
 bool exids,complete;
 struct waffle_audio_smmu_match stream[3];
};
static inline bool waffle_audio_smmu_read(const struct waffle_audio_smmu_io *io,
 uint32_t offset,uint32_t *value)
{
 return io && io->read32 && value && !(offset&3) && offset<=0xffffc &&
     io->read32(io->context,offset,value);
}
static inline bool waffle_audio_smmu_read64(const struct waffle_audio_smmu_io *io,
 uint32_t offset,uint64_t *value)
{
 uint32_t low,high;
 if(!waffle_audio_smmu_read(io,offset,&low) ||
    !waffle_audio_smmu_read(io,offset+4,&high))return false;
 *value=(uint64_t)high<<32|low;return true;
}
static inline bool waffle_audio_smmu_survey(const struct waffle_audio_smmu_io *io,
 struct waffle_audio_smmu_snapshot *out)
{
 if(!io || !io->read32 || !out)return false;
 *out=(struct waffle_audio_smmu_snapshot){0};
 out->stream[0].sid=0x1001;out->stream[1].sid=0x1081;out->stream[2].sid=0x1061;
 if(!waffle_audio_smmu_read(io,0x20,&out->id0) ||
    !waffle_audio_smmu_read(io,0x24,&out->id1) ||
    !waffle_audio_smmu_read(io,0x28,&out->id2))return false;
 /* This survey only understands stage1-capable stream-matching SMMUv2. */
 if(!(out->id0&(1u<<30)) || !(out->id0&(1u<<27)))return false;
 out->exids=(out->id0&(1u<<8))!=0;
 out->groups=out->id0&255;out->banks=out->id1&255;
 out->page_shift=(out->id1>>31)?16:12;
 out->cb_base=(1u<<(((out->id1>>28)&7)+1))<<out->page_shift;
 if(!out->groups || !out->banks || out->cb_base>0x100000 ||
    ((uint64_t)out->cb_base+((uint64_t)out->banks<<out->page_shift))>0x100000)return false;
 uint32_t sid_mask=out->exids?0xffff:((1u<<((out->id0>>9)&15))-1);
 if((0x1081u&~sid_mask) || (0x1061u&~sid_mask))return false;
 for(uint32_t i=0;i<out->groups;i++) {
  uint32_t smr,s2cr;
  if(!waffle_audio_smmu_read(io,0x800+4*i,&smr) ||
     !waffle_audio_smmu_read(io,0xc00+4*i,&s2cr))return false;
  if(!(out->exids?(s2cr&(1u<<10)):(smr&(1u<<31))))continue;
  uint32_t id=smr&sid_mask,mask=(smr>>16)&sid_mask;
  for(unsigned j=0;j<3;j++) {
   struct waffle_audio_smmu_match *m=&out->stream[j];
   if((m->sid^id)&~mask)continue;
   if(++m->matches!=1) {m->context_read=false;continue;}
   m->index=i;m->smr=smr;m->s2cr=s2cr;m->cb=s2cr&255;
   m->translated=((s2cr>>16)&3)==0;
   if(!m->translated)continue;
   if(m->cb>=out->banks)return false;
   uint32_t base=out->cb_base+(m->cb<<out->page_shift);
   if(!waffle_audio_smmu_read(io,(1u<<out->page_shift)+4*m->cb,&m->cbar) ||
      !waffle_audio_smmu_read(io,base,&m->sctlr) ||
      !waffle_audio_smmu_read(io,base+0x10,&m->tcr2) ||
      !waffle_audio_smmu_read64(io,base+0x20,&m->ttbr0) ||
      !waffle_audio_smmu_read64(io,base+0x28,&m->ttbr1) ||
      !waffle_audio_smmu_read(io,base+0x30,&m->tcr) ||
      !waffle_audio_smmu_read(io,base+0x58,&m->fsr) ||
      !waffle_audio_smmu_read64(io,base+0x60,&m->far))return false;
   uint32_t after_smr,after_s2cr;
   if(!waffle_audio_smmu_read(io,0x800+4*i,&after_smr) ||
      !waffle_audio_smmu_read(io,0xc00+4*i,&after_s2cr) ||
      after_smr!=smr || after_s2cr!=s2cr)return false;
   m->context_read=true;
  }
 }
 out->complete=true;return true;
}
#endif
