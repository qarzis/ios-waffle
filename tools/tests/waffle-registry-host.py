"""General BO registry tested with actual logical/allocated sizes from GL trace."""
from pathlib import Path
import json,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
trace=root/'work/waffle/gpu/forensic-audit/gl-context-r3/msm-requests.jsonl'
rows=[json.loads(l) for l in trace.read_text().splitlines()]
# Keep the13 actual BOs referenced by the captured real GL submit, choose each
# handle's last successful allocation in that fd (initial capability probes reuse1).
submit=next(r for r in rows if r.get('nr')==0x46);requests=[]
for bo in submit['buffers']:
 r=[v for v in rows if v.get('nr')==0x42 and v['fd']==submit['fd'] and v['handle']==bo['handle']][-1]
 # Cached-coherent is explicitly unsupported; Mesa may fall back to WC.
 flags=0x20000|(r['flags']&2);requests.append((r['size'],flags))
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_gpu_registry.h"
static struct waffle_gpu_memory entries[WAFFLE_GPU_BO_LIMIT];
static unsigned mode,allocs,frees,pages,cleans,tlbs,idles;
static bool idle(void *p){assert(p==(void *)1);idles++;return mode!=1;}
static bool vacant(void *p,uint64_t a){assert(p==(void *)1 && a>=0x100000000ULL && a<WAFFLE_GPU_BO_VA_BASE+WAFFLE_GPU_BO_VA_BYTES);return mode!=2;}
static bool page(void *p,uint64_t a,uint64_t pa,bool ro){assert(p==(void *)1 && !(a&4095) && !(pa&4095));(void)ro;pages++;return mode!=4 || pages!=2;}
static void clean(void *p){assert(p==(void *)1);cleans++;}
static bool tlb(void *p){assert(p==(void *)1);tlbs++;return mode!=5;}
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *bo){if(mode==3)return false;allocs++;*bo=(struct waffle_gpu_memory){.object=allocs,.bytes=bytes,.allocation_bytes=(bytes+16383)&~16383,.flags=flags};return true;}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){assert(bo->object && off<bo->allocation_bytes);return 0x1000000+bo->object*0x1000000+off*2;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){assert(detached && bo->object);frees++;memset(bo,0,sizeof(*bo));return true;}
int main(void){
 const struct waffle_gpu_registry_ops ops={idle,vacant,page,clean,tlb,(void *)1};
 for(mode=0;mode<=5;mode++){
  struct waffle_gpu_registry r={.buffers=entries};allocs=frees=pages=cleans=tlbs=idles=0;
  struct waffle_gpu_memory *bo=waffle_gpu_registry_new(&r,&ops,8192,WAFFLE_GPU_BO_WC);
  assert((bo!=0)==(mode==0));
  if(mode<=3 && mode)assert(!r.count && !allocs && !pages && !r.poisoned);
  if(mode>=4){assert(r.count==1 && r.poisoned && !frees);unsigned old=allocs;assert(!waffle_gpu_registry_new(&r,&ops,4096,WAFFLE_GPU_BO_WC) && allocs==old);}
  assert(!waffle_gpu_registry_destroy(&r,false));
  assert(waffle_gpu_registry_destroy(&r,true));assert(frees==allocs && !r.count && !r.poisoned);
 }
 mode=0;struct waffle_gpu_registry r={.buffers=entries};allocs=frees=pages=cleans=tlbs=idles=0;
 uint64_t previous_end=WAFFLE_GPU_BO_VA_BASE;
'''
body='\n'.join(f'{{struct waffle_gpu_memory *bo=waffle_gpu_registry_new(&r,&ops,{size}u,{flags}u);assert(bo && bo->gpu_va==previous_end && bo->bytes=={size}u);previous_end+=bo->allocation_bytes;}}' for size,flags in requests)
t=r'''
 assert(r.count==13 && allocs==13 && tlbs==13 && cleans==13 && r.used<WAFFLE_GPU_BO_HEAP_BYTES);
 unsigned old_allocs=allocs;
 assert(!waffle_gpu_registry_new(&r,&ops,4096,0x80000) && allocs==old_allocs);
 assert(!waffle_gpu_registry_new(&r,&ops,WAFFLE_GPU_BO_MAX_BYTES+1,WAFFLE_GPU_BO_WC));
 assert(!waffle_gpu_registry_destroy(&r,false) && !frees);
 assert(waffle_gpu_registry_destroy(&r,true) && frees==13);
 /* Both slot and heap exhaustion refuse without allocating/reusing any VA. */
 r.buffers=entries;r.count=WAFFLE_GPU_BO_LIMIT;
 for(unsigned i=0;i<WAFFLE_GPU_BO_LIMIT;i++)entries[i].object=i+1;
 assert(!waffle_gpu_registry_new(&r,&ops,4096,WAFFLE_GPU_BO_WC) && allocs==old_allocs);
 memset(entries,0,sizeof(entries));r.count=0;r.used=WAFFLE_GPU_BO_HEAP_BYTES;
 assert(!waffle_gpu_registry_new(&r,&ops,4096,WAFFLE_GPU_BO_WC));return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+body+t);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('General BO registry:13 real GL BO requests replayed,unique64bit VAs/32MiB budget/pagewise permissions, idle/vacancy/allocation/partial-map/TLB failures and detach-only reclamation; host only')
