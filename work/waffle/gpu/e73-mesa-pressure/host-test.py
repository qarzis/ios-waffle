from pathlib import Path
import subprocess,tempfile
source=Path('xnu-deps/build/mesa/mesa-26.3.0-rc1/src/freedreno/drm/freedreno_bo.c').read_text()
a=source.index('static struct fd_bo *\nbo_new(');b=source.index('{',a);depth=1;i=b+1
while depth:
 depth+=(source[i]=='{')-(source[i]=='}');i+=1
function=source[a:i]
preamble=r'''
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define FD_BO_HEAP_BLOCK_SIZE 4096
#define _FD_BO_HINTS 0xf000
#define RING_FLAGS 2
#define FD_BO_CACHED_COHERENT 16
#define FD_ALLOC_NONE 0
#define FD_ALLOC_ACTIVE 1
struct fd_bo {uint32_t handle,alloc_flags;};
struct fd_bo_cache {int id;};
struct fd_device;
struct funcs {struct fd_bo *(*bo_new)(struct fd_device *,uint32_t,uint32_t);};
struct fd_device {void *default_heap,*ring_heap;bool has_cached_coherent;struct fd_bo_cache bo_cache,ring_cache;struct funcs *funcs;void *handle_table;};
static int table_lock,locked,locks,purges,attempts,inserts,mode,cached;
static unsigned mask;
static struct fd_bo object;
static void simple_mtx_lock(int *p){assert(p==&table_lock && !locked);locked=1;locks++;}
static void simple_mtx_unlock(int *p){assert(p==&table_lock && locked);locked=0;}
static struct fd_bo *fd_bo_heap_alloc(void *p,uint32_t s,uint32_t f){(void)p;(void)s;(void)f;assert(0);return 0;}
static struct fd_bo *fd_bo_cache_alloc(struct fd_bo_cache *c,uint32_t *s,uint32_t f){(void)c;(void)s;(void)f;return cached?&object:0;}
static void fd_bo_cache_cleanup(struct fd_bo_cache *c,int t){assert(!locked && t==0);simple_mtx_lock(&table_lock);simple_mtx_unlock(&table_lock);purges++;mask|=1u<<c->id;}
static void _mesa_hash_table_insert(void *t,uint32_t *h,struct fd_bo *b){(void)t;assert(locked && h==&object.handle && b==&object);inserts++;}
static void fd_alloc_log(struct fd_bo *b,int from,int to){assert(b==&object && from==FD_ALLOC_NONE && to==FD_ALLOC_ACTIVE);}
static struct fd_bo *backend(struct fd_device *d,uint32_t size,uint32_t flags){(void)d;(void)flags;assert(!locked && size==4194304);attempts++;return mode==1 || (mode==0 && attempts==2 && mask==6)?&object:0;}
static void reset(void){locked=locks=purges=attempts=inserts=cached=mode=0;mask=0;object=(struct fd_bo){42,0};unsetenv("WAFFLE_GPU_DRM");unsetenv("WAFFLE_GPU_RECLAIM_ON_OOM");}
'''
tests=r'''
int main(void){struct funcs f={backend};struct fd_device d={.has_cached_coherent=true,.bo_cache={1},.ring_cache={2},.funcs=&f};
reset();assert(!bo_new(&d,4194304,3,&d.bo_cache));assert(attempts==1 && !purges && !locks && !inserts);
reset();setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","0",1);assert(!bo_new(&d,4194304,3,&d.bo_cache));assert(attempts==1 && !purges);
reset();setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","1",1);assert(bo_new(&d,4194304,3,&d.bo_cache)==&object);assert(attempts==2 && purges==2 && locks==3 && inserts==1 && object.alloc_flags==3 && !locked);
reset();mode=2;setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","1",1);assert(!bo_new(&d,4194304,3,&d.bo_cache));assert(attempts==2 && purges==2 && locks==2 && !inserts && !locked);
reset();mode=1;setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","1",1);assert(bo_new(&d,4194304,3,&d.bo_cache)==&object);assert(attempts==1 && !purges && locks==1 && inserts==1);
reset();cached=1;setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","1",1);assert(bo_new(&d,4194304,3,&d.bo_cache)==&object);assert(!attempts && !purges && !locks && !inserts);
reset();setenv("WAFFLE_GPU_DRM","1",1);setenv("WAFFLE_GPU_RECLAIM_ON_OOM","1",1);assert(bo_new(&d,4194304,RING_FLAGS,&d.ring_cache)==&object);assert(attempts==2 && purges==2 && !locked);return 0;}
'''
with tempfile.TemporaryDirectory(prefix='waffle-bo-pressure-') as directory:
 p=Path(directory);(p/'test.c').write_text(preamble+function+tests);subprocess.run(['cc','-std=c11','-D__APPLE__','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual Mesa bo_new: disabled policy preserved, both caches purged without holding table lock; simulated destructor can lock it, one bounded retry, permanent failure preserved, success/cache-hit fast paths unchanged, ring path covered. Host only.')
