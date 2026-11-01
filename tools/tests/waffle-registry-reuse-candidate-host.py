"""Tombstone reuse in unmodified actual registry/SMMU code; hardware mocked."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-reclaim-smmu-host.py')}
s=(root/'tools/tests/waffle-reclaim-smmu-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
memory=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
registry=(root/'kernel/files/bsd/sys/waffle_gpu_registry.h').read_text()
extra=ns['extra'].replace('return 0x20000000ULL+bo->object*0x1000000ULL+off*2;',
 'return 0x20000000ULL+(uint64_t)(bo-active->registry.buffers)*0x100000ULL+off*2;')
test=r'''
int main(void){
 struct smmu_owner owner;reset_owner(&owner);
 struct waffle_gpu_memory *anchor=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC|2);assert(anchor);
 uint64_t expected=pte(&owner.pool,anchor->gpu_va);unsigned tables=owner.pool.count;
 for(unsigned i=0;i<100000;i++){
  struct waffle_gpu_memory *bo=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC);
  assert(bo==&owner.registry.buffers[1] && owner.registry.count==2);
  assert(bo->serial==i+2 && owner.registry.issued==i+2 && owner.registry.used==32768);
  for(unsigned off=0;off<16384;off+=4096){
   uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
   assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==0x43);
  }
  assert(smmu_registry_reclaim(&owner,bo,true));
  assert(!bo->object && !bo->serial && owner.registry.used==16384);
  assert(pte(&owner.pool,anchor->gpu_va)==expected && owner.pool.count==tables);
 }
 assert(objects==100001 && live_released==100000 && owner.registry.count==2 && owner.registry.issued==100001);
 unsigned saved=owner.registry.issued;owner.registry.issued=UINT32_MAX;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC) && objects==100001);
 owner.registry.issued=saved;
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects && storage_frees==1);
 assert(!owner.registry.count && !owner.registry.issued && !owner.registry.buffers);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 (p/'waffle_gpu_memory.h').write_text(memory);(p/'waffle_gpu_registry.h').write_text(registry)
 (p/'waffle_gpu_reclaim.h').write_text((root/'kernel/files/bsd/sys/waffle_gpu_reclaim.h').read_text())
 h=ns['h'].replace('memory[64][16384]','memory[160][16384]').replace('allocated<64','allocated<160')
 (p/'test.c').write_text(h+ns['ns']['parts']['mapping']+ns['types']+ns['ns']['parts']['dynamic']+extra+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
  '-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual registry/SMMU:100000 allocate/revoke/reclaim cycles reuse one tombstone with monotonic serials; readonly anchor PTE/table count/resident budget unchanged, dual-ASID revocation before reuse, serial overflow refuses, full teardown once. No registry header adaptations; hardware mocked.')
