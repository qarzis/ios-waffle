#!/usr/bin/env python3
"""Compare disabled startup writes against the actual pinned gen7_start body."""
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
VENDOR=ROOT/'work/waffle/gpu/vendor'
spec=importlib.util.spec_from_file_location('start_tables',ROOT/'tools/build-waffle-gpu-start-tables.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
data=module.generate(VENDOR)
native=(VENDOR/'adreno_gen7.c').read_text()
cores=(VENDOR/'adreno-gpulist.h').read_text()

def function(name):
    return re.search(r'(?:static void|static u64|int) '+name+r'\(.*?\n\}',native,re.S)[0]

def table(name):
    return re.search(r'static const [^;]+\b'+name+r'\[\]\s*=\s*\{.*?\n\};',cores,re.S)[0]

code='''#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1u<<(n))
#define GENMASK(h,l) ((0xffffffffu>>(31-(h))) & (0xffffffffu<<(l)))
#define FIELD_PREP(mask,val) (((uint32_t)(val)<<__builtin_ctz(mask))&(mask))
#define lower_32_bits(x) ((uint32_t)(x))
#define upper_32_bits(x) ((uint32_t)((x)>>32))
#define WARN_ON(x) (x)
#define KGSL_UBWC_4_0 4
#define SZ_4K 4096u
/* Our private protected aperture replaces the stock f0000000 bounds. */
#define KGSL_IOMMU_SECURE_BASE32 0xa0000000ULL
#define KGSL_IOMMU_SECURE_SIZE(x) 0x400000u
#define GEN7_UCHE_TRAP_BASE 0x1fffffffff000ULL
#define GEN7_PROTECT_DEFAULT (BIT(0)|BIT(1)|BIT(3))
#define GEN7_APRIV_DEFAULT (BIT(3)|BIT(2)|BIT(1)|BIT(0))
#define GEN7_BR_APRIV_DEFAULT (GEN7_APRIV_DEFAULT|BIT(6)|BIT(5))
#define ADRENO_FEATURE(a,b) true
#include "gen7_reg.h"
struct kgsl_regmap_list { u32 offset,val; };
struct gen7_protected_regs { u32 reg,start,end,noaccess; };
struct cpu_gpu_lock { u32 gpu_req,cpu_req,turn; union { struct {
 uint8_t ifpc_list_len,preemption_list_len;uint16_t dynamic_list_len; };u32 counts; }; };
struct platform { struct { void *of_node; } dev; } platform;
struct kgsl_device { struct platform *pdev; int regmap,mmu; } native_device={&platform,0,0};
struct adreno_gen7_core { const struct kgsl_regmap_list *gbif; unsigned gbif_count;
 unsigned hang_detect_cycles; const struct gen7_protected_regs *protected_regs; };
struct memory { void *hostptr; u64 gpuaddr; };
struct gpu_core { u32 gmem_size; };
struct adreno_device { struct memory *pwrup_reglist;u32 uche_gmem_base;struct gpu_core *gpucore;
 unsigned highest_bank_bit,uche_client_pf;bool lpac_enabled,bcl_enabled,patch_reglist; };
#define KGSL_DEVICE(a) (&native_device)
static void kgsl_regwrite(struct kgsl_device *d,u32 index,u32 value) {
 (void)d;printf("%u %u %u\\n",index,0xffffffffu,value); }
static void kgsl_regrmw(struct kgsl_device *d,u32 index,u32 mask,u32 value) {
 (void)d;printf("%u %u %u\\n",index,mask,value); }
static void kgsl_regmap_multi_write(int *map,const struct kgsl_regmap_list *r,unsigned count) {
 (void)map;for (unsigned i=0;i<count;i++) kgsl_regwrite(&native_device,r[i].offset,r[i].val); }
static int of_property_read_u32(void *node,const char *name,u32 *out) {
 (void)node;*out=name[5]=='m'?32:4;return 0; }
static bool adreno_is_gen7_9_x(struct adreno_device *a) { (void)a;return true; }
'''
for name in ('adreno_is_preemption_enabled','adreno_is_gen7_2_x_family','adreno_is_gen7_0_0',
             'adreno_is_gen7_0_1','adreno_is_gen7_4_0','adreno_is_gen7_2_0',
             'adreno_is_gen7_2_1','adreno_is_gen7_11_0'):
    code+=f'static bool {name}(struct adreno_device *a) {{ (void)a;return false; }}\n'
for name in ('_llc_configure_gpu_scid','_llc_gpuhtw_slice_activate','gen7_patch_pwrup_reglist'):
    code+=f'static void {name}(struct adreno_device *a) {{ (void)a; }}\n'
code+='static void gen7_hwcg_set(struct adreno_device *a,bool on) { (void)a;(void)on; }\n'
code+=table('gen7_0_0_gbif_regs')+'\n'+table('gen7_9_0_protected_regs')+'\n'
code+='''static const struct adreno_gen7_core core={gen7_0_0_gbif_regs,5,0xcfffff,gen7_9_0_protected_regs};
static const struct adreno_gen7_core *to_gen7_core(struct adreno_device *a) { (void)a;return &core; }
'''
code+='\n'.join(function(n) for n in ('gen7_get_uche_trap_base','gen7_protect_init','_set_secvid','gen7_start'))
code+='''
int main(void) {
 struct cpu_gpu_lock lock={0};struct memory memory={&lock,0x80070000};
 struct gpu_core gpu={0x300000};
 struct adreno_device adreno={&memory,0x1000000,&gpu,16,1,false,false,true};
 return gen7_start(&adreno);
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory);(path/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I',str(VENDOR),str(path/'test.c'),'-o',str(path/'test')],check=True)
    output=subprocess.check_output([str(path/'test')],text=True)
actual=[list(map(int,line.split())) for line in output.splitlines()]
expected=[[r['offset'],r['mask'],r['value']] for r in data['disabled_setup']]
assert actual==expected,[(a,b) for a,b in zip(actual,expected) if a!=b]
print(f'Native gen7_start configuration: {len(actual)} writes/RMW matched; ASan+UBSan passed; no device access')

# Execute the same pinned native startup with its stock trusted-window constants.
native_code=code.replace('KGSL_IOMMU_SECURE_BASE32 0xa0000000ULL','KGSL_IOMMU_SECURE_BASE32 0xf0000000ULL').replace('KGSL_IOMMU_SECURE_SIZE(x) 0x400000u','KGSL_IOMMU_SECURE_SIZE(x) 0xfffff000u')
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory);(path/'test.c').write_text(native_code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I',str(VENDOR),str(path/'test.c'),'-o',str(path/'test')],check=True)
    stock=[list(map(int,line.split())) for line in subprocess.check_output([str(path/'test')],text=True).splitlines()]
stock_expected=[row.copy() for row in expected]
for row in stock_expected:
    if row[0]==0xf800:row[2]=0xf0000000
    if row[0]==0xf802:row[2]=0xfffff000
assert stock==stock_expected
print('Stock native trusted window: exact _set_secvid writes and all other startup writes agree')
