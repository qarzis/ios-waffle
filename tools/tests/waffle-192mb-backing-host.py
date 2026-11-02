"""Qualify the larger physical budget with the actual registry/SMMU adapter."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-reclaim-smmu-host.py')}
s=(root/'tools/tests/waffle-reclaim-smmu-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
test=r'''
int main(void){
 struct smmu_owner owner;reset_owner(&owner);
 assert(WAFFLE_GPU_BO_LIMIT==8192 && WAFFLE_GPU_BO_HEAP_BYTES==201326592 && WAFFLE_GPU_BO_VA_BYTES==268435456);
 struct waffle_gpu_memory *blocks[24];
 for(unsigned i=0;i<24;i++){
  blocks[i]=smmu_registry_new(&owner,8388608,WAFFLE_GPU_BO_WC|(i&1?2:0));assert(blocks[i]);
  assert(blocks[i]->gpu_va==WAFFLE_GPU_BO_VA_BASE+(uint64_t)i*8388608);
  for(unsigned off=0;off<8388608;off+=4096){
   uint64_t entry=pte(&owner.pool,blocks[i]->gpu_va+off);
   assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(blocks[i],off));
   assert((entry&0xc3)==(i&1?0xc3:0x43));
  }
 }
 assert(owner.registry.used==201326592 && owner.registry.count==24 && !owner.registry.poisoned && owner.pool.count<=160);
 unsigned tables=owner.pool.count,created=objects;uint32_t issued=owner.registry.issued;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
 assert(objects==created && owner.pool.count==tables && owner.registry.issued==issued && owner.registry.used==201326592 && !owner.registry.poisoned);
 uint64_t va=blocks[17]->gpu_va;uint64_t left=pte(&owner.pool,va-4096),right=pte(&owner.pool,va+8388608);
 assert(va>=WAFFLE_GPU_BO_VA_BASE+134217728);
 assert(smmu_registry_reclaim(&owner,blocks[17],true));
 assert(owner.registry.used==192937984 && live_released==1);
 for(unsigned off=0;off<8388608;off+=4096)assert(!pte(&owner.pool,va+off));
 assert(pte(&owner.pool,va-4096)==left && pte(&owner.pool,va+8388608)==right);
 struct waffle_gpu_memory *replacement=smmu_registry_new(&owner,8388608,WAFFLE_GPU_BO_WC);
 assert(replacement==blocks[17] && replacement->gpu_va==va && replacement->serial==issued+1 && owner.registry.used==201326592);
 for(unsigned off=0;off<8388608;off+=4096){
  uint64_t entry=pte(&owner.pool,va+off);assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(replacement,off) && (entry&0xc3)==0x43);
 }
 assert(owner.pool.count==tables && waffle_gpu_registry_destroy(&owner.registry,true) && released==25 && storage_frees==1);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='waffle-192m-') as directory:
 p=Path(directory)
 mapping=re.sub(r'#define TABLE_LIMIT \d+','#define TABLE_LIMIT 160',ns['ns']['parts']['mapping'])
 h=ns['h'].replace('memory[64][16384]','memory[160][16384]').replace('allocated<64','allocated<160')
 (p/'test.c').write_text(h+mapping+ns['types']+ns['ns']['parts']['dynamic']+ns['extra']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual registry/SMMU:24x8MiB reaches192MiB through160-table pool, all PA/AP leaves verified, heap+16KiB refuses before mutation, live reclaim/reuse above128MiB preserves neighbors/8192-slot generation ABI and full teardown. Synthetic physical memory/GPU only.')
