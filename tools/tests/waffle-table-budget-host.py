"""Replay actual GL allocation prefix after the observed25-table bootstrap."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2];parts={};s=(root/'tools/tests/waffle-dynamic-bo-host.py').read_text();exec(s[:s.index('with tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-dynamic-bo-host.py')},parts)
h=parts['harness'].replace('memory[16][16384]','memory[64][16384]').replace('allocated<16','allocated<64').replace('after_start_allocs==1','after_start_allocs>=1')
import re
for signature in ['bool waffle_gpu_memory_create','uint64_t waffle_gpu_memory_page','bool waffle_gpu_memory_destroy']:h=re.sub(r'^'+signature+r'.*$','',h,flags=re.M)
h+=r'''
static unsigned objects;
bool waffle_gpu_memory_create(uint64_t b,uint32_t f,struct waffle_gpu_memory *bo){objects++;*bo=(struct waffle_gpu_memory){.object=objects,.bytes=b,.allocation_bytes=(b+16383)&~16383,.flags=f};return true;}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){return 0x20000000+bo->object*0x1000000+off;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){assert(detached);memset(bo,0,sizeof(*bo));return true;}
'''
t=r'''
int main(void){
 struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;
 /* Hardware log: bootstrap consumes25 owned tables before general BOs. */
 for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));
 owner.permission_context.tables=&owner.pool;live=true;
 const unsigned sizes[]={16384,16384,4194304,16384,4194304,4194304,16384,16384,16384,16384,16384,16384,16384};
 if(setjmp(reset_trap)){
  assert(TABLE_LIMIT==32 && objects==6 && owner.registry.count==6 && owner.registry.poisoned && owner.pool.count==32);
  return 0;
 }
 for(unsigned i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++)assert(smmu_registry_new(&owner,sizes[i],WAFFLE_GPU_BO_WC));
 assert(TABLE_LIMIT>=64 && objects==13 && !owner.registry.poisoned && owner.pool.count==33);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 for limit in (32,64):
  mapping=re.sub(r'#define TABLE_LIMIT \d+','#define TABLE_LIMIT '+str(limit),parts['mapping'])
  (p/'test.c').write_text(h+mapping+parts['types']+parts['dynamic']+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('Actual SMMU table budget:25-table bootstrap+observedGLsizes reproduces32-table failure at6thBO;64-table bound admits13BOs using33tables; host only')
