"""E55 generic lifetime/allocator model; SMMU/owner paths tested separately."""
from pathlib import Path
import json,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ledger=json.loads((root/'work/waffle/gpu/forensic-audit/E54-memory-timeline.json').read_text())
fixture='static const uint64_t events[][5]={'+','.join(
 '{%d,%d,%d,%d,%dULL}'%((1 if e['kind']=='new' else 0),e['handle'],e.get('bytes',0),e.get('flags',0),e.get('VA',0))
 for e in ledger['events'])+'};\n'
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_gpu_reclaim.h"
static struct waffle_gpu_memory entries[WAFFLE_GPU_BO_LIMIT];
static uint64_t ptes[WAFFLE_GPU_BO_HEAP_BYTES/4096];
static unsigned mode,objects,frees,cleans,tlbs,owned_checks,cleared;
static bool after_tlb,gpu_ok,lpac_ok;
static unsigned slot(uint64_t address){assert(address>=WAFFLE_GPU_BO_VA_BASE && address<WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_HEAP_BYTES && !(address&4095));return (address-WAFFLE_GPU_BO_VA_BASE)/4096;}
static bool idle(void *p){assert(p==(void *)1);return mode!=1 && !(mode==6 && after_tlb);}
static bool vacant(void *p,uint64_t address){assert(p==(void *)1);return !ptes[slot(address)];}
static bool page(void *p,uint64_t address,uint64_t pa,bool ro){assert(p==(void *)1 && !ptes[slot(address)]);ptes[slot(address)]=pa|0x43|(ro?0x80:0);return true;}
static void clean(void *p){assert(p==(void *)1);cleans++;}
static bool tlb(void *p){assert(p==(void *)1);tlbs++;gpu_ok=mode!=4;tlbs++;lpac_ok=mode!=5;after_tlb=true;return gpu_ok && lpac_ok;}
static bool owns(void *p,uint64_t address,uint64_t pa,bool ro){assert(p==(void *)1);owned_checks++;return !(mode==2 && owned_checks==8) && ptes[slot(address)]==(pa|0x43|(ro?0x80:0));}
static bool unmap(void *p,uint64_t address,uint64_t pa,bool ro){assert(p==(void *)1);cleared++;if(mode==3 && cleared==2)return false;assert(ptes[slot(address)]==(pa|0x43|(ro?0x80:0)));ptes[slot(address)]=0;return true;}
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *bo){
 *bo=(struct waffle_gpu_memory){.object=++objects,.bytes=bytes,.allocation_bytes=(bytes+16383)&~16383,.flags=flags};return true;
}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){assert(bo->object && off<bo->allocation_bytes);return 0x10000000ULL+bo->object*0x1000000ULL+off*2;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){
 assert(bo && bo->object);
 if(!detached){
  assert(!bo->published && gpu_ok && lpac_ok && cleans);
  for(unsigned off=0;off<bo->allocation_bytes;off+=4096)assert(!ptes[slot(bo->gpu_va+off)]);
  if(mode==7)return false;
 }
 frees++;memset(bo,0,sizeof(*bo));return true;
}
static void reset_phase(void){after_tlb=gpu_ok=lpac_ok=false;cleans=tlbs=owned_checks=cleared=0;}
static void reset_all(void){mode=objects=frees=0;memset(entries,0,sizeof(entries));memset(ptes,0,sizeof(ptes));reset_phase();}
static const struct waffle_gpu_registry_ops base={idle,vacant,page,clean,tlb,(void *)1};
static const struct waffle_gpu_reclaim_ops ops={&base,owns,unmap};
'''
test=r'''
int main(void){
 for(unsigned failure=0;failure<=7;failure++){
  reset_all();struct waffle_gpu_registry r={.buffers=entries};
  struct waffle_gpu_memory *a=waffle_gpu_registry_new(&r,&base,16384,WAFFLE_GPU_BO_WC);
  struct waffle_gpu_memory *b=waffle_gpu_registry_new(&r,&base,32768,WAFFLE_GPU_BO_WC|2);
  struct waffle_gpu_memory *c=waffle_gpu_registry_new(&r,&base,16384,WAFFLE_GPU_BO_WC);
  assert(a && b && c && r.used==65536);uint64_t bva=b->gpu_va;
  uint64_t neighbor0=ptes[slot(a->gpu_va)],neighbor1=ptes[slot(c->gpu_va)];
  reset_phase();struct waffle_gpu_memory fake=*b;
  assert(!waffle_gpu_registry_reclaim(&r,&ops,&fake,true) && !owned_checks && !cleared);
  assert(!waffle_gpu_registry_reclaim(&r,&ops,b,false) && !owned_checks && !cleared);
  mode=failure;
  bool ok=waffle_gpu_registry_reclaim(&r,&ops,b,true);
  assert(ok==(failure==0));
  if(failure==0){
   assert(!b->object && r.used==32768 && frees==1 && cleared==8 && tlbs==2 && !r.poisoned);
   struct waffle_gpu_memory *d=waffle_gpu_registry_new(&r,&base,32768,WAFFLE_GPU_BO_WC);
   assert(d && d->gpu_va==bva && d==&entries[3] && r.used==65536);
   assert(!waffle_gpu_registry_reclaim(&r,&ops,b,true));
  }else{
   assert(b->object && r.used==65536 && !frees);
   if(failure<=2)assert(!cleared && !r.poisoned);
   else{
    assert(r.poisoned);
    assert(!waffle_gpu_registry_new(&r,&base,16384,WAFFLE_GPU_BO_WC));
    if(failure>=4)assert(tlbs==2);
   }
  }
  assert(ptes[slot(a->gpu_va)]==neighbor0 && ptes[slot(c->gpu_va)]==neighbor1);
  assert(!waffle_gpu_registry_destroy(&r,false));
  mode=0;assert(waffle_gpu_registry_destroy(&r,true) && frees==objects);
 }
 /* Replay all800 measured allocations/10closes. Retention reproduces exact
  * first failure; hypothetical eligible reclamation admits the next16KiB. */
 for(unsigned reclaim=0;reclaim<2;reclaim++){
  reset_all();struct waffle_gpu_registry r={.buffers=entries};
  for(unsigned i=0;i<sizeof(events)/sizeof(events[0]);i++){
   const uint64_t *event=events[i];
   if(event[0]){
    struct waffle_gpu_memory *bo=waffle_gpu_registry_new(&r,&base,event[2],event[3]);
    assert(bo && r.count==event[1]);
    if(!reclaim)assert(bo->gpu_va==event[4]);
    for(unsigned off=0;off<bo->allocation_bytes;off+=4096)
     assert(ptes[slot(bo->gpu_va+off)]==(waffle_gpu_memory_page(bo,off)|0x43|((bo->flags&2)?0x80:0)));
   }else if(reclaim){reset_phase();assert(waffle_gpu_registry_reclaim(&r,&ops,&entries[event[1]-1],true));}
  }
  assert(r.count==800 && r.used==(reclaim?60080128:67108864));
  struct waffle_gpu_memory *next=waffle_gpu_registry_new(&r,&base,16384,WAFFLE_GPU_BO_WC|2);
  assert((next!=NULL)==(reclaim!=0));
  if(reclaim)assert(r.count==801 && r.used==60096512 && frees==10);
  assert(waffle_gpu_registry_destroy(&r,true) && frees==objects);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 header=(root/'kernel/files/bsd/sys/waffle_gpu_memory.h').read_text()
 header=re.sub(r'#define WAFFLE_GPU_BO_HEAP_BYTES .*','#define WAFFLE_GPU_BO_HEAP_BYTES 67108864u',header)
 header=re.sub(r'#define WAFFLE_GPU_BO_VA_BYTES .*','#define WAFFLE_GPU_BO_VA_BYTES 67108864u',header)
 (p/'waffle_gpu_memory.h').write_text(header)
 for name in ['waffle_gpu_registry.h','waffle_gpu_reclaim.h']:(p/name).write_text((root/'kernel/files/bsd/sys'/name).read_text())
 (p/'test.c').write_text(code+fixture+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
  '-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST ONLY generic reclaim: CPU mapping/busy/foreign/ownership/partial-clear/GPU-TLB/LPAC-TLB/post-idle/release-failure retention; no free before both modeled TLB syncs; readonly/live-neighbor integrity, monotonic handle and revoked-hole reuse. All800 actual allocation sizes/10closes reproduce64MiB failure under retention and admit failed16KiB under hypothetical eligible reclamation. SMMU/owner paths tested separately; no hardware claim.')
