"""Actual post-bootstrap mapper, real table walk/PTEs and dual-ASID publication."""
from pathlib import Path
import subprocess, tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/waffle_smmu.c').read_text()
mapping = source[source.index('#define TABLE_LIMIT'):source.index('static bool pool_permissions(')]
dynamic = source[source.index('static bool dynamic_bo_vacant('):source.index('struct waffle_smmu_owner {')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu_writeback.h"
#include "waffle_gpu_data.h"
#include "waffle_gpu_buffer.h"
#include "waffle_gpu_registry.h"
#include "waffle_gpu_reclaim.h"

bool waffle_gpu_memory_create(uint64_t b,uint32_t f,struct waffle_gpu_memory *m){(void)b;(void)f;(void)m;assert(0);return false;}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *m,uint32_t o){(void)m;(void)o;assert(0);return 0;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *m,bool d){(void)m;(void)d;assert(0);return false;}

typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
static _Alignas(16384) uint8_t memory[16][16384];
static unsigned allocated,mode,tlbs,cleans,binds,after_start_allocs;
static bool live;
static _Alignas(16384) unsigned char registry_storage[(WAFFLE_GPU_BO_LIMIT*sizeof(struct waffle_gpu_memory)+16383)&~16383u];
static unsigned storage_allocs,storage_frees;
static jmp_buf reset_trap;
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned bytes,unsigned flags,unsigned tag){assert(map==7 && flags==7 && tag==5);if(bytes>16384){assert(bytes==sizeof(registry_storage));if(mode==14)return 1;*out=(uintptr_t)registry_storage;memset(registry_storage,0,bytes);storage_allocs++;return 0;}assert(bytes==16384 && allocated<16);if(live && mode==1)return 1;*out=(uintptr_t)memory[allocated++];if(live)after_start_allocs++;memset((void *)*out,0,bytes);return 0;}
static void kmem_free(unsigned map,uintptr_t address,unsigned bytes){assert(map==7 && address && bytes);storage_frees++;}
static uint64_t kvtophys(uintptr_t p){for(unsigned i=0;i<allocated;i++)if(p>=(uintptr_t)memory[i] && p<(uintptr_t)memory[i]+16384){if(live && mode==6 && i==allocated-1 && p>=(uintptr_t)memory[i]+4096)return 1ULL<<36;return 0x10000000+i*16384+p-(uintptr_t)memory[i];}assert(0);return 0;}
static void clean(uintptr_t address){assert(live && address && after_start_allocs==1);cleans++;}
static bool tlb_sync(uintptr_t cb){assert(live && cleans && (cb==1 || cb==2));tlbs++;return !(mode==7 && cb==2);}
static void log_line(const char *fmt,...){(void)fmt;}
static void smmu_owner_stop(const char *reason){assert(reason);longjmp(reset_trap,1);}
'''
types = r'''
struct waffle_gmu_region {uint32_t address,size;uintptr_t memory;bool gpu_only,readonly;};
struct waffle_gmu_plan {bool compact_gpu_va;unsigned count;struct waffle_gmu_region regions[16];};
struct waffle_gmu_owner {unsigned tag;};
struct smmu_owner {struct waffle_gpu_registry registry;struct waffle_gmu_region dynamic,data;struct waffle_gpu_buffer user_buffer;unsigned compute_image;struct waffle_gmu_plan firmware;struct table_pool pool;struct pool_permission_context permission_context;struct waffle_gmu_owner *child;};
static struct waffle_gmu_owner child;
static struct smmu_owner *active;
static uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *p,uint64_t address){return p->compact_gpu_va?waffle_gpu_compact_alias(address):0;}
static bool waffle_gmu_owner_memory_idle(struct waffle_gmu_owner *g){assert(g==&child && live);return mode!=2;}
static bool waffle_gmu_owner_bind_user_buffer(struct waffle_gmu_owner *g,const struct waffle_gpu_buffer *b){(void)g;(void)b;assert(0);return false;}
static bool waffle_gmu_owner_bind_data_bo(struct waffle_gmu_owner *g,struct waffle_gmu_region *r){(void)g;(void)r;assert(0);return false;}
static bool waffle_gmu_owner_can_bind_bo(struct waffle_gmu_owner *g){assert(g==&child && live);return mode!=2;}
static uint64_t pte(struct table_pool *p,uint64_t va){uint64_t *r=(void *)p->memory[0];uint64_t *middle=permission_table(p,r[(va>>30)&511]);if(!middle)return 0;uint64_t *leaf=permission_table(p,middle[(va>>21)&511]);return leaf?leaf[(va>>12)&511]:0;}
static bool waffle_gmu_owner_bind_bo(struct waffle_gmu_owner *g,struct waffle_gmu_region *r){
 assert(g==&child && r==&active->dynamic && live && tlbs==2 && cleans==active->pool.count && after_start_allocs==1);
 uint64_t high=waffle_gpu_compact_alias(r->address)-WAFFLE_GPU_GLOBAL_BASE;
 for(unsigned off=0;off<16384;off+=4096){uint64_t low_pte=pte(&active->pool,(uint64_t)r->address+off),high_pte=pte(&active->pool,high+off);assert(low_pte==high_pte && (low_pte&PTE_ADDRESS)==kvtophys(r->memory+off) && (low_pte&0xc3)==0x43);}
 binds++;return mode!=8;
}
'''
tests = r'''
int main(void){
 assert(!smmu_registry_reclaim(NULL,NULL,false));
 assert(!smmu_registry_new(NULL,4096,WAFFLE_GPU_BO_WC));
 for(mode=0;mode<12;mode++){
  allocated=tlbs=cleans=binds=after_start_allocs=0;live=false;
  struct smmu_owner owner={.child=&child,.firmware={.compact_gpu_va=true,.count=1,.regions={{.address=0x80074000,.size=16384}}},.permission_context={.cb=1,.lpac_cb=2}};
  active=&owner;owner.permission_context.tables=&owner.pool;
  assert(new_table(&owner.pool));
  assert(map_page(&owner.pool,0x80074000,0x20000000,false));
  assert(map_page(&owner.pool,0x474000,0x20000000,false));
  if(mode==3)owner.firmware.regions[0].address=WAFFLE_GPU_DYNAMIC_ADDRESS;
  if(mode==4)assert(map_page(&owner.pool,WAFFLE_GPU_DYNAMIC_ADDRESS,0x20000000,false));
  if(mode==5)assert(map_page(&owner.pool,0x478000,0x20000000,false));
  if(mode==9)owner.dynamic.memory=1;
  if(mode==10)owner.firmware.compact_gpu_va=false;
  if(mode==11)((uint64_t *)owner.pool.memory[0])[WAFFLE_GPU_DYNAMIC_ADDRESS>>30]=0x30000003;
  live=true;
  if(setjmp(reset_trap)){assert((mode==6 || mode==7) && after_start_allocs==1 && owner.dynamic.memory && !binds);continue;}
  bool result=smmu_dynamic_bo_bind(&owner);
  assert(result==(mode==0));
  if(mode==0 || mode==8)assert(after_start_allocs==1 && owner.dynamic.memory && tlbs==2 && binds==1);
  else assert(!after_start_allocs && !tlbs && !binds);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + mapping + types + dynamic + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Actual dynamic BO: 12 vacancy/overlap/physical-range/partial-map/dual-ASID/bind-failure scenarios passed (host only)')
