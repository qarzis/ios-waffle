"""Independent post-bootstrap data mapping and descriptor relocation audit."""
from pathlib import Path
import importlib.util,json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
# Reuse actual mapper test fixture, enable its second allocation and inspect both sets of real PTEs.
fixture=(root/'tools/tests/waffle-dynamic-bo-host.py').read_text();parts={}
# Only obtain harness strings; do not execute fixture's bottom-level compile/run.
exec(fixture[:fixture.index('with tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-dynamic-bo-host.py')},parts)
h=parts['harness'].replace('static unsigned allocated,mode,tlbs,cleans,binds,after_start_allocs;','static unsigned allocated,mode,tlbs,cleans,binds,after_start_allocs,data_binds;')
h=h.replace('if(live && mode==1)return 1;', 'if(live && ((mode==1 && after_start_allocs==0)||(mode==13 && after_start_allocs==1)))return 1;')
h=h.replace('after_start_allocs==1);cleans++;','after_start_allocs>=1);cleans++;')
h=h.replace('!(mode==7 && cb==2)','!(mode==7 && cb==2) && !(mode==15 && tlbs==4)')
types=parts['types'];start=types.index('static bool waffle_gmu_owner_bind_data_bo(');end=types.index('static bool waffle_gmu_owner_can_bind_bo(',start)
types=types[:start]+types[end:]
types=types.replace('static bool waffle_gmu_owner_can_bind_bo(', 'static bool waffle_gmu_owner_can_bind_bo(')
# Stale lower/upper leaf entries and explicit allocation failure are tested before mapping data.
types=types.replace(' binds++;return mode!=8;', ''' binds++;
 if(mode==12)assert(map_page(&active->pool,WAFFLE_GPU_DATA_ADDRESS,0x20000000,false));
 if(mode==14)assert(map_page(&active->pool,0x47c000,0x20000000,false));
 return mode!=8;''')
types += r'''
static bool waffle_gmu_owner_bind_data_bo(struct waffle_gmu_owner *g,struct waffle_gmu_region *r){
 assert(g==&child && r==&active->data && r->address==WAFFLE_GPU_DATA_ADDRESS && tlbs==4);
 assert(r->memory!=active->dynamic.memory && kvtophys(r->memory)!=kvtophys(active->dynamic.memory));
 for(unsigned off=0;off<16384;off+=4096){
  uint64_t low=pte(&active->pool,(uint64_t)r->address+off),high=pte(&active->pool,0x47c000+off);
  assert(low==high && (low&PTE_ADDRESS)==kvtophys(r->memory+off) && (low&0xc3)==0x43);
 }
 data_binds++;return mode!=16;
}
'''
t=parts['tests'].replace('mode<12','mode<17').replace('after_start_allocs=0;live=false;', 'after_start_allocs=data_binds=0;live=false;').replace('struct smmu_owner owner={.child=', 'struct smmu_owner owner={.compute_image=7,.child=')
t=t.replace('(mode==6 || mode==7)', '(mode==6 || mode==7 || mode==15)').replace('assert((mode==6 || mode==7 || mode==15) && after_start_allocs==1 && owner.dynamic.memory && !binds);','assert(owner.dynamic.memory && ((mode==15 && after_start_allocs==2 && owner.data.memory && binds==1) || ((mode==6 || mode==7) && after_start_allocs==1 && !binds)));')
t=t.replace('if(mode==0 || mode==8)assert(after_start_allocs==1 && owner.dynamic.memory && tlbs==2 && binds==1);\n  else assert(!after_start_allocs && !tlbs && !binds);', '''if(mode==0 || mode==16)assert(after_start_allocs==2 && owner.dynamic.memory && owner.data.memory && tlbs==4 && binds==1 && data_binds==1);
  else if(mode==8 || mode==12 || mode==13 || mode==14)assert(after_start_allocs==1 && owner.dynamic.memory && !owner.data.memory && tlbs==2 && binds==1 && !data_binds);
  else assert(!after_start_allocs && !tlbs && !binds);''')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+parts['mapping']+types+parts['dynamic']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Existing stock Mesa FDL descriptor has base address at dwords4/5 of its16-word record.
source=(root/'kernel/files/bsd/sys/waffle_gpu_copy.h').read_text();body=re.search(r'waffle_copy_payload\[4096\]=\{(.*?)\};',source,re.S)[1]
w=[int(v,16) for v in re.findall('0x([0-9a-f]+)u',body)]
assert len(w)==4096 and w[1089]==512 and (w[1092]|w[1093]<<32)==0x1ff800047b000
assert 'fdl6_buffer_view_init' in (root/'xnu-deps/build/mesa/mesa-26.3.0-rc1/src/freedreno/computerator/a6xx.cc').read_text()
code=r'''
#include <assert.h>
#include "waffle_gpu_data.h"
int main(void){
 uint32_t input[256];for(unsigned i=0;i<256;i++)input[i]=waffle_job_test_pixel(2,i);
 for(unsigned fence=1;fence<=3;fence++)for(unsigned word=0;word<4096;word++){
  uint32_t initial=waffle_copy_initial(2,word),before=waffle_data_command_word(input,fence,word,0x1ff800047c000ULL,false);
  if(word==430 || word==435)initial=fence;
  if(word==1092)initial=0x47c000;if(word==1093)initial=0x1ff80;
  assert(initial==before);
  assert(waffle_data_command_word(input,fence,word,0x1ff800047c000ULL,true)==(word==2048?fence:before));
  uint32_t value=word<256?0xdead0000u+word:word<512?input[word-256]:0xdada0000u^word;
  assert(waffle_data_word(input,word,false)==value);
  assert(waffle_data_word(input,word,true)==(word<256?input[word]:value));
 }
 assert(waffle_gpu_compact_alias(0x8007ffff)==0x1ff800047ffffULL);
 assert(!waffle_gpu_compact_alias(0x80080000));
 return 0;
}
'''
code=code.replace('#include "waffle_gpu_data.h"','#include "waffle_gpu_data.h"\n#include "waffle_gpu_va.h"')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
text=(root/'work/waffle/runs/20261101T081724Z/kernel-final.log').read_text()
text=text.replace('waffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256','DATA_BO published separately VA=8007c000 pages=4 aliases=2 unprivileged=1\nwaffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256')
for f in (1,2,3):
 marker=f'waffle-gmu: COPY_JOB done fence={f} seq={43+f} control={f:08x} checked=4096 wrong_words=0'
 text=text.replace(marker,f'DATA_BO checked=4096 wrong_words=0 fence={f} independent=1\n'+marker)
text=text.replace('waffle-iommu: SMMU_OWNER released after child stop and context detach','DATA_BO released after GPU stop and context detach\nwaffle-iommu: SMMU_OWNER released after child stop and context detach')
assert runner.validate_aop_owner_log(text,2,7)==runner.extract_copy_jobs(text)[-1]
for m in ['DATA_BO published separately VA=8007c000 pages=4 aliases=2 unprivileged=1','DATA_BO released after GPU stop and context detach',*(f'DATA_BO checked=4096 wrong_words=0 fence={f} independent=1' for f in (1,2,3))]:
 try:runner.validate_aop_owner_log(text.replace(m,''),2,7)
 except RuntimeError:pass
 else:raise AssertionError('Missing independent data BO evidence accepted')
print('Separate data BO: 17 actual mapping/PTE/publication/failure cases, distinct backing, exact FDL descriptor base relocation, command-old-output unchanged and all8192 expected words passed (host only)')
