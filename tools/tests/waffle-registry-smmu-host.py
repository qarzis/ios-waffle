"""Actual general-BO registry adapter and real SMMU page tables, no GPU model claim."""
from pathlib import Path
import subprocess,tempfile,re,json
root=Path(__file__).resolve().parents[2];parts={}
s=(root/'tools/tests/waffle-dynamic-bo-host.py').read_text();exec(s[:s.index('with tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-dynamic-bo-host.py')},parts)
h=parts['harness'].replace('after_start_allocs==1','after_start_allocs>=1')
h=re.sub(r'^bool waffle_gpu_memory_create.*$','',h,flags=re.M);h=re.sub(r'^uint64_t waffle_gpu_memory_page.*$','',h,flags=re.M);h=re.sub(r'^bool waffle_gpu_memory_destroy.*$','',h,flags=re.M)
h+=r'''
static unsigned objects,reclaimed;
bool waffle_gpu_memory_create(uint64_t b,uint32_t f,struct waffle_gpu_memory *bo){objects++;*bo=(struct waffle_gpu_memory){.object=objects,.bytes=b,.allocation_bytes=(b+16383)&~16383,.flags=f};return true;}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){assert(bo->object && off<bo->allocation_bytes);return 0x20000000+bo->object*0x1000000+off*2;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool d){assert(d && bo->object);reclaimed++;memset(bo,0,sizeof(*bo));return true;}
'''
rows=[json.loads(l) for l in (root/'work/waffle/gpu/forensic-audit/gl-context-r3/msm-requests.jsonl').read_text().splitlines()];sub=next(r for r in rows if r.get('nr')==0x46);requests=[]
for b in sub['buffers']:
 r=[r for r in rows if r.get('nr')==0x42 and r['handle']==b['handle'] and r['fd']==sub['fd']][-1];requests.append((r['size'],0x20000|(r['flags']&2)))
t=r'''
int main(void){
 struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;
 assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;
'''
for b,f in requests:
 t+=f'''{{struct waffle_gpu_memory *bo=smmu_registry_new(&owner,{b}u,{f}u);assert(bo && bo->published);for(unsigned off=0;off<bo->allocation_bytes;off+=4096){{uint64_t e=pte(&owner.pool,bo->gpu_va+off);assert((e&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (e&0xc3)=={hex(0xc3 if f&2 else 0x43)});}}}}
'''
t+=r'''
 assert(owner.registry.count==13 && objects==13 && !reclaimed && tlbs==26 && owner.pool.count<=16);
 unsigned old=objects;mode=2;assert(!smmu_registry_new(&owner,4096,WAFFLE_GPU_BO_WC) && objects==old);mode=0;
 assert(!waffle_gpu_registry_destroy(&owner.registry,false) && !reclaimed);
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && reclaimed==13);
 /* Exact low-level failure retains backing; parent must detach before free. */
 for(unsigned failure=0;failure<2;failure++){
  allocated=objects=reclaimed=tlbs=cleans=after_start_allocs=0;live=false;memset(&owner,0,sizeof(owner));owner.compute_image=13;owner.child=&child;owner.permission_context=(struct pool_permission_context){.cb=1,.lpac_cb=2,.tables=&owner.pool};
  assert(new_table(&owner.pool));live=true;mode=failure?7:1;
  if(!setjmp(reset_trap)){(void)smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC);assert(0);}
  assert(owner.registry.poisoned && owner.registry.count==1 && objects==1 && !reclaimed);
  mode=0;assert(waffle_gpu_registry_destroy(&owner.registry,true) && reclaimed==1);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+parts['mapping']+parts['types']+parts['dynamic']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual SMMU registry adapter:13 real GL sizes/flags, all noncontiguous4KiB PTEs/AP/read-only bits,26 GPU/LPAC TLB syncs, table-allocation/TLB failure retention and detach-only release; host only')
