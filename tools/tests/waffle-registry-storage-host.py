"""Actual registry metadata ownership, failure cleanup and full64MiB/min-BO bound."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
s=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h='static unsigned destroyed;\n'+ns['h']
h=h.replace('objects++;*bo=','if(mode==3)return false;objects++;*bo=')
h=h.replace('bo->object*0x1000000','bo->object*0x10000')
h=h.replace('assert(detached);memset(bo,0,sizeof(*bo));','assert(detached && !storage_frees);destroyed++;memset(bo,0,sizeof(*bo));')
t=r'''
static void reset_owner(struct smmu_owner *owner){
 allocated=objects=after_start_allocs=tlbs=cleans=storage_allocs=storage_frees=destroyed=0;
 live=false;mode=0;memset(owner,0,sizeof(*owner));
 owner->compute_image=13;owner->child=&child;
 owner->permission_context=(struct pool_permission_context){.cb=1,.lpac_cb=2,.tables=&owner->pool};active=owner;
 for(unsigned i=0;i<25;i++)assert(new_table(&owner->pool));live=true;
}
int main(void){
 struct smmu_owner owner;
 /* Descriptor allocation fails before any BO or PTE publication. */
 reset_owner(&owner);mode=14;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
 assert(!objects && !owner.registry.buffers && !storage_allocs && owner.pool.count==25);
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && !storage_frees);
 /* Empty metadata storage must still be released on a failed first BO. */
 reset_owner(&owner);mode=3;
 assert(!smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));
 assert(!objects && owner.registry.buffers && storage_allocs==1 && !storage_frees);
 assert(!waffle_gpu_registry_destroy(&owner.registry,false) && owner.registry.buffers && !storage_frees);
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && !owner.registry.buffers && storage_frees==1 && !destroyed);
 /* PTE and TLB failures retain BO backing and descriptor storage together. */
 for(unsigned failure=0;failure<2;failure++){
  reset_owner(&owner);assert(smmu_registry_prepare(&owner));mode=failure?7:1;
  if(!setjmp(reset_trap)){(void)smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC);assert(0);}
  assert(owner.registry.poisoned && objects==1 && !destroyed && !storage_frees);
  assert(!waffle_gpu_registry_destroy(&owner.registry,false) && !storage_frees);
  mode=0;assert(waffle_gpu_registry_destroy(&owner.registry,true));
  assert(destroyed==1 && storage_frees==1 && !owner.registry.buffers);
 }
 /* Physical residency and the fixed generation-handle slot ABI are separate. */
 reset_owner(&owner);
 assert((WAFFLE_GPU_BO_LIMIT==4096 && WAFFLE_GPU_BO_HEAP_BYTES==67108864) ||
        (WAFFLE_GPU_BO_LIMIT==8192 && (WAFFLE_GPU_BO_HEAP_BYTES==134217728 || WAFFLE_GPU_BO_HEAP_BYTES==201326592)));
 for(unsigned i=0;i<WAFFLE_GPU_BO_LIMIT;i++){
  struct waffle_gpu_memory *bo=smmu_registry_new(&owner,4096,WAFFLE_GPU_BO_WC);assert(bo);
  assert(bo==&owner.registry.buffers[i] && bo->allocation_bytes==16384);
  for(unsigned off=0;off<16384;off+=4096){
   uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
   assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==0x43);
  }
 }
 assert(objects==WAFFLE_GPU_BO_LIMIT && owner.registry.used==WAFFLE_GPU_BO_LIMIT*16384u && owner.registry.used<=WAFFLE_GPU_BO_HEAP_BYTES && storage_allocs==1 && !storage_frees && owner.pool.count<=TABLE_LIMIT);
 assert(!smmu_registry_new(&owner,4096,WAFFLE_GPU_BO_WC) && objects==WAFFLE_GPU_BO_LIMIT);
 assert(!waffle_gpu_registry_destroy(&owner.registry,false) && !destroyed && !storage_frees);
 assert(waffle_gpu_registry_destroy(&owner.registry,true));
 assert(destroyed==WAFFLE_GPU_BO_LIMIT && storage_frees==1 && !owner.registry.buffers && !owner.registry.count && !owner.registry.used);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);parts=ns['parts']
 for budget,limit,slots in [(67108864,64,4096),(134217728,128,8192),(201326592,160,8192)]:
  header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
  header=re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*',f'#define WAFFLE_GPU_BO_HEAP_BYTES {budget}u',header)
  header=re.sub(r'#define WAFFLE_GPU_BO_LIMIT .*',f'#define WAFFLE_GPU_BO_LIMIT {slots}u',header)
  (p/'waffle_gpu_memory.h').write_text(header)
  for name in ['waffle_gpu_registry.h','waffle_gpu_reclaim.h']:(p/name).write_text((root/'kernel/files/bsd/sys'/name).read_text())
  harness=h.replace('memory[64][16384]','memory[160][16384]').replace('allocated<64','allocated<160')
  mapping=re.sub(r'#define TABLE_LIMIT \d+',f'#define TABLE_LIMIT {limit}',parts['mapping'])
  (p/'test.c').write_text(harness+mapping+parts['types']+parts['dynamic']+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('Actual registry/SMMU metadata ownership:allocation/empty/partial-failure retention and BO-before-storage teardown; historical4096/64MiB and8192/128MiB plus current8192slots/192MiB pass minimum-BO slot exhaustion with unchanged generation capacity, stable offstack descriptors and synthetic36bit PTEs; host model only')
