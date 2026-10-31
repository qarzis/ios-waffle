#!/usr/bin/env python3
"""Actual GPU context code: ownership refusal, failed setup and TLB rollback."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
code=s[s.index('struct gpu_context {'):s.index('\nstatic bool gpu_secure_context_probe(')]
pte=s[s.index("#define PTE_ADDRESS "):].splitlines()[0]+"\n"
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
typedef uintptr_t vm_offset_t;
#define bzero(p,n) memset(p,0,n)
#define FSR_FAULT_MASK 0xc00001feu
#define BIT(n) (1u<<(n))
#define GENMASK(h,l) ((0xffffffffu>>(31-(h)))& (0xffffffffu<<(l)))
#define FIELD_PREP(mask,value) (((uint32_t)(value)<<__builtin_ctz(mask))&(mask))
#define IO_PGTABLE_QUIRK_ARM_TTBR1 BIT(5)
struct io_pgtable_cfg {unsigned quirks;struct {struct {unsigned tg,sh,orgn,irgn,tsz;} tcr;} arm_lpae_s1_cfg;};
static uint32_t memory[0x40000/4];
static unsigned writes,sync_calls,fail_sync,drop_route;
static uint32_t r32(vm_offset_t base,unsigned off) {return *(uint32_t *)(base+off);}
static uint64_t r64(vm_offset_t base,unsigned off) {return *(uint64_t *)(base+off);}
static void w32(vm_offset_t base,unsigned off,uint32_t value) {
    uintptr_t absolute=base+off-(uintptr_t)memory;
    assert(absolute<sizeof(memory));writes++;
    if (absolute==0x1000 || absolute==0x1008) assert(((value>>16)&3)!=0); /* never restore unsupported stage2 */
    if ((absolute==0x800 || absolute==0x808) && (value>>31) && drop_route) {drop_route=0;return;}
    if (absolute==0x20058) *(uint32_t *)(base+off)&=~value;
    else *(uint32_t *)(base+off)=value;
}
static void w64(vm_offset_t base,unsigned off,uint64_t value) {
    assert(base+off-(uintptr_t)memory<sizeof(memory)-7);writes++;
    *(uint64_t *)(base+off)=value;
}
static bool tlb_sync(vm_offset_t cb) {assert(cb==(uintptr_t)memory+0x20000 || cb==(uintptr_t)memory+0x22000);sync_calls++;return sync_calls!=fail_sync;}
static void log_line(const char *fmt,...) {(void)fmt;}
'''
native_header=(ROOT/'work/waffle/gpu/vendor/arm-smmu.h').read_text()
import re
native_constants='\n'.join(line for line in native_header.splitlines() if re.match(r'#define ARM_SMMU_TCR_(?:TG0|SH0|ORGN0|IRGN0|T0SZ|A1|EPD0|EPD1)\s',line))+'\n'
granules=(ROOT/'work/waffle/gpu/vendor/kernel-drivers-iommu-io-pgtable-arm.h').read_text()
native_constants+='\n'.join(line for line in granules.splitlines() if re.match(r'#define ARM_LPAE_TCR_TG[01]_4K\s',line))+'\n'
native=native_header[native_header.index('static inline u32 arm_smmu_lpae_tcr('):native_header.index('static inline u32 arm_smmu_lpae_tcr2(')].replace('u32','uint32_t')
tests=r''' 
static void reset(void) {
    memset(memory,0,sizeof(memory));writes=sync_calls=fail_sync=drop_route=0;
    memory[0xc00/4]=0x20000; /* unused/fault stream0 */
    memory[0x804/4]=(1u<<31)|5;memory[0xc04/4]=1; /* working GMU route */
    memory[0x20058/4]=0x400; /* reserved bit is NOT a fault */
}
static bool begin(struct gpu_context *g) {
    return gpu_context_begin(g,(uintptr_t)memory,4096,32,22,24,0x12345000);
}
static void restored(void) {
    assert(memory[0x800/4]==0 && memory[0xc00/4]==0x20000 && memory[0x20000/4]==0);
    assert(memory[0x1000/4]==0x10000 && memory[0x1800/4]==0);
    assert(memory[0x804/4]==((1u<<31)|5) && memory[0xc04/4]==1);
    for (unsigned i=0;i<9;i++) assert(memory[(0x20000+gpu_cb_offsets[i])/4]==0);
}
int main(void) {
    struct gpu_context g;
    reset();memory[0x20000/4]=1;assert(!begin(&g) && !writes);
    reset();memory[0x20058/4]|=8;assert(!begin(&g) && !writes);
    reset();memory[0x808/4]=(1u<<31);assert(!begin(&g) && !writes);
    reset();memory[0x808/4]=(1u<<31)|7;memory[0xc08/4]=0;assert(!begin(&g) && !writes);
    reset();assert(begin(&g));assert(r64(g.cb,0x20)==(0x12345000|(1ULL<<48)));
    assert(gpu_context_end(&g));restored();
    reset();fail_sync=1;assert(!begin(&g));assert(gpu_context_end(&g));restored();
    reset();drop_route=1;assert(!begin(&g));assert(gpu_context_end(&g));restored();
    reset();assert(begin(&g));fail_sync=2;assert(!gpu_context_end(&g));restored();
    reset();memory[0x800/4]=(1u<<31);memory[0xc00/4]=0;memory[0x20000/4]=1;
    assert(gpu_context_begin_at(&g,(uintptr_t)memory,4096,32,22,24,0x23456000,2,2,2));
    assert(r64(g.cb,0x20)==(0x23456000|(3ULL<<48)) && memory[0xc08/4]==2);
    assert(gpu_context_end(&g));
    assert(memory[0x800/4]==(1u<<31) && memory[0x20000/4]==1 && memory[0x808/4]==0);
    reset();memory[0x22000/4]=1;
    assert(!gpu_context_begin_at(&g,(uintptr_t)memory,4096,32,22,24,0x23456000,2,2,2) && !writes);
    reset();memory[0x810/4]=(1u<<31)|2;memory[0xc10/4]=4;
    assert(!gpu_context_begin_at(&g,(uintptr_t)memory,4096,32,22,24,0x23456000,2,2,2) && !writes);
    reset();assert(begin(&g));
    assert(gpu_context_split(&g));
    struct io_pgtable_cfg cfg={.arm_lpae_s1_cfg.tcr={0,3,1,1,25}};
    uint32_t native_low=arm_smmu_lpae_tcr(&cfg);
    cfg.quirks=IO_PGTABLE_QUIRK_ARM_TTBR1;
    cfg.arm_lpae_s1_cfg.tcr.tg=ARM_LPAE_TCR_TG1_4K; /* qcom allocator changes encoding for TTBR1. */
    uint32_t native_split=(native_low|arm_smmu_lpae_tcr(&cfg))&~(ARM_SMMU_TCR_EPD0|ARM_SMMU_TCR_EPD1);
    assert(r32(g.cb,0x30)==native_split && native_split==0xb5193519);
    assert(r64(g.cb,0x28)==r64(g.cb,0x20));
    assert(gpu_context_end(&g));restored();
    reset();assert(begin(&g));fail_sync=2;
    assert(!gpu_context_split(&g));assert(gpu_context_end(&g));restored();
    reset();assert(begin(&g));unsigned before=writes;
    g.bank=2;assert(!gpu_context_split(&g) && writes==before);g.bank=0;
    uint32_t original_tcr=memory[0x20030/4];
    for(unsigned tg=1;tg<4;tg++) {
        memory[0x20030/4]=original_tcr|(tg<<14);
        assert(!gpu_context_split(&g) && writes==before);
    }
    memory[0x20030/4]=original_tcr;
    memory[0x20058/4]=8;assert(!gpu_context_split(&g) && writes==before);memory[0x20058/4]=0;
    memory[0x20028/4]=1;assert(!gpu_context_split(&g) && writes==before);memory[0x20028/4]=0;
    assert(gpu_context_end(&g));restored();
    puts("GPU context ownership/setup/rollback/TLB-timeout/SID2-isolation and actual native split TCR checks passed");return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+pte+native_constants+native+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
