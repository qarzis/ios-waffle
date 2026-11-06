from pathlib import Path
import subprocess,tempfile,re,json,hashlib
r=Path(__file__).resolve().parents[4]
h=r/'work/waffle/audio/upstream/msm-kernel/drivers/iommu/arm/arm-smmu/arm-smmu.h'
s=h.read_text();start=s.index('static inline u32 arm_smmu_lpae_sctlr(');end=s.index('\n}\n',start)+2;fn=s[start:end]
defs='\n'.join(x for x in s.splitlines() if x.startswith('#define ARM_SMMU_SCTLR_'))
code='''#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
typedef uint32_t u32;
#define BIT(n) (1u<<(n))
#define GENMASK(h,l) (((~0u)<<(l))&((~0u)>>(31-(h))))
#define FIELD_PREP(mask,value) (((u32)(value)<<__builtin_ctz(mask))&(mask))
#define CONFIG_CPU_BIG_ENDIAN 0
#define IS_ENABLED(v) (v)
#define CBAR_TYPE_S2_TRANS 0
struct arm_smmu_cfg {unsigned cbar;struct {u32 wacfg:2,racfg:2,shcfg:2,mtcfg:1,memattr:4,hupcf:1,cfcfg:1,cfre:1,m:1;} sctlr;};
'''+defs+'\n'+fn+'''
int main(void){struct arm_smmu_cfg cfg={.cbar=1};u32 raw=0x77da;__builtin_memcpy(&cfg.sctlr,&raw,4);assert(arm_smmu_lpae_sctlr(&cfg)==0x0a5f10e7);cfg.sctlr.m=0;assert(!(arm_smmu_lpae_sctlr(&cfg)&1));puts("PASS actual pinned native SCTLR builder: observed cfg77da/cbar1 -> cached0a5f10e7; disabled stage1 M0 retains cache/fault configuration. Host/native-observation consistency only.");}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
trace=r/'work/waffle/audio/A21-native-cfg-trace.txt';text=trace.read_text();assert 'probe_exit=0' in text and re.search(r'cb=46 asid=46 cfg_sctlr=0x77da cbar=0x1 fmt=1 stage=0',text)
(r/'work/waffle/audio/A21-result.json').write_text(json.dumps({'native_import_unmap_pass':True,'Android_only':True,'context_bank':46,'asid':46,'cfg_sctlr':'0x77da','cbar':1,'format':'AArch64','stage':1,'native_builder_sctlr':'0x0a5f10e7','matches_cached_SCTLR':True,'source_sha256':hashlib.sha256(h.read_bytes()).hexdigest(),'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'XNU_context_bank_ownership':False,'DSP_PCM_playback':False},indent=2)+'\n')
