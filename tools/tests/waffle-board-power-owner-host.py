"""Actual board power owner: live return, borrowed CX and child-first rollback."""
from pathlib import Path
import subprocess, tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/waffle_adreno.c').read_text()
decl = source[source.index('struct board_clock_owner;'):source.index('struct aop_channel_context')]
power = source[source.index('static void probe_cx('):source.index('void waffle_adreno_init(void)\n{')]
begin = source[source.index('static struct board_power_owner *probe_gpu_body(unsigned probe)'):source.index('/* Internal adapter;')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define NSEC_PER_USEC 1000
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
static uint32_t gcc[WAFFLE_GCC_SIZE/4],cc[WAFFLE_GPUCC_SIZE/4];
static _Alignas(16384) uint8_t parent_heap[16384],child_heap[16384];
struct board_clock_owner {uintptr_t allocation;bool released;};
static unsigned mode,allocs,parent_frees,child_frees,writes,clock_starts,exercises;
static bool child_live;
static jmp_buf reset_trap;
static void gpu_log(const char *fmt,...){(void)fmt;}
'''
mocks = r'''
static bool PE_parse_boot_argn(const char *name,void *out,unsigned size){assert(!strcmp(name,"waffle_session") && size==4);*(uint32_t *)out=1;return true;}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5 && !allocs);
 if(mode==1)return 1;
 *out=(uintptr_t)parent_heap;memset(parent_heap,0,sizeof(parent_heap));allocs++;return 0;
}
static void kmem_free(unsigned map,uintptr_t address,unsigned size){
 assert(map==7 && size==16384 && !child_live);
 if(address==(uintptr_t)child_heap){assert(!child_frees && !parent_frees);child_frees++;}
 else {assert(address==(uintptr_t)parent_heap && !parent_frees && !active_board_power);parent_frees++;}
}
static uint32_t read_reg(uintptr_t base,unsigned off){
 assert((base==(uintptr_t)gcc && off<sizeof(gcc)) || (base==(uintptr_t)cc && off<sizeof(cc)));
 return *(uint32_t *)(base+off);
}
static void write_reg(uintptr_t base,unsigned off,uint32_t value){assert(!child_live);writes++;*(uint32_t *)(base+off)=value;}
static bool cx_is_on(uintptr_t base){return ((read_reg(base,WAFFLE_GPU_CX_GDSCR)|read_reg(base,WAFFLE_GPU_CX_HW_CTRL))&(1u<<31))!=0;}
static void delay_for_interval(unsigned time,unsigned unit){
 assert(time==100 && unit==1000);
 if(mode!=5){if(cc[WAFFLE_GPU_CX_GDSCR/4]&1)cc[WAFFLE_GPU_CX_HW_CTRL/4]&=~(1u<<31);else cc[WAFFLE_GPU_CX_HW_CTRL/4]|=1u<<31;}
}
static uintptr_t ml_io_map(unsigned pa,unsigned size){
 if(pa==WAFFLE_GCC_BASE){assert(size==WAFFLE_GCC_SIZE);return mode==2?0:(uintptr_t)gcc;}
 assert(pa==WAFFLE_GPUCC_BASE && size==WAFFLE_GPUCC_SIZE);return mode==4?0:(uintptr_t)cc;
}
static void show(uintptr_t base,unsigned pa,const char *name,unsigned off){(void)pa;(void)name;(void)read_reg(base,off);}
static struct board_clock_owner *probe_clocks(uintptr_t g,uintptr_t c,unsigned probe){
 assert(g==(uintptr_t)gcc && c==(uintptr_t)cc && probe==94 && cx_is_on(c) && (gcc[WAFFLE_GPU_CFG_AHB/4]&3)==1 && !child_live);
 clock_starts++;if(mode==6)return NULL;
 struct board_clock_owner *child=(void *)child_heap;*child=(struct board_clock_owner){.allocation=(uintptr_t)child_heap};child_live=true;return child;
}
static void probe_clock_session(uintptr_t g,uintptr_t c,unsigned p){(void)g;(void)c;(void)p;assert(0);}
static bool board_clock_exercise(struct board_clock_owner *child){assert(child==(void *)child_heap && child_live && !parent_frees && !child_frees);exercises++;return mode!=7;}
static bool board_clock_finish(struct board_clock_owner *child){
 assert(child==(void *)child_heap && child_live && !parent_frees && !child_frees);
 if(mode==9)longjmp(reset_trap,1);
 child_live=false;child->released=true;return mode!=7 && mode!=8;
}
static void native_clock_reboot_required(void){assert(0);}
'''
tests = r'''
int main(void){
 for(mode=0;mode<14;mode++){
  memset(gcc,0,sizeof(gcc));memset(cc,0,sizeof(cc));
  gcc[WAFFLE_GPU_CFG_AHB/4]=mode==11?1:3;
  if(mode==3)gcc[WAFFLE_GPU_CFG_AHB/4]|=1u<<31;
  cc[WAFFLE_GPU_CX_GDSCR/4]=(mode==10 || mode==12)?0:1;
  if(mode==10)cc[WAFFLE_GPU_CX_HW_CTRL/4]=1u<<31;
  uint32_t saved_cfg=gcc[WAFFLE_GPU_CFG_AHB/4],saved_cx=cc[WAFFLE_GPU_CX_GDSCR/4],saved_hw=cc[WAFFLE_GPU_CX_HW_CTRL/4];
  active_board_power=NULL;allocs=parent_frees=child_frees=writes=clock_starts=exercises=0;child_live=false;
  if(setjmp(reset_trap)){assert(mode==9 && child_live && active_board_power && !parent_frees && !child_frees);active_board_power=NULL;continue;}
  if(mode==13){unsigned probe=94;aop_gpu_task(&probe);assert(exercises==1 && parent_frees==1 && child_frees==1);}
  else {
   struct board_power_owner *live=probe_gpu_body(94);
   bool expected=mode==0 || mode==7 || mode==8 || mode==9 || mode==10 || mode==11;
   assert((live!=NULL)==expected);
   if(live){
    assert(live==(void *)parent_heap && live==active_board_power && child_live && !parent_frees && !child_frees && !exercises);
    assert(live->cx_acquired==(mode!=10) && live->cfg_changed==(mode!=11));
    unsigned prior=writes;
    assert(!probe_gpu_body(94) && writes==prior && allocs==1);
    assert(board_power_exercise(live)==(mode!=7));
    assert(board_power_end(live)==(mode!=7 && mode!=8));
   }
  }
  assert(!active_board_power && !child_live && parent_frees==(mode==1?0u:1u));
  assert(gcc[WAFFLE_GPU_CFG_AHB/4]==saved_cfg && cc[WAFFLE_GPU_CX_GDSCR/4]==saved_cx && cc[WAFFLE_GPU_CX_HW_CTRL/4]==saved_hw);
  if(mode==1 || mode==2)assert(!writes);
  if(mode==12)assert(writes==2 && !clock_starts); /* CFG acquired/restored; CX untouched. */
  if(mode==10)assert(!(cc[WAFFLE_GPU_CX_GDSCR/4]&1));
 }
 assert(!board_power_exercise(NULL) && !board_power_end(NULL));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + decl + mocks + power + begin + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g',
                    '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Actual board power owner: 14 construction/rollback/borrowed-CX/caller-handoff scenarios and unsafe-child retention passed (host only)')
