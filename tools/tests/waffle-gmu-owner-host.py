"""Actual GMU begin/finish owner: snapshot lifetime, cleanup and retention."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static const struct { uint32_t index, value; } gmu_boot_setup[]'):s.index('struct waffle_tcm_context {')]
code=code.replace('__asm__ volatile("dc ivac, %0" :: "r"(a) : "memory");','invalidate(a);').replace('__asm__ volatile("dsb sy" ::: "memory");','barrier();')
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
#define VM_WIMG_WCOMB 6
#define WAFFLE_GMU_HFI_ADDRESS 0x60014000
#define WAFFLE_GMU_LOG_ADDRESS 0x60004000
#define WAFFLE_GEN7_STOP_SLUMBER 1
#define WAFFLE_GEN7_STOP_CM3_RESET 2
#define WAFFLE_GEN7_STOP_RSC_ASLEEP 4
#define WAFFLE_GEN7_STOP_GX_OFF 8
#define WAFFLE_GEN7_STOP_GBIF_DRAINED 16
#define WAFFLE_GEN7_STOP_QTB_DRAINED 32
#define GMU 1
#define GBIF 2
#define CC 3
#define RSC 4
typedef uintptr_t vm_offset_t;
struct gen7_live_probe {unsigned snapshot;};
struct power_sequence {uintptr_t rsc;bool native_sleep;};
struct waffle_gmu_region {uintptr_t memory;unsigned size;};
struct waffle_gmu_plan {unsigned count,session_slumber_sequence;struct waffle_gmu_region regions[1];void *submit_session;};
static const uint32_t waffle_hfi_perf_table[]={1},waffle_hfi_bw_table[]={2};
static _Alignas(16384) uint8_t heap[16384],hfi[16384],qtb[4096];
static struct waffle_gmu_region hfi_region={(uintptr_t)hfi,16384};
static unsigned mode,allocated,freed,maps,unmaps,restores,started,stopped,reset_value,core_releases;
static bool use_heap;
static unsigned slumber_expected;
static jmp_buf trap;
static bool session_requested(void){return use_heap;}
static bool zap_requested(void){return use_heap;}
static bool writeback_requested(void){return use_heap;}
static void barrier(void){}
static void invalidate(uintptr_t a){assert(a);}
static uintptr_t ml_io_map(uintptr_t pa,unsigned size){
 ++maps;if(pa==WAFFLE_GPU_BASE+0x3c00*4){assert(size==0x1000);return mode==1?0:GBIF;}
 assert(pa==WAFFLE_GPUCC_BASE && size==WAFFLE_GPUCC_SIZE);return CC;
}
static uintptr_t ml_io_map_unmappable(uint64_t pa,unsigned size,unsigned attr){assert(pa==0x1230000 && size==16384 && attr==6);return mode==2?0:(uintptr_t)hfi;}
static void ml_io_unmap(uintptr_t va,unsigned size){assert(va==(uintptr_t)hfi && size==16384 && !unmaps);++unmaps;}
static uint64_t kvtophys(uintptr_t va){assert(va==(uintptr_t)hfi);return 0x1230000;}
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,unsigned va,unsigned size){
 assert(p);if(va==WAFFLE_GMU_HFI_ADDRESS){assert(size==16384);return &hfi_region;}
 assert(va==WAFFLE_GMU_LOG_ADDRESS && size==64);return NULL;
}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5 && !allocated);if(mode==15)return 1;
 ++allocated;memset(heap,0,sizeof(heap));*out=(uintptr_t)heap;return 0;
}
static void kmem_free(unsigned map,uintptr_t va,unsigned size){assert(map==7 && va==(uintptr_t)heap && size==16384 && allocated && !freed);++freed;}
static bool power_sequence_prepare(struct power_sequence *s){s->rsc=RSC;return mode!=3;}
static void power_sequence_restore(struct power_sequence *s){assert(s->rsc==RSC);++restores;}
static bool secure_gpu_init(void){return mode!=4;}
static uint32_t rd(uintptr_t base,unsigned off){
 if(base==GMU){
  if(off==WAFFLE_GMU_SYSRESET)return reset_value;
  if(off==WAFFLE_GMU_REG(0x23b07))return mode==5?1:0;
  if(off==WAFFLE_GMU_DTCM+0xffc*4)return 0x20060001;
  if(off==WAFFLE_GMU_REG(0x1f8d0))return stopped?3:0;
  return 0;
 }
 if(base==CC)return 0;
 if(base==GBIF)return 0;
 if(base==RSC){assert(off==16 || off==0x101*4);return off==16?(1u<<16):0;}
 assert(base==(uintptr_t)qtb && off==0x418);return 0;
}
static void wr(uintptr_t base,unsigned off,uint32_t value){
 assert(base==GMU || base==GBIF);
 if(base==GMU && off==WAFFLE_GMU_SYSRESET){reset_value=value;if(!value)++started;else ++stopped;}
}
static bool wait_for(uintptr_t base,unsigned off,unsigned mask,unsigned expected,unsigned loops){
 (void)mask;(void)expected;(void)loops;
 if(base==(uintptr_t)qtb)return off==0x418 && (expected?mode!=14:mode!=6);
 if(base==GMU && off==WAFFLE_GMU_FW_INIT)return mode!=7;
 if(base==GMU && off==WAFFLE_GMU_REG(0x1f980))return mode!=18;
 if(base==RSC)return mode!=12;
 if(base==GBIF)return mode!=13;
 return true;
}
static bool hfi_exchange(uintptr_t gmu,uintptr_t alias,const uint32_t *p,unsigned n,const char *name,bool zero){
 assert(gmu==GMU && alias==(uintptr_t)hfi && p && n && name);(void)zero;
 if(!strcmp(name,"GET_VALUE122"))return mode!=8;
 if(!strcmp(name,"PREPARE_SLUMBER")){
  assert(p[0]==((slumber_expected<<20)|(3u<<8)|33u));return mode!=11;
 }
 return true;
}
static bool hfi_boot_features(uintptr_t g,uintptr_t a,unsigned p){assert(g==1 && a==(uintptr_t)hfi && p>=14);return true;}
static bool hfi_start_capture(uintptr_t g,uintptr_t a,struct waffle_gmu_plan *plan,unsigned p){assert(g==1 && a==(uintptr_t)hfi && plan && p>=25);return true;}
static bool hfi_boot_votes(uintptr_t g,uintptr_t a,unsigned p){assert(g==1 && a==(uintptr_t)hfi && p>=17);return true;}
bool waffle_gpu_native_runtime_clock(unsigned probe){assert(probe==93 || probe==94);return mode!=9;}
static bool gpu_power_probe(uintptr_t gmu,uintptr_t cc,struct waffle_gmu_plan *plan,unsigned p,uintptr_t alias,struct gen7_live_probe *live){
 assert(gmu==1 && cc==3 && (p==93 || p==94) && alias==(uintptr_t)hfi);
 if(mode==10)return false;
 live->snapshot=0xabcd1234;
 if(use_heap)plan->submit_session=(void *)1;
 return true;
}
static bool submit_session_run(struct waffle_gmu_plan *p){assert(use_heap && p->submit_session && !stopped && !freed);p->session_slumber_sequence=47;slumber_expected=47;return mode!=16;}
static bool submit_session_close(struct waffle_gmu_plan *p){assert(p->submit_session && !freed);return mode!=17;}
static void submit_session_destroy(struct waffle_gmu_plan *p,unsigned evidence){assert(p->submit_session && evidence==63 && stopped && !freed);p->submit_session=NULL;++core_releases;}
static void gpu_gen7_live_finish(struct gen7_live_probe *live,unsigned evidence){if(live->snapshot)assert(live->snapshot==0xabcd1234 && evidence==63);}
static bool secure_page_probe(bool table){(void)table;return true;}
static void say(const char *fmt,...){(void)fmt;}
static void stop_unsafe(const char *reason){assert(reason);longjmp(trap,1);}
'''
t=r'''
int main(void){
 for(unsigned heap_mode=0;heap_mode<2;++heap_mode)for(mode=0;mode<=18;++mode){
  use_heap=heap_mode;slumber_expected=use_heap?45:43;allocated=freed=maps=unmaps=restores=started=stopped=core_releases=0;reset_value=1;
  memset(qtb,0,sizeof(qtb));struct waffle_gmu_plan plan={0};
  bool unsafe=mode==9 || mode==11 || mode==12 || mode==13 || mode==14 || (use_heap && mode==17);
  if(!setjmp(trap)){
   bool ok=boot_probe(GMU,(uintptr_t)qtb,&plan,use_heap?94:93);
   assert(!unsafe);
   assert(ok==(mode==0 || (!use_heap && (mode==15 || mode==16 || mode==17))));
   assert(freed==allocated);
   if(mode==6)assert(!started && !stopped && restores==1 && unmaps==1);
   if(use_heap && (mode==0 || mode==16))assert(core_releases==1 && !plan.submit_session);
  }else{
   assert(unsafe && !freed);
   if(use_heap)assert(allocated==1);
  }
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual GMU begin/finish/wrapper: snapshot owner across calls, stack/heap controls, startup cleanup and unsafe-stop retention passed (host only)')
