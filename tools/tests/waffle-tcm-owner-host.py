"""Actual TCM snapshot + exported GMU component owner across parent calls."""
from pathlib import Path
import struct,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('struct waffle_tcm_context {'):s.index('static uint32_t gen7_config_read(')]
code=code.replace('__asm__ volatile("dsb sy" ::: "memory");','barrier();')
fw=b''.join(struct.pack('<4I',addr,len(data),0,0)+data for addr,data in ((0,struct.pack('<4I',1,2,3,4)),(4,struct.pack('<I',9)),(0x10004008,struct.pack('<2I',6,7))))
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#include "waffle_gmu_firmware.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define round_page(n) (((n)+16383)&~16383u)
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
struct waffle_gmu_plan {const uint8_t *firmware;size_t length;void *submit_session;};
struct gmu_boot_context {uintptr_t gmu,qtb;struct waffle_gmu_plan *plan;unsigned probe;bool configured,running;};
static _Alignas(16384) uint8_t gmu[WAFFLE_GMU_SIZE],backup[32768],heap[16384],original[32768];
static unsigned mode,allocs,backup_frees,heap_frees;
static bool parent_owner;
static jmp_buf trap;
static bool session_requested(void){return parent_owner;}
static void barrier(void){}
static uint32_t rd(uintptr_t base,unsigned off){return *(uint32_t *)(base+off);}
static void wr(uintptr_t base,unsigned off,uint32_t value){
 assert(base==(uintptr_t)gmu);
 if(mode==5 && off==WAFFLE_GMU_ITCM+1024)return;
 *(uint32_t *)(base+off)=value;
}
static uintptr_t ml_io_map(uint64_t pa,unsigned size){assert(pa==WAFFLE_GMU_BASE && size==WAFFLE_GMU_SIZE);return mode==1?0:(uintptr_t)gmu;}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && flags==7 && tag==5 && (size==16384 || size==32768));
 bool root=parent_owner && allocs==0;
 if(mode==2 || (mode==14 && root))return 1;
 ++allocs;*out=root?(uintptr_t)heap:(uintptr_t)backup;memset((void *)*out,0,size);return 0;
}
static void kmem_free(unsigned map,uintptr_t p,unsigned size){
 assert(map==7 && (size==16384 || size==32768));
 if(p==(uintptr_t)heap){assert(!heap_frees);++heap_frees;}
 else {assert(p==(uintptr_t)backup && !backup_frees);++backup_frees;}
}
static void say(const char *fmt,...){(void)fmt;}
static void stop_unsafe(const char *reason){assert(reason);longjmp(trap,1);}
static void firmware_changes_tcm(void){memset(gmu+WAFFLE_GMU_ITCM,0xa5,32768);}
static bool boot_probe(uintptr_t base,uintptr_t qtb,struct waffle_gmu_plan *p,unsigned probe){
 assert(base==(uintptr_t)gmu && qtb==1 && p && probe==94);
 firmware_changes_tcm();*(uint32_t *)(gmu+WAFFLE_GMU_SYSRESET)=mode==4?0:1;
 return mode!=6;
}
static bool gmu_boot_begin(struct gmu_boot_context *c){
 if(mode==9)return false;
 c->configured=true;
 if(mode==10)return false;
 assert(c->gmu==(uintptr_t)gmu && c->qtb==1 && c->probe==94);
 c->running=true;c->plan->submit_session=(void *)1;
 *(uint32_t *)(gmu+WAFFLE_GMU_SYSRESET)=0;
 return true;
}
static bool submit_session_run(struct waffle_gmu_plan *p){assert(p->submit_session && !heap_frees && !backup_frees);firmware_changes_tcm();return mode!=11;}
static bool submit_session_close(struct waffle_gmu_plan *p){assert(p->submit_session);return mode!=12;}
static bool gmu_boot_finish(struct gmu_boot_context *c){
 if(mode==13)stop_unsafe("failed stop");
 *(uint32_t *)(gmu+WAFFLE_GMU_SYSRESET)=1;
 c->plan->submit_session=NULL;return c->running;
}
'''
h+='static const uint8_t fw[]={'+','.join(map(str,fw))+'};\n'
t=r'''
static void init(unsigned m,bool owner){
 mode=m;parent_owner=owner;allocs=backup_frees=heap_frees=0;
 for(unsigned i=0;i<sizeof(gmu)/4;++i)((uint32_t *)gmu)[i]=0x1a2b0000+i;
 *(uint32_t *)(gmu+WAFFLE_GMU_SYSRESET)=mode==7?0:1;
 memcpy(original,gmu+WAFFLE_GMU_ITCM,32768);
}
int main(void){
 for(unsigned probe_case=0;probe_case<2;++probe_case)for(unsigned m=0;m<=7;++m){
  init(m,false);struct waffle_gmu_plan plan={fw,mode==3?sizeof(fw)-1:sizeof(fw),NULL};
  if(!setjmp(trap)){
   bool ok=waffle_gmu_probe_tcm(&plan,probe_case?94:8,1);
   assert(ok==((mode==0) || (!probe_case && (mode==4 || mode==5 || mode==6))));
   assert(backup_frees==allocs);
   if(backup_frees)assert(!memcmp(original,gmu+WAFFLE_GMU_ITCM,32768));
  }else{assert(probe_case && (mode==4 || mode==5));assert(allocs==1 && !backup_frees);}
 }
 for(unsigned m=0;m<=14;++m){
  if(m==4 || m==5 || m==6 || m==8)continue;
  init(m,true);struct waffle_gmu_plan plan={fw,mode==3?sizeof(fw)-1:sizeof(fw),NULL};
  if(!setjmp(trap)){
   struct waffle_gmu_owner *owner=waffle_gmu_owner_begin(&plan,94,1);
   if(mode==1 || mode==2 || mode==3 || mode==7 || mode==9 || mode==10 || mode==14){
    assert(!owner && !plan.submit_session);assert(heap_frees+backup_frees==allocs);continue;
   }
   assert(owner && plan.submit_session && !heap_frees && !backup_frees && allocs==2);
   assert(!waffle_gmu_owner_begin(&plan,94,1));
   bool exercised=waffle_gmu_owner_exercise(owner);
   bool closed=waffle_gmu_owner_end(owner);
   assert(mode!=12 && mode!=13);
   assert(exercised==(mode!=11) && closed==(mode!=11));
   assert(!plan.submit_session && heap_frees==1 && backup_frees==1);
   assert(!memcmp(original,gmu+WAFFLE_GMU_ITCM,32768));
  }else{assert(mode==12 || mode==13);assert(allocs==2 && !heap_frees && !backup_frees);}
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual TCM/component owner: overlapping snapshots, full restoration, begin/exercise/end parent handoff, partial failures and live/failed-stop retention passed (host only)')
