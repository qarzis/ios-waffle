"""Reproduce the first measured UI heap failure with the actual registry/SMMU."""
from pathlib import Path
import json,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
model={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
src=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(src[:src.index('\nwith tempfile.TemporaryDirectory()')],model)
report=json.loads((root/'work/waffle/gpu/forensic-audit/E47-result.json').read_text())
requests=report['BO_prefix_at_heap_refusal']
assert len(requests)==35 and sum(r['allocated'] for r in requests)==28901376
t='int main(void){struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;\n'
for r in requests:t+=f"assert(smmu_registry_new(&owner,{r['bytes']}u,{r['flags']}u));\n"
t+=r'''
 assert(owner.registry.count==35 && objects==35 && owner.registry.used==28901376 && !owner.registry.poisoned);
 unsigned tables_before=owner.pool.count;
 assert(!smmu_registry_new(&owner,5242880,WAFFLE_GPU_BO_WC));
 /* Refusal occurs before backing allocation or PTE/TLB changes. */
 assert(owner.registry.count==35 && objects==35 && owner.registry.used==28901376 && !owner.registry.poisoned && owner.pool.count==tables_before);
 assert(smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
 assert(owner.registry.count==36 && objects==36 && owner.registry.used==28917760 && owner.pool.count<=64);
 assert(waffle_gpu_registry_destroy(&owner.registry,true));return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);parts=model['parts'];
 header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text();import re
 (p/'waffle_gpu_memory.h').write_text(re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*','#define WAFFLE_GPU_BO_HEAP_BYTES 33554432u',header))
 (p/'waffle_gpu_registry.h').write_text((root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text())
 (p/'test.c').write_text(model['h']+parts['mapping']+parts['types']+parts['dynamic']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual SMMU/registry:35 observedUIBOs use28901376bytes;5MiB request exceeds32MiB and fails before allocation/PTE/TLB,small16KiB request succeeds,no poisoning/table exhaustion; host only')
