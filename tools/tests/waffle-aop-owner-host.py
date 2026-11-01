"""Actual AOP top-level owner with real QMP helpers and simulated XNU transport."""
from pathlib import Path
import subprocess, tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/waffle_adreno.c').read_text()
callbacks = source[source.index('struct aop_channel_context'):source.index('static void probe_aop_channel(')]
owner = source[source.index('/* Heap top-level owner'):source.index('static void show(vm_offset_t base, uint32_t physical, const char *name, uint32_t off)\n{')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_aop.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define NSEC_PER_USEC 1000
#define VM_WIMG_IO 7
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
static uint32_t qmp[4096],ipcc[4096];
static _Alignas(16384) uint8_t heap[16384];
static unsigned mode,allocs,frees,maps,unmaps,writes,on_seen,off_seen,starts,exercises,ends,lock_count;
static unsigned macan_aop_mailbox_lock;
static bool held,child_live;
static jmp_buf reset_trap;
struct board_power_owner {unsigned tag;};
static struct board_power_owner power;
static void gpu_log(const char *fmt,...){(void)fmt;}
static void loader_return(void){longjmp(reset_trap,1);}
static bool lck_mtx_try_lock(unsigned *mutex){assert(mutex==&macan_aop_mailbox_lock);if(held)return false;held=true;lock_count++;return true;}
static void lck_mtx_unlock(unsigned *mutex){assert(mutex==&macan_aop_mailbox_lock && held);held=false;}
static bool PE_parse_boot_argn(const char *name,void *out,unsigned size){assert(!strcmp(name,"waffle_session") && size==4);*(uint32_t *)out=1;return true;}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){assert(map==7 && size==16384 && flags==7 && tag==5 && !allocs);if(mode==1)return 1;allocs++;*out=(uintptr_t)heap;memset(heap,0,sizeof(heap));return 0;}
static void kmem_free(unsigned map,uintptr_t address,unsigned size){assert(map==7 && address==(uintptr_t)heap && size==16384 && !child_live && !frees);frees++;}
static uintptr_t ml_io_map_unmappable(unsigned physical,unsigned size,unsigned flags){assert(held && size==16384 && flags==7);if(physical==WAFFLE_AOP_QMP_BASE){if(mode==3)return 0;maps++;return (uintptr_t)qmp;}assert(physical==0x00404000);if(mode==4)return 0;maps++;return (uintptr_t)ipcc;}
static void ml_io_unmap(uintptr_t address,unsigned size){assert(!held && !child_live && size==16384 && (address==(uintptr_t)qmp || address==(uintptr_t)ipcc));unmaps++;}
static uint32_t read_reg(uintptr_t base,unsigned offset){assert(held && base==(uintptr_t)qmp && !(offset&3) && offset<sizeof(qmp));return qmp[offset/4];}
static void write_reg(uintptr_t base,unsigned offset,uint32_t value){
 assert(held && !child_live);writes++;
 if(base==(uintptr_t)qmp){assert(!(offset&3) && offset<sizeof(qmp));qmp[offset/4]=value;return;}
 assert(base==(uintptr_t)ipcc+0x2000 && offset==0x0c && !value);
 if(!(mode==15 && qmp[0x2c/4]==WAFFLE_AOP_QMP_DOWN))qmp[0x30/4]=qmp[0x2c/4];
 if(qmp[0x128/4]){
  bool on=!memcmp(&qmp[0x12c/4],"{class: gpu, res: acd, val: 1}",31);
  if(on)on_seen++;else off_seen++;
  if(!(on?mode==6:mode==14))qmp[0x128/4]=0;
 }
}
static void delay_for_interval(unsigned n,unsigned unit){assert(held && (n==100 || n==1000) && unit==1000);}
static struct board_power_owner *probe_gpu_body(unsigned probe);
static bool board_power_exercise(struct board_power_owner *child);
static bool board_power_end(struct board_power_owner *child);
'''
mocks = r'''
static struct board_power_owner *probe_gpu_body(unsigned probe){
 assert(probe==94 && !held && !child_live && active_aop_gpu && !active_aop_gpu->locked);
 assert(active_aop_gpu->transport.io.context==&active_aop_gpu->channel);
 assert(on_seen==1 && !off_seen && qmp[0x2c/4]==WAFFLE_AOP_QMP_UP);
 assert(lck_mtx_try_lock(&macan_aop_mailbox_lock));lck_mtx_unlock(&macan_aop_mailbox_lock);
 starts++;if(mode==7)return NULL;child_live=true;return &power;
}
static bool board_power_exercise(struct board_power_owner *child){assert(child==&power && child_live && !held && !frees && !unmaps);assert(lck_mtx_try_lock(&macan_aop_mailbox_lock));lck_mtx_unlock(&macan_aop_mailbox_lock);exercises++;return mode!=8;}
static bool board_power_end(struct board_power_owner *child){assert(child==&power && child_live && !held && !frees && !unmaps && !off_seen);if(mode==10)longjmp(reset_trap,1);child_live=false;ends++;if(mode==11)held=true;return mode!=8 && mode!=9;}
'''
tests = r'''
int main(void){
 for(mode=0;mode<19;mode++){
  memset(qmp,0,sizeof(qmp));memset(ipcc,0,sizeof(ipcc));
  qmp[0]=mode==5?0:WAFFLE_AOP_QMP_MAGIC;qmp[1]=1;qmp[0x34/4]=728;qmp[0x38/4]=0x128;
  const unsigned up[]={0x0c,0x10,0x14,0x18,0x24,0x28};for(unsigned i=0;i<6;i++)qmp[up[i]/4]=WAFFLE_AOP_QMP_UP;
  qmp[0x2c/4]=qmp[0x30/4]=WAFFLE_AOP_QMP_DOWN;
  allocs=frees=maps=unmaps=writes=on_seen=off_seen=starts=exercises=ends=lock_count=0;
  held=mode==2;child_live=false;active_aop_gpu=NULL;
  bool retain=mode>=10 && mode!=16 && mode!=17;
  if(setjmp(reset_trap)){assert(retain && active_aop_gpu && !frees && !unmaps);if(mode==10)assert(child_live && !off_seen);else assert(!child_live && ends==1);active_aop_gpu=NULL;continue;}
  assert(!aop_gpu_owner_begin(93) && !allocs && !writes);
  struct aop_gpu_owner *live=aop_gpu_owner_begin(94);
  bool expected=mode==0 || mode>=8;
  assert((live!=NULL)==expected);
  if(live){
   assert(live==(void *)heap && live==active_aop_gpu && !live->locked && !held && child_live && !exercises && !frees && !unmaps);
   unsigned previous=writes;assert(!aop_gpu_owner_begin(94) && writes==previous && allocs==1);
   if(mode!=17){assert(aop_gpu_owner_exercise(live)==(mode!=8));assert(!aop_gpu_owner_exercise(live) && exercises==1);}
   if(mode==12)qmp[0x128/4]=4;
   if(mode==13)qmp[0x34/4]-=4;
   if(mode==18)qmp[0x2c/4]=WAFFLE_AOP_QMP_DOWN;
   bool result=aop_gpu_owner_end(live);assert(!retain && result==(mode==0 || mode==16));
  }
  assert(!active_aop_gpu && !child_live && frees==(mode==1?0u:1u) && maps==unmaps);
  if(mode!=2)assert(!held);
  if(mode>=1 && mode<=5)assert(!starts && !writes);
  if(mode==0 || mode==16 || mode==17)assert(on_seen==1 && off_seen==1 && ends==1);
 }
 assert(!aop_gpu_owner_exercise(NULL) && !aop_gpu_owner_end(NULL));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + callbacks + owner + mocks + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g', '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Actual AOP owner: 19 startup/rollback/live-child/short-lock/foreign-message/unknown-stop retention scenarios passed (host only)')
