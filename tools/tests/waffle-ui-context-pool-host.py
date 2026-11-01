"""Candidate128 context records with actual UI prefix, unchanged64MiB heap."""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
model={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
src=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(src[:src.index('\nwith tempfile.TemporaryDirectory()')],model)
log=(root/'work/waffle/runs/20261101T142143Z/kernel-120.log').read_text(errors='replace')
log=log[:log.index('GENERAL allocation_refused bytes=16384')]
requests={int(i):(int(b),int(f,16)) for i,b,f in re.findall(r'GENERAL_BO published index=(\d+) VA=[0-9a-f]+ bytes=(\d+) allocated=\d+ flags=([0-9a-f]+)',log)}
assert len(requests)==64 and sum((b+16383)&~16383 for b,f in requests.values())==40173568
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for bound in (64,128):
  header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
  (p/'waffle_gpu_memory.h').write_text(re.sub(r'#define WAFFLE_GPU_BO_LIMIT .*','#define WAFFLE_GPU_BO_LIMIT '+str(bound)+'u',header))
  (p/'waffle_gpu_registry.h').write_text((root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text())
  t='_Static_assert(sizeof(struct smmu_owner)<=16384,"Actual SMMU owner fits one16KiB allocation");\n'
  t+='int main(void){struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;\n'
  for i in sorted(requests):
   b,f=requests[i];t+=f'assert(smmu_registry_new(&owner,{b}u,{f}u));\n'
  if bound==64:
   t+='assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC) && objects==64 && !owner.registry.poisoned);\n'
  else:
   t+='for(unsigned i=64;i<128;i++)assert(smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));\n'
   t+='assert(owner.registry.count==128 && objects==128 && owner.registry.used==41222144 && owner.pool.count<=64 && !owner.registry.poisoned);\n'
   t+='assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC) && objects==128);\n'
  t+='assert(waffle_gpu_registry_destroy(&owner.registry,true));return 0;}'
  parts=model['parts'];(p/'test.c').write_text(model['h']+parts['mapping']+parts['types']+parts['dynamic']+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('Actual SMMU/registry:observed64UIBOs/40173568B reproduce65thslot refusal;candidate128records admits prefix+64smallBOs in41222144B,under unchanged64MiB/64tables;ownerfits16KiB;129threfused; host only')
