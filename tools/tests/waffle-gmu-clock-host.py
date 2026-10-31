"""Production GMU source selection, timeout rollback and readback rejection."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_adreno.c').read_text()
import re
native=(root/'work/waffle/gpu/vendor/gpucc-pineapple.c').read_text()
parents=re.search(r'gpu_cc_parent_map_1\[\].*?\n\};',native,re.S)[0]
source=int(re.search(r'P_GPLL0_OUT_MAIN, (\d+)',parents)[1])
assert 'F(200000000, P_GPLL0_OUT_MAIN, 3, 0, 0)' in native
assert '#define GMU_FREQ_MIN   200000000' in (root/'work/waffle/gpu/vendor/kgsl_gmu_core.h').read_text()
expected=(source<<8)|(2*3-1)
assert expected==0x505

helpers=s[s.index('struct clock_change {'):s.index('static struct waffle_smmu_owner *probe_smmu(')]
program=s[s.index('static uint32_t gmu_clock_config('):s.index('static void probe_cx(')]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#include "waffle_smmu.h"
typedef uintptr_t vm_offset_t;
#define NSEC_PER_USEC 1000
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
static _Alignas(16384) uint8_t owner_heap[16384];
static unsigned owner_allocs,owner_frees,mmio_writes;
static bool heap_requested;
static jmp_buf panic;

static uint32_t cc[WAFFLE_GPUCC_SIZE/4],gcc[WAFFLE_GCC_SIZE/4],gmu[WAFFLE_GMU_SIZE/4];
static unsigned fail_at,rcg_waits,entered,mapped,probe_number,pll_calls;
static bool failed,bad_readback,child_live;
static unsigned component_calls,native_finishes,component_mode;
struct waffle_smmu_owner {unsigned tag;};
static struct waffle_smmu_owner component;

static uint32_t read_reg(vm_offset_t base,unsigned off) {
 if(base==(uintptr_t)cc) {
  assert(off<sizeof(cc));
  if(bad_readback && !failed && off==WAFFLE_GPU_GMU_RCGR+4 && (cc[off/4]&0x71f)==0x505) {failed=true;return cc[off/4]^4;}
 } else if(base==(uintptr_t)gcc)assert(off<sizeof(gcc));
 else assert(base==(uintptr_t)gmu && off<sizeof(gmu));
 return *(uint32_t *)(base+off);
}
static void write_reg(vm_offset_t base,unsigned off,uint32_t value) {
 assert(!child_live);++mmio_writes;
 assert(base==(uintptr_t)cc || base==(uintptr_t)gcc);
 if(base==(uintptr_t)cc)assert(off==WAFFLE_GPU_SMMU_CLOCK || off>=0x9000); /* No PLL register writes. */
 if(base==(uintptr_t)cc && (off==WAFFLE_GPU_GMU_RCGR || off==WAFFLE_GPU_HUB_RCGR)) value&=~1u;
 *(uint32_t *)(base+off)=value;
}
static bool wait_mask(vm_offset_t base,unsigned off,uint32_t mask,uint32_t value) {
 if(base==(uintptr_t)cc && mask==1 && !value && (off==WAFFLE_GPU_GMU_RCGR || off==WAFFLE_GPU_HUB_RCGR)) {
  if(++rcg_waits==fail_at && !failed) {failed=true;return false;}
 }
 return (read_reg(base,off)&mask)==value;
}
static void gpu_log(const char *fmt,...) {(void)fmt;}
static void delay_for_interval(unsigned n,unsigned unit){assert((n==10 || n==1000) && unit==1000);}
static vm_offset_t ml_io_map(unsigned base,unsigned size) {assert(base==WAFFLE_GMU_BASE && size==WAFFLE_GMU_SIZE);mapped++;return (uintptr_t)gmu;}
static void show(vm_offset_t b,unsigned p,const char *s,unsigned o){(void)p;(void)s;(void)read_reg(b,o);}
/* Legacy87..92 dispatch: native93 is exercised separately by the real
 * clock-session header test. Entering it here is a regression. */
static struct {vm_offset_t cc;} native_clock_context;
static vm_offset_t native_clock_gmu;
static unsigned native_clock_probe;
static struct {bool runtime;struct {bool owned;} pll;} native_clock_state;
static unsigned native_clock_io;
static bool waffle_gmu_clock_start(void *io,void *state){(void)io;(void)state;assert(probe_number>=93);native_clock_state.runtime=true;return true;}
static bool waffle_gmu_clock_finish(void *io,void *state){(void)io;(void)state;assert(probe_number>=93 && !child_live);native_finishes++;return component_mode!=5;}
static uint32_t native_clock_root(void *arg){(void)arg;assert(probe_number>=93);return read_reg((uintptr_t)cc,WAFFLE_GPU_GMU_RCGR+4);}
static void native_clock_reboot_required(void){assert(component_mode==5 || component_mode==6);longjmp(panic,1);}
static bool probe_pll1(vm_offset_t clock,vm_offset_t cm3) {
 assert(clock==(uintptr_t)cc && cm3==(uintptr_t)gmu && probe_number==92);pll_calls++;return true;
}
static struct waffle_smmu_owner *probe_smmu(unsigned p) {
 assert(p==probe_number);entered++;
 assert((cc[(WAFFLE_GPU_GMU_RCGR+4)/4]&0x71f)==(p>=88?0x505u:1u));
 assert((cc[(WAFFLE_GPU_GMU_RCGR+4)/4]&0x100000)==0x100000); /* HW control preserved. */
 if(p==94 && component_mode!=1){assert(!child_live && !native_finishes);child_live=true;return &component;}
 return NULL;
}
bool waffle_smmu_owner_exercise(struct waffle_smmu_owner *o){assert(o==&component && child_live && !native_finishes);component_calls++;return component_mode!=2;}
bool waffle_smmu_owner_end(struct waffle_smmu_owner *o){assert(o==&component && child_live && component_calls==1 && !native_finishes);component_calls++;child_live=false;return component_mode!=3;}
static bool PE_parse_boot_argn(const char *name,void *out,unsigned size){assert(!strcmp(name,"waffle_session") && size==4);if(!heap_requested)return false;*(uint32_t *)out=1;return true;}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5 && !owner_allocs);
 if(component_mode==4)return 1;
 *out=(uintptr_t)owner_heap;memset(owner_heap,0,sizeof(owner_heap));owner_allocs++;return 0;
}
static void kmem_free(unsigned map,uintptr_t p,unsigned size){assert(map==7 && p==(uintptr_t)owner_heap && size==16384 && !child_live && !owner_frees);owner_frees++;}

'''
tests=r'''
int main(void) {
 for(unsigned p=87;p<=92;p++)for(unsigned mode=0;mode<6;mode++) {
  memset(cc,0,sizeof(cc));memset(gcc,0,sizeof(gcc));memset(gmu,0,sizeof(gmu));
  cc[(WAFFLE_GPU_GMU_RCGR+4)/4]=0x100001;
  cc[(WAFFLE_GPU_HUB_RCGR+4)/4]=0x100001;
  uint32_t saved_cc[WAFFLE_GPUCC_SIZE/4],saved_gcc[WAFFLE_GCC_SIZE/4];
  memcpy(saved_cc,cc,sizeof(cc));memcpy(saved_gcc,gcc,sizeof(gcc));
  probe_number=p;fail_at=mode<5?mode:0;bad_readback=mode==5 && p>=88;
  rcg_waits=entered=mapped=pll_calls=0;failed=false;
  probe_clock_session((uintptr_t)gcc,(uintptr_t)cc,p);
  bool success=mode==0 || (mode==5 && p==87);
  assert(entered==(unsigned)(success && p!=92) && mapped==(unsigned)success);
  assert(pll_calls==(unsigned)(success && p==92));
  assert(!memcmp(cc,saved_cc,sizeof(cc)) && !memcmp(gcc,saved_gcc,sizeof(gcc)));
 }
 for(unsigned p=93;p<=94;p++)for(component_mode=0;component_mode<7;component_mode++) {
  memset(cc,0,sizeof(cc));memset(gcc,0,sizeof(gcc));memset(gmu,0,sizeof(gmu));
  cc[(WAFFLE_GPU_GMU_RCGR+4)/4]=0x100001;cc[(WAFFLE_GPU_HUB_RCGR+4)/4]=0x100001;
  uint32_t saved_cc[WAFFLE_GPUCC_SIZE/4],saved_gcc[WAFFLE_GCC_SIZE/4];
  memcpy(saved_cc,cc,sizeof(cc));memcpy(saved_gcc,gcc,sizeof(gcc));
  probe_number=p;fail_at=component_mode==6?5:0;bad_readback=false;failed=false;
  rcg_waits=entered=mapped=pll_calls=component_calls=native_finishes=owner_allocs=owner_frees=mmio_writes=0;
  child_live=false;heap_requested=p==94;active_board_clocks=NULL;
  if(setjmp(panic)){
   assert((component_mode==5 || component_mode==6) && native_finishes==1 && !child_live && !owner_frees && active_board_clocks);
   active_board_clocks=NULL;continue; /* Simulated reset after retained failure. */
  }
  probe_clock_session((uintptr_t)gcc,(uintptr_t)cc,p);
  if(p==94 && component_mode==4){assert(!entered && !owner_allocs && !mmio_writes && !active_board_clocks);continue;}
  assert(entered==1 && native_finishes==1 && !child_live && !active_board_clocks);
  assert(owner_allocs==(p==94?1u:0u) && owner_frees==owner_allocs);
  assert(component_calls==(p==94 && component_mode!=1?2u:0u));
  assert(!memcmp(cc,saved_cc,sizeof(cc)) && !memcmp(gcc,saved_gcc,sizeof(gcc)));
 }
 memset(cc,0,sizeof(cc));memset(gcc,0,sizeof(gcc));memset(gmu,0,sizeof(gmu));
 cc[(WAFFLE_GPU_GMU_RCGR+4)/4]=0x100001;cc[(WAFFLE_GPU_HUB_RCGR+4)/4]=0x100001;
 probe_number=94;component_mode=0;heap_requested=true;bad_readback=false;fail_at=0;
 rcg_waits=entered=mapped=component_calls=native_finishes=owner_allocs=owner_frees=mmio_writes=0;
 active_board_clocks=NULL;child_live=false;
 struct board_clock_owner *live=probe_clocks((uintptr_t)gcc,(uintptr_t)cc,94);
 assert(live==(void *)owner_heap && live==active_board_clocks && child_live && live->count==14);
 assert(!component_calls && !native_finishes && !owner_frees);
 unsigned prior_writes=mmio_writes;
 assert(!probe_clocks((uintptr_t)gcc,(uintptr_t)cc,94) && mmio_writes==prior_writes && owner_allocs==1);
 struct board_clock_owner other={0};assert(!board_clock_begin(&other));
 assert(board_clock_exercise(live) && !board_clock_exercise(live));
 assert(board_clock_finish(live) && live->released && !active_board_clocks && !child_live);
 assert(!board_clock_finish(live));
 kmem_free(7,(uintptr_t)live,16384);assert(owner_frees==1);
 puts("Production clock owner: legacy rollback, live heap journal after return, duplicate begin/exercise refusal, child-before-clock restore, allocation failure and unsafe PLL/RCG retention passed (host only)");
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(harness+helpers+program+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
