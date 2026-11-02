"""Actual registry/SMMU: native 10/12 MiB and largest bounded single objects."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
ns = {'__file__': str(root/'tools/tests/waffle-reclaim-smmu-host.py')}
source = (root/'tools/tests/waffle-reclaim-smmu-host.py').read_text()
exec(source[:source.index('\nwith tempfile.TemporaryDirectory()')], ns)
test = r'''
int main(void) {
 struct smmu_owner owner;reset_owner(&owner);
 assert(waffle_gpu_registry_flags(10485760,WAFFLE_GPU_BO_WC));
 assert(WAFFLE_GPU_BO_MAX_BYTES==WAFFLE_GPU_BO_HEAP_BYTES);
 assert(!waffle_gpu_registry_flags((uint64_t)WAFFLE_GPU_BO_MAX_BYTES+1,WAFFLE_GPU_BO_WC));
 assert(WAFFLE_GPU_BO_HEAP_BYTES==201326592 && WAFFLE_GPU_BO_VA_BYTES==268435456 && WAFFLE_GPU_BO_LIMIT==8192);
 struct waffle_gpu_memory *bo[20];
 for(unsigned i=0;i<20;i++) {
  unsigned bytes=i<19?10485760:2097152;
  bo[i]=smmu_registry_new(&owner,bytes,WAFFLE_GPU_BO_WC|(i&1?2:0));assert(bo[i]);
  for(unsigned off=0;off<bytes;off+=4096) {
   uint64_t e=pte(&owner.pool,bo[i]->gpu_va+off);
   assert((e&PTE_ADDRESS)==waffle_gpu_memory_page(bo[i],off));
   assert((e&0xc3)==(i&1?0xc3:0x43));
  }
 }
 assert(owner.registry.used==201326592 && owner.pool.count<=160 && !owner.registry.poisoned);
 unsigned old=objects,tables=owner.pool.count,issued=owner.registry.issued;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
 assert(!smmu_registry_new(&owner,(uint64_t)WAFFLE_GPU_BO_MAX_BYTES+1,WAFFLE_GPU_BO_WC));
 assert(objects==old && owner.pool.count==tables && owner.registry.issued==issued);
 uint64_t va=bo[7]->gpu_va,left=pte(&owner.pool,va-4096),right=pte(&owner.pool,va+10485760);
 assert(smmu_registry_reclaim(&owner,bo[7],true));
 for(unsigned off=0;off<10485760;off+=4096)assert(!pte(&owner.pool,va+off));
 assert(pte(&owner.pool,va-4096)==left && pte(&owner.pool,va+10485760)==right);
 struct waffle_gpu_memory *again=smmu_registry_new(&owner,10485760,WAFFLE_GPU_BO_WC);
 assert(again==bo[7] && again->gpu_va==va && again->serial==issued+1 && owner.registry.used==201326592);
 for(unsigned off=0;off<10485760;off+=4096)assert((pte(&owner.pool,va+off)&PTE_ADDRESS)==waffle_gpu_memory_page(again,off));
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==21 && live_released==1 && storage_frees==1);
 reset_owner(&owner);
 struct waffle_gpu_memory *largest=smmu_registry_new(&owner,201326592,WAFFLE_GPU_BO_WC|2);
 assert(largest && owner.registry.used==201326592 && owner.pool.count<=160);
 for(unsigned off=0;off<201326592;off+=4096) {
  uint64_t e=pte(&owner.pool,largest->gpu_va+off);
  assert((e&PTE_ADDRESS)==waffle_gpu_memory_page(largest,off) && (e&0xc3)==0xc3);
 }
 old=objects;issued=owner.registry.issued;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC) && objects==old && owner.registry.issued==issued);
 assert(smmu_registry_reclaim(&owner,largest,true) && !owner.registry.used);
 for(unsigned off=0;off<201326592;off+=4096)assert(!pte(&owner.pool,WAFFLE_GPU_BO_VA_BASE+off));
 struct waffle_gpu_memory *ten=smmu_registry_new(&owner,10485760,WAFFLE_GPU_BO_WC);
 struct waffle_gpu_memory *twelve=smmu_registry_new(&owner,12582912,WAFFLE_GPU_BO_WC|2);
 assert(ten && twelve && owner.registry.used==23068672);
 assert(twelve->gpu_va>=ten->gpu_va+ten->allocation_bytes);
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==3 && live_released==1 && storage_frees==1);
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    mapping = re.sub(r'#define TABLE_LIMIT \d+', '#define TABLE_LIMIT 160', ns['ns']['parts']['mapping'])
    h = ns['h'].replace('memory[64][16384]', 'memory[160][16384]').replace('allocated<64', 'allocated<160')
    # Mock allocator has discontiguous pages; reserve 32 MiB per synthetic
    # object so the larger allocation cannot alias its neighbor in the model.
    extra = ns['extra'].replace('bo->object*0x1000000ULL', 'bo->object*0x2000000ULL')
    (path/'test.c').write_text(h+mapping+ns['types']+ns['ns']['parts']['dynamic']+extra+test)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-Wno-misleading-indentation', '-fsanitize=address,undefined',
                    '-I', str(root/'kernel/files/bsd/sys'), str(path/'test.c'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
print('PASS actual registry/SMMU 19x10MiB+2MiB and single192MiB, then10+12MiB reuse: unchanged heap/VA/slots, every PTE/AP, full-budget/oversize refusal, cross-table revoke/reuse and teardown. Mock backing/GPU only.')
