#ifndef WAFFLE_DISPLAY_SMMU_H
#define WAFFLE_DISPLAY_SMMU_H
#include <stdint.h>
#include <stdbool.h>
/* Read-only Apps SMMUv2, native arm-smmu.h and live display DT.
 * Stream IDs 1c00/1c02 are the nonsecure master (ignore mask2).
 * Raw observations do not establish permission to modify a context bank. */
struct waffle_display_smmu_io {void *context;bool (*read32)(void *,uint32_t,uint32_t *);};
struct waffle_display_smmu_route {
 uint32_t sid,matches,index,smr,s2cr,cb,cbar,sctlr,tcr,tcr2,fsr;
 uint64_t ttbr0,ttbr1;
 bool context_read;
};
struct waffle_display_smmu_snapshot {
 uint32_t cr0,id0,id1,id2,groups,banks,page_shift,cb_base;
 bool exids,complete;
 struct waffle_display_smmu_route stream[2];
};
static inline bool waffle_display_smmu_read(const struct waffle_display_smmu_io *io,uint32_t off,uint32_t *v)
{return io && io->read32 && v && !(off&3) && off<=0xffffc && io->read32(io->context,off,v);}
static inline bool waffle_display_smmu_read64(const struct waffle_display_smmu_io *io,uint32_t off,uint64_t *v)
{
 for(unsigned i=0;i<3;i++){
  uint32_t high,low,after;
  if(!waffle_display_smmu_read(io,off+4,&high) || !waffle_display_smmu_read(io,off,&low) || !waffle_display_smmu_read(io,off+4,&after))return false;
  if(high==after){*v=((uint64_t)high<<32)|low;return true;}
 }
 return false;
}
static inline bool waffle_display_smmu_capture(const struct waffle_display_smmu_io *io,struct waffle_display_smmu_snapshot *o)
{
 if(!o)return false;
 *o=(struct waffle_display_smmu_snapshot){0};o->stream[0].sid=0x1c00;o->stream[1].sid=0x1c02;
 if(!waffle_display_smmu_read(io,0,&o->cr0) || !waffle_display_smmu_read(io,0x20,&o->id0) ||
    !waffle_display_smmu_read(io,0x24,&o->id1) || !waffle_display_smmu_read(io,0x28,&o->id2))return false;
 if(!(o->id0&(1u<<30)) || !(o->id0&(1u<<27)))return false;
 o->exids=(o->id0&(1u<<8))!=0;o->groups=o->id0&255;o->banks=o->id1&255;
 o->page_shift=(o->id1>>31)?16:12;o->cb_base=(1u<<(((o->id1>>28)&7)+1))<<o->page_shift;
 if(!o->groups || !o->banks || (uint64_t)o->cb_base+((uint64_t)o->banks<<o->page_shift)>0x100000)return false;
 uint32_t mask=o->exids?0xffff:((1u<<((o->id0>>9)&15))-1);
 if(0x1c02u&~mask)return false;
 for(unsigned i=0;i<o->groups;i++){
  uint32_t smr,s2cr;
  if(!waffle_display_smmu_read(io,0x800+4*i,&smr) || !waffle_display_smmu_read(io,0xc00+4*i,&s2cr))return false;
  if(!(o->exids?(s2cr&(1u<<10)):(smr&(1u<<31))))continue;
  for(unsigned j=0;j<2;j++){
   struct waffle_display_smmu_route *r=&o->stream[j];
   if((r->sid^(smr&mask))&~((smr>>16)&mask))continue;
   if(++r->matches!=1){r->context_read=false;continue;}
   r->index=i;r->smr=smr;r->s2cr=s2cr;r->cb=s2cr&255;
   if(((s2cr>>16)&3)!=0)continue; /* Bypass/fault: no context read. */
   if(r->cb>=o->banks)return false;
   uint32_t cb=o->cb_base+(r->cb<<o->page_shift);
   if(!waffle_display_smmu_read(io,(1u<<o->page_shift)+4*r->cb,&r->cbar) ||
      !waffle_display_smmu_read(io,cb,&r->sctlr) || !waffle_display_smmu_read(io,cb+0x10,&r->tcr2) ||
      !waffle_display_smmu_read64(io,cb+0x20,&r->ttbr0) || !waffle_display_smmu_read64(io,cb+0x28,&r->ttbr1) ||
      !waffle_display_smmu_read(io,cb+0x30,&r->tcr) || !waffle_display_smmu_read(io,cb+0x58,&r->fsr))return false;
   uint32_t after_smr,after_s2cr;
   if(!waffle_display_smmu_read(io,0x800+4*i,&after_smr) || !waffle_display_smmu_read(io,0xc00+4*i,&after_s2cr) ||
      after_smr!=smr || after_s2cr!=s2cr)return false;
   r->context_read=true;
  }
 }
 o->complete=true;return true;
}
#endif
