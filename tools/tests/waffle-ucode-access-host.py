#!/usr/bin/env python3
"""Actual page mapper: native UCODE AP permissions, readonly and VA/PA bounds."""
from pathlib import Path
import re, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
mapper=source[source.index('#define TABLE_LIMIT'):source.index('/* Change only the high GPU alias,')]
v=ROOT/'work/waffle/gpu/vendor'
kgsl=(v/'kgsl_iommu.c').read_text()
native=re.search(r'static int _iommu_get_protection_flags\(.*?\n\}',kgsl,re.S)[0]
pte=(v/'kernel-drivers-iommu-qcom-io-pgtable-arm.c').read_text()
branch=re.search(r'static arm_lpae_iopte arm_lpae_prot_to_pte\(.*?\n\}',pte,re.S)[0]
needed=set(re.findall(r'ARM_LPAE_[A-Za-z0-9_]+',branch))
constants='\n'.join(line for line in pte.splitlines() if any(re.match(r'#define '+name+r'\s',line) for name in needed))+'\n'
uapi=(v/'msm_kgsl-uapi.h').read_text();kgsl_h=(v/'kgsl.h').read_text()
memflags='\n'.join(re.search(r'^#define '+name+r'\s+[^\n]+',source,re.M)[0] for name,source in (
 ('KGSL_MEMFLAGS_GPUREADONLY',uapi),('KGSL_MEMFLAGS_IOCOHERENT',uapi),
 ('KGSL_MEMDESC_PRIVILEGED',kgsl_h),('KGSL_MEMDESC_UCODE',kgsl_h)))+'\n'
