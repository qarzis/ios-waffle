#!/usr/bin/env python3
"""Execute real ECATS/matrix code against native encoding and faulting MMIO mocks."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'kernel/files/bsd/dev/waffle_smmu.c').read_text()
code = source[source.index('enum ecats_access'):source.index('/* Diagnostic only: native GPUHALT')]
native = (ROOT / 'work/waffle/gpu/vendor/arm-smmu-qcom.c').read_text()
start = native.index('static phys_addr_t qtb500_trigger_atos(')
native = native[start:]
encoding = native[native.index('\tinfld0 = FIELD_PREP'):native.index('\n\tinfld2 = iova;')]
reference = '''static void native_encode(unsigned sid,unsigned long trans_flags,uint64_t *a,uint64_t *b) {
uint64_t infld0,infld1;
''' + encoding + '\n*a=infld0;*b=infld1;\n}\n'
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#define FSR_FAULT_MASK 0xc00001feu
#define NSEC_PER_USEC 1
#define WAFFLE_GMU_SYSRESET 0x500
#define WAFFLE_GPU_GX_GDSCR 0x600
#define WAFFLE_GPU_SQE_ADDRESS 0x80010000u
#define WAFFLE_GPU_AQE_ADDRESS 0x80030000u
#define WAFFLE_GPU_PWRUP_ADDRESS 0x80070000u
#define WAFFLE_HWSCHED_POOL_ADDRESS 0x61000000u
#define BASE 0x1ff8000000000ULL
#define IOMMU_TRANS_SEC 1
#define IOMMU_TRANS_PRIV 2
#define IOMMU_TRANS_INST 4
#define IOMMU_TRANS_WRITE 8
#define BIT(x) (1ULL<<(x))
#define GENMASK(h,l) ((~0ULL>>(63-(h)))&(~0ULL<<(l)))
#define FIELD_PREP(m,v) (((uint64_t)(v)<<__builtin_ctzll(m))&(m))
'''
# Use the vendor's masks, not a second copy of port bit positions.
for line in (ROOT / 'work/waffle/gpu/vendor/arm-smmu-qcom.c').read_text().splitlines():
    if re.match(r'#define QTB_OVR_ECATS_INFLD[01]_', line):
        harness += line + '\n'
harness += r'''
struct pool_permission_context {void *tables;vm_offset_t cb;};
struct waffle_gmu_region {uint32_t address,size;vm_offset_t memory;bool gpu_only,readonly;};
struct waffle_gmu_plan {unsigned count;struct waffle_gmu_region regions[16];};
static uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *p,uint64_t a) {
 (void)p;return a>=0x80000000?BASE+0x400000+a-0x80000000:BASE+0x500000+a-0x61000000;
}
static struct waffle_gmu_plan plan;
static unsigned transfers,failed_at,permission_calls;
static uint64_t in0,in1,in2,trigger,override_pa;
static uint32_t fsr;
static bool ready=true,timeout,wrong_pa,permission_ok=true;
static unsigned seen[128];
static uint64_t kvtophys(vm_offset_t p) {return p+0x10000000;}
static uint64_t result_pa(void) {
 if(override_pa)return override_pa;
 for(unsigned i=0;i<plan.count;i++) {
  struct waffle_gmu_region *r=&plan.regions[i];uint64_t va=waffle_gpu_plan_alias(&plan,r->address);
  if(in2>=va && in2-va<r->size)return kvtophys(r->memory+in2-va);
 }
 assert(0);return 0;
}
static uint32_t r32(vm_offset_t b,unsigned o) {
 if(o==0x58)return fsr;
 if(o==WAFFLE_GMU_SYSRESET || o==WAFFLE_GPU_GX_GDSCR)return ready;
 (void)b;assert(0);return 0;
}
static uint64_t r64(vm_offset_t b,unsigned o) {
 (void)b;
 if(o==0x410 || o==0x418)return ready;
 if(o==0x448)return trigger;
 if(o==0x450)return !timeout;
 if(o==0x60)return in2;
 if(o==0x458) {
  if(failed_at && transfers>=failed_at)return 1;
  return (result_pa()+(wrong_pa?4096:0))<<12;
 }
 assert(0);return 0;
}
static void w32(vm_offset_t b,unsigned o,uint32_t v) {(void)b;assert(o==0x58 || o==8);(void)v;fsr=0;}
static void w64(vm_offset_t b,unsigned o,uint64_t v) {
 (void)b;
 if(o==0x430)in0=v;
 else if(o==0x438)in1=v;
 else if(o==0x440)in2=v;
 else if(o==0x448) {trigger=v;if(v) {assert(transfers<128);seen[transfers++]=(unsigned)in1;}}
 else assert(0);
}
static void delay_for_interval(unsigned a,unsigned b) {(void)a;(void)b;}
static void log_line(const char *fmt,...) {(void)fmt;}
static bool pool_permissions(void *c,uint64_t va,uint32_t size,uint32_t flags) {
 assert(c && va && size && (flags&1));++permission_calls;return permission_ok;
}
'''
tests = r'''
int main(void) {
 uint64_t a,b;override_pa=0x12345000;
 for(unsigned sid=0;sid<=5;sid+=5)for(unsigned mode=0;mode<8;mode++) {
  transfers=0;unsigned native_flags=((mode&1)?IOMMU_TRANS_PRIV:0)|((mode&2)?IOMMU_TRANS_INST:0)|((mode&4)?IOMMU_TRANS_WRITE:0);
  native_encode(sid,native_flags,&a,&b);
  assert(translate_page_access(1,2,0x4000,override_pa,sid,mode,1));
  assert(in0==a && in1==b && !trigger && transfers==1);
 }
 transfers=0;assert(!translate_page_access(1,2,0x4000,override_pa,1024,0,1) && !transfers);
 assert(!translate_page_access(1,2,0x4000,override_pa,0,8,1) && !transfers);
 assert(!translate_page_access(1,2,0x4000,override_pa,0,0,0) && !transfers);
 wrong_pa=true;assert(!translate_page_access(1,2,0x4000,override_pa,0,0,1) && transfers==1 && !trigger);
 transfers=0;wrong_pa=false;timeout=true;assert(!translate_page_access(1,2,0x4000,override_pa,0,0,1) && transfers==1 && !trigger);timeout=false;
 transfers=0;assert(translate_page(1,2,0x4000,override_pa,5) && in1==0x2408);
 override_pa=0;transfers=0;
 plan=(struct waffle_gmu_plan){.count=4,.regions={
  {WAFFLE_GPU_SQE_ADDRESS,8192,0x100000,true,true},
  {WAFFLE_GPU_AQE_ADDRESS,8192,0x200000,true,true},
  {WAFFLE_GPU_PWRUP_ADDRESS,4096,0x300000,true,false},
  {WAFFLE_HWSCHED_POOL_ADDRESS,16384,0x400000,false,false}}};
 struct access_matrix_context ctx={0};
 assert(access_matrix_capture(&ctx,BASE+0x500000,24,0x17f));
 assert(access_matrix_capture(&ctx,BASE+0x501000,4096,0x339));
 assert(ctx.count==2 && permission_calls==2);
 assert(access_matrix_run(&ctx,&plan,1,2,3,4) && transfers==13);
 /* Code: unprivileged data and instruction reads, never writes. */
 assert(seen[0]==0x408 && seen[1]==0x1408 && seen[2]==0x408 && seen[3]==0x1408);
 /* Restore: privileged read/write, then kind3 RW and kind15 unprivileged RO. */
 assert(seen[8]==0x2408 && seen[9]==0x2409 && seen[10]==0x2408 && seen[11]==0x2409 && seen[12]==0x408);
 transfers=0;failed_at=3;assert(!access_matrix_run(&ctx,&plan,1,2,3,4) && transfers==3 && !trigger);failed_at=0;
 transfers=0;ready=false;assert(!access_matrix_run(&ctx,&plan,1,2,3,4) && !transfers);ready=true;
 ctx.allocations[0].size=32768;transfers=0;assert(!access_matrix_run(&ctx,&plan,1,2,3,4) && transfers==10);
 permission_ok=false;unsigned before=ctx.count;assert(!access_matrix_capture(&ctx,BASE+0x502000,4096,7) && ctx.count==before);
 ctx.count=32;permission_calls=0;assert(!access_matrix_capture(&ctx,BASE+0x502000,4096,7) && !permission_calls);
 puts("ECATS actual code matches native encoding; real allocation modes, first-failure stop and shutdown guards pass (host only)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + reference + code + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g', str(path / 'test.c'),
                    '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
