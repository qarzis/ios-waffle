"""E56 candidate128MiB BEFORE changing runtime: exact live UI and full PTE span."""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-reclaim-smmu-host.py')}
s=(root/'tools/tests/waffle-reclaim-smmu-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
ledger=json.loads((root/'work/waffle/gpu/forensic-audit/E55-memory-timeline.json').read_text())
fixture='static const uint64_t measured[][4]={'+','.join(
 '{%d,%d,%d,%d}'%((e['kind']=='new'),e['handle'],e.get('bytes',0),e.get('flags',0)) for e in ledger['events'])+'};\n'
test=r'''
int main(void){
 struct smmu_owner owner;reset_owner(&owner);
 struct waffle_gpu_memory *issued[907]={0};
 for(unsigned i=0;i<sizeof(measured)/sizeof(measured[0]);i++){
  const uint64_t *e=measured[i];
  if(e[0]){
   struct waffle_gpu_memory *bo=smmu_registry_new(&owner,e[2],e[3]);assert(bo && owner.registry.issued==e[1]);issued[e[1]]=bo;
   for(unsigned off=0;off<bo->allocation_bytes;off+=4096){
    uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
    assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==((bo->flags&2)?0xc3:0x43));
   }
  }else assert(smmu_registry_reclaim(&owner,issued[e[1]],true));
 }
 assert(owner.registry.issued==906 && owner.registry.used==67108864 && live_released==13);
 struct waffle_gpu_memory *next=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC|2);
 assert((next!=NULL)==(WAFFLE_GPU_BO_HEAP_BYTES==134217728));
 if(next)assert(owner.registry.used==67125248 && owner.registry.issued==907);
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects && storage_frees==1);
 if(WAFFLE_GPU_BO_HEAP_BYTES==134217728){
  reset_owner(&owner);
  if(setjmp(reset_trap)){
   assert(TABLE_LIMIT==64 && owner.registry.poisoned && objects==10 && owner.registry.count==10 && !released);
   assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects);return 0;
  }
  for(unsigned i=0;i<16;i++){
   struct waffle_gpu_memory *bo=smmu_registry_new(&owner,8388608,WAFFLE_GPU_BO_WC|(i&1?2:0));assert(bo);
   for(unsigned off=0;off<bo->allocation_bytes;off+=4096){
    uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
    assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==((i&1)?0xc3:0x43));
   }
  }
  assert(TABLE_LIMIT==128 && owner.pool.count==90 && owner.registry.used==134217728 && !owner.registry.poisoned);
  unsigned tables=owner.pool.count,created=objects;
  assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
  assert(objects==created && owner.pool.count==tables && !owner.registry.poisoned);
  assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects && storage_frees==1);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for budget,tables in [(67108864,64),(134217728,64),(134217728,128)]:
  header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
  header=re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*',f'#define WAFFLE_GPU_BO_HEAP_BYTES {budget}u',header)
  (p/'waffle_gpu_memory.h').write_text(header)
  for name in ['waffle_gpu_registry.h','waffle_gpu_reclaim.h']:(p/name).write_text((root/'kernel/files/bsd/sys'/name).read_text())
  h=ns['h'].replace('memory[64][16384]','memory[128][16384]').replace('allocated<64','allocated<128')
  mapping=re.sub(r'#define TABLE_LIMIT \d+',f'#define TABLE_LIMIT {tables}',ns['ns']['parts']['mapping'])
  (p/'test.c').write_text(h+mapping+ns['types']+ns['ns']['parts']['dynamic']+ns['extra']+fixture+test)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
   '-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)

# Actual owner declarations and constructor code, rather than the small adapter
# harness's reduced owner, must still fit the allocated16KiB kernel page.
owner={'__file__':str(root/'tools/tests/waffle-smmu-owner-host.py')}
s=(root/'tools/tests/waffle-smmu-owner-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],owner)
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 h=owner['h'].replace('#define TABLE_LIMIT 32','#define TABLE_LIMIT 128')
 body='int main(void){assert(sizeof(struct smmu_owner)<=PAGE_SIZE);assert(sizeof(struct protected_gpu_pool)<=PAGE_SIZE);return 0;}'
 (p/'owner.c').write_text(h+owner['code']+body)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
  '-I',str(root/'kernel/files/bsd/sys'),str(p/'owner.c'),'-o',str(p/'owner')],check=True)
 subprocess.run([str(p/'owner')],check=True)
print('HOST candidate:all906 measured allocations/13reclaims reproduce live64MiB refusal and admit next16KiB at128MiB; old64 tables fail/retain during128MiB fill,128tables cover all32768PTEs using90tables after25bootstrap; extra page refuses without mutation; actual owner/protected structs still fit16KiB. Runtime not changed by this test, no GPU claim.')
