"""Actual 4KiB GPU IOVA spans backed by separately owned 16KiB CPU pages."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2];ns={'__file__':str(root/'tools/tests/waffle-reclaim-host.py')}
s=(root/'tools/tests/waffle-reclaim-host.py').read_text();exec(s[:s.index('test=r')],ns)
code=ns['code'].replace('for(unsigned off=0;off<bo->allocation_bytes;off+=4096)assert(!ptes','for(unsigned off=0;off<waffle_gpu_memory_gpu_bytes(bo);off+=4096)assert(!ptes')
t=r'''
int main(void){
 reset_all();struct waffle_gpu_registry r={.buffers=entries};
 auto_unused:;
 struct waffle_gpu_memory *a=waffle_gpu_registry_new(&r,&base,4096,WAFFLE_GPU_BO_WC);
 struct waffle_gpu_memory *b=waffle_gpu_registry_new(&r,&base,4096,WAFFLE_GPU_BO_WC);
 struct waffle_gpu_memory *c=waffle_gpu_registry_new(&r,&base,8192,WAFFLE_GPU_BO_WC|2);
 assert(a&&b&&c&&r.used==49152);uint64_t dest=WAFFLE_GPU_BO_VA_BASE+r.used;
 assert(waffle_gpu_registry_relocate(&r,&ops,a,dest,true));
 assert(waffle_gpu_registry_relocate(&r,&ops,b,dest+4096,true));
 assert(waffle_gpu_registry_relocate(&r,&ops,c,dest+8192,true));
 assert(a->mapped_bytes==4096 && b->mapped_bytes==4096 && c->mapped_bytes==8192 && r.used==49152);
 assert(owns((void*)1,dest,waffle_gpu_memory_page(a,0),false));
 assert(owns((void*)1,dest+4096,waffle_gpu_memory_page(b,0),false));
 assert(owns((void*)1,dest+8192,waffle_gpu_memory_page(c,0),true));
 assert(owns((void*)1,dest+12288,waffle_gpu_memory_page(c,4096),true));
 assert(vacant((void*)1,dest+16384));
 unsigned before=cleared;assert(!waffle_gpu_registry_relocate(&r,&ops,c,dest,true)&&cleared==before&&!r.poisoned);
 struct waffle_gpu_memory *d=waffle_gpu_registry_new(&r,&base,4096,WAFFLE_GPU_BO_WC);
 assert(d && d->gpu_va!=dest && d->allocation_bytes==16384 && !d->mapped_bytes && r.used==65536);
 assert(waffle_gpu_registry_reclaim(&r,&ops,b,true)&&r.used==49152);
 assert(owns((void*)1,dest,waffle_gpu_memory_page(a,0),false)&&owns((void*)1,dest+8192,waffle_gpu_memory_page(c,0),true));
 assert(waffle_gpu_registry_reclaim(&r,&ops,a,true));assert(waffle_gpu_registry_reclaim(&r,&ops,c,true));assert(r.used==16384);
 assert(waffle_gpu_registry_destroy(&r,true)&&frees==objects);
 /* Shrink in place frees the tail PTEs without freeing CPU backing. */
 reset_all();r=(struct waffle_gpu_registry){.buffers=entries};a=waffle_gpu_registry_new(&r,&base,4096,WAFFLE_GPU_BO_WC);uint64_t va=a->gpu_va;
 assert(waffle_gpu_registry_relocate(&r,&ops,a,va,true)&&a->mapped_bytes==4096);
 for(unsigned off=4096;off<16384;off+=4096)assert(vacant((void*)1,va+off));
 b=waffle_gpu_registry_new(&r,&base,8192,WAFFLE_GPU_BO_WC);assert(waffle_gpu_registry_relocate(&r,&ops,b,va+4096,true));assert(r.used==32768);
 assert(waffle_gpu_registry_reclaim(&r,&ops,b,true)&&waffle_gpu_registry_reclaim(&r,&ops,a,true));assert(!r.used&&waffle_gpu_registry_destroy(&r,true));
 /* Shift into the BO's own old rounded range; old ownership is prevalidated. */
 reset_all();r=(struct waffle_gpu_registry){.buffers=entries};a=waffle_gpu_registry_new(&r,&base,8192,WAFFLE_GPU_BO_WC);va=a->gpu_va;
 assert(waffle_gpu_registry_relocate(&r,&ops,a,va+4096,true)&&a->mapped_bytes==8192&&!ptes[slot(va)]&&!ptes[slot(va+12288)]);
 assert(waffle_gpu_registry_reclaim(&r,&ops,a,true)&&!r.used);assert(waffle_gpu_registry_destroy(&r,true));
 /* Native read-only shader BO: validate old RW leaves, publish RO leaves,
  * then reclaim using the new permission without touching other mappings. */
 reset_all();r=(struct waffle_gpu_registry){.buffers=entries};a=waffle_gpu_registry_new(&r,&base,4096,WAFFLE_GPU_BO_WC);va=a->gpu_va;
 assert(waffle_gpu_registry_relocate_access(&r,&ops,a,va+4096,true,true));
 assert((a->flags&WAFFLE_GPU_BO_READONLY)&&a->mapped_bytes==4096&&owns((void*)1,va+4096,waffle_gpu_memory_page(a,0),true));
 assert(waffle_gpu_registry_reclaim(&r,&ops,a,true)&&!r.used);assert(waffle_gpu_registry_destroy(&r,true));
 return 0;
}
'''.replace(' auto_unused:;','')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual 4KiB/8KiB adjacent IOVAs, independent16KiB backing budget, ordinary allocation collision avoidance, readonly neighbors, exact reclaim, shrink-in-place and self-overlap; PTE/GPU callbacks modeled')
