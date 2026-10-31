"""Actual SMMU parent owner: callback lifetime, constructor rollback and child-first teardown."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2];src=(root/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
code=src[src.index('static const uint32_t smmu_gmu_offsets[]'):src.index('static void secure_context_stop(')]
code=code.replace('__asm__ volatile("wfi");','longjmp(trap,1);')
def decl(name,text=src):return re.search(r'struct '+name+r' \{.*?\n?\};',text,re.S)[0]+'\n'
gmu=(root/'kernel/files/bsd/sys/waffle_gmu.h').read_text()
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#include "waffle_gpu_va.h"
#include "waffle_gpu_writeback.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define TABLE_LIMIT 32
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
#define FSR_FAULT_MASK 0xc00001feu
#define ECATS_INST 2
#define PROTECTED_POOL_BYTES 0x400000
#define PROTECTED_POOL_ADDRESS 0xa0000000
#define WAFFLE_GMU_REGIONS 16
#define WAFFLE_GPU_SQE_ADDRESS 0x80010000u
#define WAFFLE_HWSCHED_POOL_ADDRESS 0x61000000u
struct waffle_submit_session;
struct waffle_gmu_owner {int tag;};
'''
for n in ('table_pool','gpu_context','pool_permission_context','access_matrix_context','protected_gpu_pool'):h+=decl(n)
h+=decl('waffle_gmu_region',gmu)+decl('waffle_gmu_plan',gmu)
h+=r'''
static _Alignas(16384) uint8_t smmu[0x40000],qtb[0x1000],gmu[WAFFLE_GMU_SIZE],cc[WAFFLE_GPUCC_SIZE];
static _Alignas(16384) uint8_t heap[16384],target[16384],sqe[16384],table[16384];
static struct protected_gpu_pool protected;
static struct waffle_gmu_owner child_object;
static unsigned mode,allocs,heap_frees,data_frees,fw_frees,detaches,callbacks,child_ends,matrix_runs,mmio_maps;
static bool heap_mode,child_live;
static jmp_buf trap;
static bool PE_parse_boot_argn(const char *name,void *out,unsigned size){
 assert(size==4);uint32_t value=1;bool found=false;
 if(!strcmp(name,"waffle_lpac_map")){found=true;if(mode==14)value=2;}
 if(heap_mode && (!strcmp(name,"waffle_zap") || !strcmp(name,"waffle_writeback") || !strcmp(name,"waffle_ib") || !strcmp(name,"waffle_session")))found=true;
 if(!heap_mode && mode==18 && !strcmp(name,"waffle_ecats_access"))found=true;
 if(found)memcpy(out,&value,4);
 return found;
}
static void log_line(const char *fmt,...){(void)fmt;}
static void loader_return(void){}
static uintptr_t ml_io_map(uint64_t pa,unsigned size){
 ++mmio_maps;
 if(pa==WAFFLE_GPU_QTB_BASE){assert(size==WAFFLE_GPU_QTB_SIZE);return mode==2?0:(uintptr_t)qtb;}
 if(pa==WAFFLE_GMU_BASE){assert(size==WAFFLE_GMU_SIZE);return (uintptr_t)gmu;}
 assert(pa==WAFFLE_GPUCC_BASE && size==WAFFLE_GPUCC_SIZE);return (uintptr_t)cc;
}
static uint32_t r32(uintptr_t base,unsigned off){return *(uint32_t *)(base+off);}
static uint64_t r64(uintptr_t base,unsigned off){if(mode==16 && base==(uintptr_t)smmu+0x23000 && off==0x20 && !detaches)return 0;return *(uint64_t *)(base+off);}
static void w32(uintptr_t base,unsigned off,uint32_t v){assert(!child_live);*(uint32_t *)(base+off)=v;}
static void w64(uintptr_t base,unsigned off,uint64_t v){assert(!child_live);*(uint64_t *)(base+off)=v;}
static void barrier(void){}
static bool poll(uintptr_t base,unsigned off,unsigned mask,unsigned expected,unsigned us){assert(base==(uintptr_t)qtb && off==0x418 && mask==1 && expected==1 && us==1000);return mode!=15;}
static bool tlb_sync(uintptr_t cb){assert(!child_live && cb==(uintptr_t)smmu+0x23000);return !(mode==10 && detaches);}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5);
 if(mode==1 && heap_mode && !allocs)return 1;
 bool metadata=heap_mode && !allocs;++allocs;*out=metadata?(uintptr_t)heap:(uintptr_t)target;
 memset((void *)*out,0,16384);return 0;
}
static void kmem_free(unsigned map,uintptr_t p,unsigned size){
 assert(map==7 && size==16384 && !child_live);
 if(p==(uintptr_t)heap){assert(!heap_frees);++heap_frees;}
 else{assert(p==(uintptr_t)target || p==(uintptr_t)table);++data_frees;}
}
static uint64_t kvtophys(uintptr_t p){
 if(p>=(uintptr_t)target && p<(uintptr_t)target+16384)return 0x12340000+p-(uintptr_t)target;
 if(p>=(uintptr_t)sqe && p<(uintptr_t)sqe+16384)return 0x12400000+p-(uintptr_t)sqe;
 assert(p>=(uintptr_t)table && p<(uintptr_t)table+16384);return 0x90000000+p-(uintptr_t)table;
}
static void clean(uintptr_t p){assert(p && !child_live);}
static uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *p,uint64_t va){assert(p);return waffle_gpu_compact_alias(va);}
static bool waffle_gmu_prepare(struct waffle_gmu_plan *p,unsigned probe){
 assert(probe==93 || probe==94);if(mode==5)return false;
 p->split_gpu_va=p->compact_gpu_va=true;p->count=1;
 p->regions[0]=(struct waffle_gmu_region){0x80010000,4096,(uintptr_t)sqe,true,true};return true;
}
static void waffle_gmu_free(struct waffle_gmu_plan *p){assert(!child_live && !p->submit_session);++fw_frees;p->count=0;}
static uint64_t *new_table(struct table_pool *p){if(mode==6)return NULL;assert(!p->count);p->count=1;p->memory[0]=(uintptr_t)table;p->phys[0]=0x90000000;return (uint64_t *)table;}
static bool map_page(struct table_pool *p,uint64_t va,uint64_t pa,bool ro){assert(p->count && va && pa && !ro);return true;}
static bool map_page_access(struct table_pool *p,uint64_t va,uint64_t pa,bool ro,bool user){assert(p->count && va && pa && ro && user);return true;}
static bool translate_page(uintptr_t q,uintptr_t cb,uint64_t va,uint64_t pa,unsigned sid){assert(q==(uintptr_t)qtb && cb && va && pa && (sid==0 || sid==5));return true;}
static bool translate_page_access(uintptr_t q,uintptr_t cb,uint64_t va,uint64_t pa,unsigned sid,unsigned access,unsigned tries){assert(q==(uintptr_t)qtb && cb && va && pa && sid==1 && (access==0 || access==2) && tries==1);return true;}
static bool gpu_context_begin_at(struct gpu_context *c,uintptr_t sm,unsigned page,unsigned pages,unsigned contexts,unsigned matches,uint64_t root,unsigned bank,unsigned slot,unsigned sid){
 assert(sm==(uintptr_t)smmu && page==4096 && pages==32 && contexts==8 && matches==8 && root==0x90000000);
 c->cb=sm+(pages+bank)*page;c->bank=bank;c->slot=slot;c->sid=sid;c->changed=true;return mode!=7;
}
static bool gpu_context_begin(struct gpu_context *c,uintptr_t sm,unsigned p,unsigned ps,unsigned cs,unsigned ms,uint64_t root){return gpu_context_begin_at(c,sm,p,ps,cs,ms,root,0,0,0);}
static bool gpu_context_split(struct gpu_context *c){assert(c->changed);return true;}
static bool gpu_context_end(struct gpu_context *c){assert(!child_live);++detaches;bool ok=!(mode==9 && c->changed && c->bank==1);c->changed=false;return ok;}
static bool gpu_context_fault_continue(uintptr_t cb){assert(cb);return true;}
static bool diagnostic_context_stall(uintptr_t cb){assert(cb);return true;}
static bool waffle_scm_lpac_aperture(void){return true;}
static bool waffle_scm_gpu_aperture(void){return true;}
static struct protected_gpu_pool *protected_pool_prepare(uintptr_t sm,unsigned p,unsigned ps,unsigned cs,unsigned ms,uintptr_t q,uint64_t va){
 assert(sm==(uintptr_t)smmu && p==4096 && ps==32 && cs==8 && ms==8 && q==(uintptr_t)qtb && va==0x100000000ULL);
 if(mode==17)return NULL;
 protected.address=va;protected.context.cb=sm+0x22000;return &protected;
}
static void protected_pool_release(struct protected_gpu_pool *p){assert(p==&protected && !child_live);}
static bool gpu_secure_context_probe(uintptr_t sm,unsigned p,unsigned ps,unsigned cs,unsigned ms,uintptr_t q){(void)sm;(void)p;(void)ps;(void)cs;(void)ms;(void)q;return true;}
static bool pool_permissions(void *opaque,uint64_t va,uint32_t size,uint32_t flags){
 struct pool_permission_context *p=opaque;assert(p && p->tables && p->tables->count && p->cb==(uintptr_t)smmu+0x20000 && p->lpac_cb==(uintptr_t)smmu+0x21000);
 assert(va && size==4096 && flags==0x339);
 if(heap_mode){assert((uintptr_t)p>=(uintptr_t)heap && (uintptr_t)p<(uintptr_t)heap+16384);assert((uintptr_t)p->tables>=(uintptr_t)heap && (uintptr_t)p->tables<(uintptr_t)heap+16384);}
 ++callbacks;return mode!=20;
}
static bool access_matrix_capture(void *opaque,uint64_t va,uint32_t size,uint32_t flags){struct access_matrix_context *m=opaque;++m->count;return pool_permissions(&m->permissions,va,size,flags);}
static bool access_matrix_run(struct access_matrix_context *m,struct waffle_gmu_plan *p,uintptr_t q,uintptr_t cb,uintptr_t g,uintptr_t c){assert(!child_live && !detaches && p && m->count && q==(uintptr_t)qtb && cb && g==(uintptr_t)gmu && c==(uintptr_t)cc);++matrix_runs;return true;}
static bool waffle_gmu_probe_tcm(struct waffle_gmu_plan *p,unsigned probe,uintptr_t q){assert(probe==93 && q==(uintptr_t)qtb);return p->pool_permissions(p->pool_permissions_context,0x1ff8000500000ULL,4096,0x339);}
static struct waffle_gmu_owner *waffle_gmu_owner_begin(struct waffle_gmu_plan *p,unsigned probe,uintptr_t q){
 assert(probe==94 && q==(uintptr_t)qtb && !child_live && !heap_frees);
 if(!p->pool_permissions(p->pool_permissions_context,0x1ff8000500000ULL,4096,0x339) || mode==8)return NULL;
 child_live=true;p->submit_session=(void *)1;
 if(mode==13)p->pool_permissions_context=NULL;
 return &child_object;
}
static struct waffle_gmu_plan *active_plan;
static bool waffle_gmu_owner_exercise(struct waffle_gmu_owner *child){
 assert(child==&child_object && child_live && !heap_frees && !data_frees && !fw_frees);
 assert(active_plan->pool_permissions(active_plan->pool_permissions_context,0x1ff8000500000ULL,4096,0x339));
 if(mode==19)active_plan->submit_session=NULL;
 return mode!=11;
}
static bool waffle_gmu_owner_end(struct waffle_gmu_owner *child){
 assert(child==&child_object && child_live && !detaches && !heap_frees && !data_frees);
 if(mode==12)longjmp(trap,1);
 child_live=false;active_plan->submit_session=NULL;++child_ends;return true;
}
'''
# The exercise callback obtains the parent-owned plan when the child starts.
h=h.replace('static struct waffle_gmu_owner *waffle_gmu_owner_begin(', 'static struct waffle_gmu_plan *active_plan;\nstatic struct waffle_gmu_owner *waffle_gmu_owner_begin(').replace(' child_live=true;p->submit_session=', ' active_plan=p;child_live=true;p->submit_session=').replace('\nstatic struct waffle_gmu_plan *active_plan;\nstatic bool waffle_gmu_owner_exercise','\nstatic bool waffle_gmu_owner_exercise')
t=r'''
int main(void){
 for(unsigned heap_case=0;heap_case<2;++heap_case)for(mode=0;mode<=20;++mode){
  heap_mode=heap_case;allocs=heap_frees=data_frees=fw_frees=detaches=callbacks=child_ends=matrix_runs=mmio_maps=0;child_live=false;active_plan=NULL;
  memset(smmu,0,sizeof(smmu));memset(qtb,0,sizeof(qtb));memset(gmu,0,sizeof(gmu));memset(cc,0,sizeof(cc));
  *(uint32_t *)(gmu+WAFFLE_GMU_SYSRESET)=mode==3?0:1;
  *(uint32_t *)(cc+WAFFLE_GPU_GX_GDSCR)=1;
  if(mode==4)*(uint32_t *)(smmu+0x80c)=0x80000005;
  bool retain=heap_mode && (mode==9 || mode==10 || mode==12 || mode==13 || mode==19);
  if(!setjmp(trap)){
   waffle_smmu_probe((uintptr_t)smmu,4096,32,8,8,heap_mode?94:93);
   assert(!retain && !child_live);
   if(mode==0){assert(callbacks==(heap_mode?2:1) && child_ends==(heap_mode?1:0) && data_frees==2 && fw_frees==1);}
   if(heap_mode && mode!=1)assert(heap_frees==1);
   if(mode==14)assert(!mmio_maps);
   if(mode==18 && !heap_mode)assert(matrix_runs==1);
   if(!heap_mode && (mode==9 || mode==10))assert(!data_frees && !fw_frees);
  }else{
   assert(retain && !heap_frees && !data_frees && !fw_frees);
   if(mode==12 || mode==13 || mode==19)assert(child_live && !detaches);
  }
 }
 /* Even a caller attempting cleanup directly cannot detach a live child. */
 struct smmu_owner owner={.child=&child_object};
 if(!setjmp(trap)){(void)smmu_owner_finish(&owner);assert(0);}
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual SMMU owner: stack/heap paths, callback after begin return, partial setup rollback, child-first detach and TLB/unknown-state retention passed (host only)')
