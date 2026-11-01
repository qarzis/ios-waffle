"""Replay the real fullscreen allocation prefix through actual BO/SMMU code."""
from pathlib import Path
import subprocess,tempfile,re,json
root=Path(__file__).resolve().parents[2]
# Existing actual C++ adapter harness; no synthetic GPU execution.
mem={};s=(root/'tools/tests/waffle-memory-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-memory-host.py')},mem)
tables={};s=(root/'tools/tests/waffle-table-budget-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-table-budget-host.py')},tables)
rows=[json.loads(l) for l in (root/'work/waffle/gpu/forensic-audit/e44-gl-fullsize/msm-requests.jsonl').read_text().splitlines()]
requests=[r for r in rows if r.get('nr')==0x42 and r.get('ret')==0]
assert len(requests)==24 and max(r['size'] for r in requests)==5242880
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for bound in (4194304,8388608):
  header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
  header=re.sub(r'#define WAFFLE_GPU_BO_MAX_BYTES .*','#define WAFFLE_GPU_BO_MAX_BYTES '+str(bound)+'u',header)
  (p/'waffle_gpu_memory.h').write_text(header)
  (p/'waffle_gpu_registry.h').write_text((root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text())
  if bound==4194304:
   t='int main(){waffle_gpu_memory bo={};mode=0;assert(!waffle_gpu_memory_create(5242880,WAFFLE_GPU_BO_WC,&bo));assert(!bo.object);return 0;}'
  else:
   t=mem['t'].replace('16384u,4194304u','16384u,4194304u,5242880u,8388608u').replace('4194305','WAFFLE_GPU_BO_MAX_BYTES+1')
  (p/'memory.cpp').write_text('#include <initializer_list>\n'+mem['h']+mem['s']+t)
  subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(p),str(p/'memory.cpp'),'-o',str(p/'memory')],check=True)
  subprocess.run([str(p/'memory')],check=True)
  t='int main(void){struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;\n'
  rejected=False
  for i,r in enumerate(requests):
   size=r['size'];flags=0x20000|(r['flags']&2)
   if size>bound:
    t+=f'assert(!smmu_registry_new(&owner,{size}u,{flags}u));assert(owner.registry.count=={i} && !owner.registry.poisoned);\n'
    rejected=True;break
   t+=f'assert(smmu_registry_new(&owner,{size}u,{flags}u));\n'
  if bound==4194304:assert rejected
  else:
   assert not rejected
   t+='assert(owner.registry.count==24 && owner.registry.used==18333696 && !owner.registry.poisoned && owner.pool.count<=64);assert(waffle_gpu_registry_destroy(&owner.registry,true));\n'
  t+='return 0;}'
  parts=tables['parts'];(p/'tables.c').write_text(tables['h']+parts['mapping']+parts['types']+parts['dynamic']+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'tables.c'),'-o',str(p/'tables')],check=True)
  subprocess.run([str(p/'tables')],check=True)
print('Actual C++ BO adapter and SMMU:4MiB reproduces5MiB refusal;8MiB accepts5/8MiB with noncontiguous physical pages, rejects cap+1; actual24fullscreen allocations fit32MiB heap and64tables after25-table bootstrap; host only')
