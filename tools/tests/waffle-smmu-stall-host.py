#!/usr/bin/env python3
"""Compare actual diagnostic SCTLR policy with native GPUHALT stall path."""
from pathlib import Path
import re,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
code=s[s.index('static bool diagnostic_context_stall('):s.index('/* Independent GPU user stream')]
native=(ROOT/'work/waffle/gpu/vendor/kgsl_iommu.c').read_text()
native=re.search(r'static void kgsl_iommu_configure_gpu_sctlr\(.*?\n\}',native,re.S)[0]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
typedef uintptr_t vm_offset_t;
typedef uint32_t u32;
#define FSR_FAULT_MASK 0xc00001feu
static uint32_t sctlr,fsr,native_sctlr;
static unsigned writes;
static bool drop_write;
static uint32_t r32(vm_offset_t cb,unsigned off) {assert(cb==1);assert(off==0 || off==0x58);return off?fsr:sctlr;}
static void w32(vm_offset_t cb,unsigned off,uint32_t v) {assert(cb==1 && !off);++writes;if(!drop_write)sctlr=v;}
static void log_line(const char *fmt,...) {(void)fmt;}
#define KGSL_IOMMU_SCTLR_CFCFG_SHIFT 7
#define KGSL_IOMMU_SCTLR_HUPCF_SHIFT 8
#define KGSL_FT_PAGEFAULT_GPUHALT_ENABLE 0
#define KGSL_MMU_PAGEFAULT_TERMINATE 0
#define KGSL_IOMMU_CTX_SCTLR 0
struct kgsl_mmu {unsigned long features;};
struct kgsl_iommu_context {unsigned dummy;};
#define KGSL_IOMMU_GET_CTX_REG(ctx,off) ((void)(ctx),(void)(off),native_sctlr)
#define KGSL_IOMMU_SET_CTX_REG(ctx,off,v) ((void)(ctx),(void)(off),native_sctlr=(v))
static bool test_bit(unsigned bit,const unsigned long *v) {return (*v>>bit)&1;}
'''
tests=r'''
int main(void) {
 struct kgsl_mmu mmu={0};struct kgsl_iommu_context ctx={0};
 uint32_t continue_cases[]={0x27,0x127,0xa7,0x1a7,0xc00027};
 for(unsigned i=0;i<5;i++) {
  sctlr=native_sctlr=continue_cases[i];fsr=0x400;writes=0;drop_write=false;
  kgsl_iommu_configure_gpu_sctlr(&mmu,0,&ctx);
  assert(gpu_context_fault_continue(1) && writes==1 && sctlr==native_sctlr);
  assert((sctlr&(1u<<8)) && !(sctlr&((1u<<6)|(1u<<7))));
 }
 sctlr=0;writes=0;fsr=0;assert(!gpu_context_fault_continue(1) && !writes);
 sctlr=0x67;assert(!gpu_context_fault_continue(1) && !writes);
 sctlr=0x27;fsr=8;assert(!gpu_context_fault_continue(1) && !writes);
 fsr=0;drop_write=true;assert(!gpu_context_fault_continue(1) && writes==1);
 drop_write=false;
 uint32_t cases[]={0x1027,0x1127,0x10a7,0x11a7};
 for(unsigned i=0;i<4;i++) {
  sctlr=native_sctlr=cases[i];fsr=0x400;writes=0;drop_write=false;
  kgsl_iommu_configure_gpu_sctlr(&mmu,1,&ctx);
  assert(diagnostic_context_stall(1) && writes==1 && sctlr==native_sctlr);
  assert((sctlr&(1u<<7)) && !(sctlr&((1u<<6)|(1u<<8))));
 }
 sctlr=0x1027;fsr=0x408;writes=0;assert(!diagnostic_context_stall(1) && !writes);
 sctlr=0x1067;fsr=0;assert(!diagnostic_context_stall(1) && !writes);
 sctlr=0x1026;assert(!diagnostic_context_stall(1) && !writes);
 sctlr=0x1027;drop_write=true;assert(!diagnostic_context_stall(1) && sctlr==0x1027 && writes==1);
 puts("Actual SMMU stall policy matches native GPUHALT, preserves IRQ mask, refuses faults/disabled bank/readback failure");
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(harness+native+code+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
