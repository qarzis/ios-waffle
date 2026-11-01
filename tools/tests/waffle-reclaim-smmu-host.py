"""E55 actual SMMU leaf/dual-ASID adapter; owner API tested separately."""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
s=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h']
for signature in ['uint64_t waffle_gpu_memory_page','bool waffle_gpu_memory_destroy']:
 h=re.sub(r'^'+signature+r'.*$','',h,flags=re.M)
h=h.replace('return !(mode==7 && cb==2);','return !(mode==7 && cb==2) && !(mode==15 && cb==1);')
types=ns['parts']['types'].replace('return mode!=2;','return mode!=2 && !(mode==17 && tlbs>=2);')
ledger=json.loads((root/'work/waffle/gpu/forensic-audit/E54-memory-timeline.json').read_text())
fixture='static const uint64_t events[][5]={'+','.join(
 '{%d,%d,%d,%d,%dULL}'%((e['kind']=='new'),e['handle'],e.get('bytes',0),e.get('flags',0),e.get('VA',0))
 for e in ledger['events'])+'};\n'
extra=r'''
static unsigned released,live_released,page_calls;
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){
 assert(bo->object && off<bo->allocation_bytes);page_calls++;
 if(mode==16 && page_calls==10){
  uint64_t *entry=smmu_registry_leaf(&active->pool,bo->gpu_va+off);assert(entry);*entry^=4096;
 }
 return 0x20000000ULL+bo->object*0x1000000ULL+off*2;
}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){
 assert(bo->object && !storage_frees);
 if(!detached){
  assert(!bo->published && tlbs>=2 && cleans);
  for(unsigned off=0;off<bo->allocation_bytes;off+=4096)assert(!pte(&active->pool,bo->gpu_va+off));
  live_released++;
 }
 released++;memset(bo,0,sizeof(*bo));return true;
}
static void reset_owner(struct smmu_owner *s){
 mode=allocated=objects=after_start_allocs=cleans=tlbs=storage_allocs=storage_frees=released=live_released=page_calls=0;
 live=false;memset(s,0,sizeof(*s));s->compute_image=13;s->child=&child;
 s->permission_context=(struct pool_permission_context){.cb=1,.lpac_cb=2,.tables=&s->pool};active=s;
 for(unsigned i=0;i<25;i++)assert(new_table(&s->pool));live=true;
}
'''
test=r'''
int main(void){
 const unsigned failures[]={0,2,7,15,16,17,18};
 for(unsigned n=0;n<sizeof(failures)/sizeof(failures[0]);n++){
  struct smmu_owner owner;reset_owner(&owner);
  struct waffle_gpu_memory *a=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC);
  struct waffle_gpu_memory *b=smmu_registry_new(&owner,32768,WAFFLE_GPU_BO_WC|2);
  struct waffle_gpu_memory *c=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC);
  assert(a && b && c);uint64_t va=b->gpu_va;
  uint64_t pa_a=pte(&owner.pool,a->gpu_va),pa_c=pte(&owner.pool,c->gpu_va);
  unsigned tables=owner.pool.count;cleans=tlbs=page_calls=0;
  assert(!smmu_registry_reclaim(&owner,b,false) && !released && !tlbs);
  uintptr_t lpac=owner.permission_context.lpac_cb;owner.permission_context.lpac_cb=0;
  assert(!smmu_registry_reclaim(&owner,b,true) && !released && !tlbs);owner.permission_context.lpac_cb=lpac;
  mode=failures[n];
  uint64_t *bad=smmu_registry_leaf(&owner.pool,va+7*4096);
  if(mode==18)*bad^=1ULL<<7; /* A wrong AP permission must block all clearing. */
  bool ok=smmu_registry_reclaim(&owner,b,true);
  assert(ok==(mode==0));
  if(ok){
   assert(!b->object && owner.registry.used==32768 && live_released==1 && tlbs==2);
   struct waffle_gpu_memory *d=smmu_registry_new(&owner,32768,WAFFLE_GPU_BO_WC);
   assert(d && d->gpu_va==va && d==&owner.registry.buffers[3]);
   for(unsigned off=0;off<d->allocation_bytes;off+=4096){
    uint64_t entry=pte(&owner.pool,va+off);
    assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(d,off) && (entry&0xc3)==0x43);
   }
  }else{
   assert(b->object && b->published && !released && owner.registry.used==65536);
   if(mode==2 || mode==18){assert(!owner.registry.poisoned && !tlbs);}
   else{assert(owner.registry.poisoned);if(mode!=16)assert(tlbs==2);}
  }
  assert(pte(&owner.pool,a->gpu_va)==pa_a && pte(&owner.pool,c->gpu_va)==pa_c);
  assert(owner.pool.count==tables && !storage_frees);
  mode=0;assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects && storage_frees==1);
 }
 for(unsigned reclaim=0;reclaim<2;reclaim++){
  struct smmu_owner owner;reset_owner(&owner);
  for(unsigned i=0;i<sizeof(events)/sizeof(events[0]);i++){
   const uint64_t *e=events[i];
   if(e[0]){
    struct waffle_gpu_memory *bo=smmu_registry_new(&owner,e[2],e[3]);assert(bo && owner.registry.count==e[1]);
    if(!reclaim)assert(bo->gpu_va==e[4]);
    for(unsigned off=0;off<bo->allocation_bytes;off+=4096){
     uint64_t entry=pte(&owner.pool,bo->gpu_va+off);
     assert((entry&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (entry&0xc3)==((bo->flags&2)?0xc3:0x43));
    }
   }else if(reclaim)assert(smmu_registry_reclaim(&owner,&owner.registry.buffers[e[1]-1],true));
  }
  assert(owner.registry.count==800 && owner.registry.used==(reclaim?60080128:67108864));
  struct waffle_gpu_memory *next=smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC|2);
  assert((next!=NULL)==(reclaim!=0));
  assert(owner.pool.count<=64 && live_released==(reclaim?10:0));
  assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==objects && storage_frees==1);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
 header=re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*','#define WAFFLE_GPU_BO_HEAP_BYTES 67108864u',header)
 (p/'waffle_gpu_memory.h').write_text(header)
 for name in ['waffle_gpu_registry.h','waffle_gpu_reclaim.h']:(p/name).write_text((root/'kernel/files/bsd/sys'/name).read_text())
 mapping=re.sub(r'#define TABLE_LIMIT \d+','#define TABLE_LIMIT 64',ns['parts']['mapping'])
 (p/'test.c').write_text(h+mapping+types+ns['parts']['dynamic']+extra+fixture+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
  '-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual SMMU adapter:owned PA/AP leaf validation,clear+clean+both-ASID sync before release;busy/CPU-mapped/absent-LPAC/AP-corrupt/changed-PTE/GPU-TLB/LPAC-TLB/post-idle failures retain backing; revoked-hole replacement preserves neighbors and new PA/AP. Exact800 allocations/10closes fit unchanged64MiB/64tables after25 bootstrap and admit next16KiB only with eligible reclaim. Owner API tested separately; no actual GPU claim.')
