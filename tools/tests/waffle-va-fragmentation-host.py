"""E59 candidate:separate virtual placement from unchanged128MiB backing budget.

Uses measured live BO addresses; PA values are synthetic and GPU is mocked.
Runtime headers are not modified by this candidate comparison.
"""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-reclaim-smmu-host.py')}
s=(root/'tools/tests/waffle-reclaim-smmu-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
record=json.loads((root/'work/waffle/gpu/forensic-audit/E58-fragmented-state.json').read_text())
assert len(record['live_BO_state'])==1840
fixture='static const uint64_t state[][5]={'+','.join(
 '{%d,%d,%d,%d,%dULL}'%(b['handle'],b['bytes'],b['allocated'],b['flags'],b['VA']) for b in record['live_BO_state'])+'};\n'
test=r'''
int main(void){
 struct smmu_owner owner;reset_owner(&owner);assert(smmu_registry_prepare(&owner));
 owner.registry.count=3272;owner.registry.used=117080064;objects=3272;
 for(unsigned i=0;i<1840;i++){
  const uint64_t *b=state[i];struct waffle_gpu_memory *bo=&owner.registry.buffers[b[0]-1];
  *bo=(struct waffle_gpu_memory){.object=b[0],.bytes=b[1],.allocation_bytes=b[2],.flags=b[3],.gpu_va=b[4],.published=true};
  for(unsigned off=0;off<bo->allocation_bytes;off+=4096)
   assert(smmu_registry_page(&owner,bo->gpu_va+off,waffle_gpu_memory_page(bo,off),(bo->flags&2)!=0));
 }
 smmu_registry_clean(&owner);assert(smmu_registry_tlb(&owner));
 unsigned tables_before=owner.pool.count;
 struct waffle_gpu_memory *next=smmu_registry_new(&owner,3145728,WAFFLE_GPU_BO_WC);
 assert((next!=NULL)==(CANDIDATE_VA_BYTES==268435456));
 if(next){
  assert(owner.registry.used==120225792 && owner.registry.used<WAFFLE_GPU_BO_HEAP_BYTES);
  assert(next->gpu_va>=WAFFLE_GPU_BO_VA_BASE+134217728-3145728);
  for(unsigned off=0;off<next->allocation_bytes;off+=4096)
   assert((pte(&owner.pool,next->gpu_va+off)&PTE_ADDRESS)==waffle_gpu_memory_page(next,off));
 }else assert(owner.registry.used==117080064 && owner.pool.count==tables_before && !owner.registry.poisoned);
 for(unsigned i=0;i<1840;i++){
  const struct waffle_gpu_memory *bo=&owner.registry.buffers[state[i][0]-1];
  for(unsigned off=0;off<bo->allocation_bytes;off+=4096){
   uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
   assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==((bo->flags&2)?0xc3:0x43));
  }
 }
 if(next){
  uint64_t va=next->gpu_va;
  assert(smmu_registry_reclaim(&owner,next,true) && owner.registry.used==117080064);
  for(unsigned off=0;off<3145728;off+=4096)assert(!pte(&owner.pool,va+off));
  struct waffle_gpu_memory *replacement=smmu_registry_new(&owner,3145728,WAFFLE_GPU_BO_WC|2);
  assert(replacement && replacement->gpu_va==va && owner.registry.used==120225792);
  for(unsigned off=0;off<3145728;off+=4096){
   uint64_t entry=pte(&owner.pool,va+off);
   assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(replacement,off) && (entry&0xc3)==0xc3);
  }
 }
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==1840+2*(next!=NULL));
 /* Verify maximum virtual coverage independent of physical residency: leaves
  * use synthetic PA pages. This is a table-bound proof, not256MiB live BOs. */
 reset_owner(&owner);
 for(unsigned off=0;off<CANDIDATE_VA_BYTES;off+=4096)
  assert(map_page_access(&owner.pool,WAFFLE_GPU_BO_VA_BASE+off,0x20000000ULL+off*2,(off&16384)!=0,true));
 for(unsigned off=0;off<CANDIDATE_VA_BYTES;off+=4096){
  uint64_t entry=pte(&owner.pool,WAFFLE_GPU_BO_VA_BASE+off);
  assert((entry&PTE_ADDRESS)==0x20000000ULL+off*2 && (entry&0xc3)==((off&16384)?0xc3:0x43));
 }
 assert(owner.pool.count==(CANDIDATE_VA_BYTES==268435456?154:90) && owner.pool.count<=TABLE_LIMIT);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for span,limit in [(134217728,128),(268435456,160)]:
  registry=(root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text()
  old='uint64_t end=WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES-allocated;'
  new='uint64_t end=WAFFLE_GPU_BO_VA_BASE+CANDIDATE_VA_BYTES-allocated;'
  assert old in registry;registry=registry.replace(old,new)
  (p/'waffle_gpu_registry.h').write_text(registry)
  for header in ['waffle_gpu_memory.h','waffle_gpu_reclaim.h']:(p/header).write_text((root/'kernel/files/bsd/sys'/header).read_text())
  h=ns['h'].replace('memory[64][16384]',f'memory[{limit}][16384]').replace('allocated<64',f'allocated<{limit}')
  mapping=re.sub(r'#define TABLE_LIMIT \d+',f'#define TABLE_LIMIT {limit}',ns['ns']['parts']['mapping'])
  (p/'test.c').write_text(h+mapping+ns['types']+ns['ns']['parts']['dynamic']+ns['extra']+fixture+test)
  subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
   f'-DCANDIDATE_VA_BYTES={span}u','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
owner={'__file__':str(root/'tools/tests/waffle-smmu-owner-host.py')}
s=(root/'tools/tests/waffle-smmu-owner-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],owner)
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);h=owner['h'].replace('#define TABLE_LIMIT 32','#define TABLE_LIMIT 160')
 (p/'owner.c').write_text(h+owner['code']+'int main(void){assert(sizeof(struct smmu_owner)<=16384);assert(sizeof(struct protected_gpu_pool)<=16384);return 0;}')
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
  '-I',str(root/'kernel/files/bsd/sys'),str(p/'owner.c'),'-o',str(p/'owner')],check=True)
 subprocess.run([str(p/'owner')],check=True)
print('HOST candidate:exact1840 live BO ranges reproduce3MiB VA fragmentation refusal in128MiB,256MiB VA admits same request with unchanged128MiB physical budget/neighbors/PA/AP; all256MiB virtual leaves fit154of160tables after25bootstrap; actualowner/protected structs fit16KiB. Synthetic PA/GPU only; runtime unchanged by comparison.')