# Execute the full native PTE formatter, including memory/shareability/XN bits.
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include "waffle_gpu_va.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
static uint64_t pages[32][PAGE_SIZE/8];
static unsigned allocated;
static int kmem_alloc(int map,vm_offset_t *out,unsigned size,unsigned flags,int tag) {
 assert(map==7 && size==PAGE_SIZE && flags==7 && tag==5 && allocated<32);
 *out=(uintptr_t)pages[allocated++];memset((void *)*out,0,PAGE_SIZE);return 0;
}
static uint64_t kvtophys(vm_offset_t va) {
 for (unsigned i=0;i<allocated;i++) if (va==(uintptr_t)pages[i]) return 0x90000000u+i*PAGE_SIZE;
 assert(0);return 0;
}
#define IOMMU_READ 1
#define IOMMU_WRITE 2
#define IOMMU_NOEXEC 4
#define IOMMU_PRIV 8
#define IOMMU_CACHE 16
#define BIT(n) (1u<<(n))
#define IOMMU_MMIO 32
#define IOMMU_SYS_CACHE 64
#define IOMMU_SYS_CACHE_NWA 128
#define IO_PGTABLE_QUIRK_ARM_NS 1
struct kgsl_mmu { int unused; };
struct kgsl_memdesc { unsigned flags,priv; };
static int get_llcc_flags(struct kgsl_mmu *mmu) { (void)mmu;return 0; }
typedef uint64_t arm_lpae_iopte;
#define ARM_64_LPAE_S1 1
#define QCOM_ARM_64_LPAE_S1 ARM_64_LPAE_S1
#define ARM_32_LPAE_S1 2
#define ARM_64_LPAE_S2 3
#define ARM_32_LPAE_S2 4
#define ARM_MALI_LPAE 5
struct arm_lpae_io_pgtable { struct { int fmt; struct { unsigned quirks; } cfg; } iop; };
'''+constants+memflags+native+'\n'+branch+'\n'+mapper+r'''
static uint64_t lookup(struct table_pool *pool,uint64_t va) {
 uint64_t *table=(uint64_t *)pool->memory[0];
 for (unsigned level=0;level<2;level++) {
  uint64_t pa=table[(va>>(level?21:30))&511]&PTE_ADDRESS;
  table=NULL;
  for (unsigned i=0;i<pool->count;i++) if(pool->phys[i]==pa) table=(uint64_t *)pool->memory[i];
  assert(table);
 }
 return table[(va>>12)&511];
}
int main(void) {
 struct table_pool pool={0};assert(new_table(&pool));
 struct kgsl_mmu mmu={0};struct arm_lpae_io_pgtable pg={.iop.fmt=ARM_64_LPAE_S1};
 const uint64_t mask=(1ULL<<6)|(1ULL<<7)|(1ULL<<11);
 for (unsigned readonly=0;readonly<2;readonly++) for (unsigned user=0;user<2;user++) {
  struct kgsl_memdesc mem={.flags=readonly?KGSL_MEMFLAGS_GPUREADONLY:0,
      .priv=KGSL_MEMDESC_UCODE|(user?0:KGSL_MEMDESC_PRIVILEGED)};
  int prot=_iommu_get_protection_flags(&mmu,&mem);
  assert(!(prot&IOMMU_NOEXEC));
  uint64_t expected=arm_lpae_prot_to_pte(&pg,prot);
  uint64_t va=0x80010000ULL+(readonly*2+user)*4096;
  assert(map_page_access(&pool,va,0x12345000,readonly,user));
  uint64_t compact=waffle_gpu_compact_alias(va)-WAFFLE_GPU_GLOBAL_BASE;
  assert(map_page_access(&pool,compact,0x12345000,readonly,user));
  assert(lookup(&pool,compact)==lookup(&pool,va));
  uint64_t actual=lookup(&pool,va);
  assert((actual&mask)==(expected&mask) && (actual&PTE_ADDRESS)==0x12345000);
  assert((actual&~PTE_ADDRESS&~3ULL)==expected);
  assert(!(actual&((1ULL<<53)|(1ULL<<54)))); /* Firmware executable. */
 }
 /* Captured native SQE/AQE flags/priv values, rather than synthetic masks. */
 struct kgsl_memdesc captured_ucode={.flags=0x10c0000,.priv=0x282};
 int captured_prot=_iommu_get_protection_flags(&mmu,&captured_ucode);
 assert(!(captured_prot&IOMMU_CACHE) && !(captured_prot&IOMMU_NOEXEC));
 assert(!(captured_prot&IOMMU_WRITE) && !(captured_prot&IOMMU_PRIV));
 assert(arm_lpae_prot_to_pte(&pg,captured_prot)==0xec0);
 assert(map_page(&pool,0x80070000,0x12346000,false));
 assert(!(lookup(&pool,0x80070000)&((1ULL<<6)|(1ULL<<7))));
 assert(!map_page(&pool,1ULL<<39,0x12345000,false));
 assert(!map_page(&pool,0x80070001,0x12345000,false));
 assert(!map_page(&pool,0x80080000,1ULL<<36,false));
 assert(!map_page(&pool,0x80080000,0x12345001,false));
 assert(!map_page(&pool,0x80070000,0x12347000,false));
 const uint64_t gmu_start[]={0x4000,0x100000,0x200000,0x300000};
 const uint64_t gmu_end[]={0x17000,0x11b000,0x213000,0x325000};
 for(unsigned i=0;i<4;i++)for(uint64_t va=gmu_start[i];va<gmu_end[i];va+=4096)
  assert(map_page(&pool,va,0x30000000+va,false));
 for(uint64_t off=0;off<WAFFLE_GPU_COMPACT_POOL_BYTES;off+=4096) {
  uint64_t original=0x61000000+off, alias=waffle_gpu_compact_alias(original)-WAFFLE_GPU_GLOBAL_BASE;
  assert(map_page(&pool,original,0x20000000+off,false));
  assert(map_page(&pool,alias,0x20000000+off,false));
  assert(lookup(&pool,original)==lookup(&pool,alias));
 }
 for(uint64_t off=0;off<0x400000;off+=4096) {
  assert(map_page(&pool,0x100000000ULL+off,0x40000000+off,false));
  assert((lookup(&pool,0x100000000ULL+off)&PTE_ADDRESS)==0x40000000+off);
 }
 assert(pool.count<=TABLE_LIMIT);
 puts("Actual mapper: full native UCODE PTE attributes (AP, nG, AF, SH, cache index, XN/NS), captured flags, privileged data, bounds and conflicting PA checks passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
