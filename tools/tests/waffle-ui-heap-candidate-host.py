"""Compare measured UI requests at32/64MiB and fill the candidate SMMU window."""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
model={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
src=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(src[:src.index('\nwith tempfile.TemporaryDirectory()')],model)
requests=json.loads((root/'work/waffle/gpu/forensic-audit/E47-result.json').read_text())['BO_prefix_at_heap_refusal']
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for budget in (33554432,67108864):
  header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
  header=re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*','#define WAFFLE_GPU_BO_HEAP_BYTES '+str(budget)+'u',header)
  (p/'waffle_gpu_memory.h').write_text(header)
  (p/'waffle_gpu_registry.h').write_text((root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text())
  t='int main(void){struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;\n'
  for r in requests:t+=f"assert(smmu_registry_new(&owner,{r['bytes']}u,{r['flags']}u));\n"
  if budget==33554432:
   t+='unsigned tables_before=owner.pool.count;assert(!smmu_registry_new(&owner,5242880,WAFFLE_GPU_BO_WC));assert(objects==35 && owner.registry.used==28901376 && owner.pool.count==tables_before && !owner.registry.poisoned);\n'
  else:
   t+='assert(smmu_registry_new(&owner,5242880,WAFFLE_GPU_BO_WC));assert(objects==36 && owner.registry.used==34144256 && !owner.registry.poisoned);\n'
  t+='assert(waffle_gpu_registry_destroy(&owner.registry,true));\n'
  if budget==67108864:
   t+=r'''
   allocated=objects=after_start_allocs=0;live=false;memset(&owner,0,sizeof(owner));
   owner.compute_image=13;owner.child=&child;
   owner.permission_context=(struct pool_permission_context){.cb=1,.lpac_cb=2};active=&owner;
   for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));
   owner.permission_context.tables=&owner.pool;live=true;
   for(unsigned i=0;i<8;i++){
    struct waffle_gpu_memory *bo=smmu_registry_new(&owner,8388608,WAFFLE_GPU_BO_WC);assert(bo);
    for(unsigned off=0;off<bo->allocation_bytes;off+=4096){
     uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
     assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==0x43);
    }
   }
   assert(objects==8 && owner.registry.used==67108864 && owner.pool.count<=64 && !owner.registry.poisoned);
   unsigned tables_before=owner.pool.count;
   assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
   assert(objects==8 && owner.registry.count==8 && owner.pool.count==tables_before);
   assert(waffle_gpu_registry_destroy(&owner.registry,true));
'''
  t+='return 0;}'
  parts=model['parts'];(p/'test.c').write_text(model['h']+parts['mapping']+parts['types']+parts['dynamic']+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('Actual registry/SMMU:32MiB reproduces measuredUI5MiB refusal;64MiB admits exact35BO prefix+5MiB;entire64MiB window/all16384PTEs fits64tables after25boot tables,heap+1page rejected without allocation/PTE mutation; host only')
