"""Actual GPU writeback helper: native packets, NC readback, guards and faults."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool gen7_memory_writeback(vm_offset_t gpu,'):s.index('/* Native kgsl_set_smmu_aperture:')]
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(a):"memory");','clean(a);').replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
pm4=(root/'work/waffle/gpu/vendor/adreno_pm4types.h').read_text()
def f(name):return re.search(r'static inline uint '+name+r'\([^}]+\n\}',pm4)[0]
native=f('pm4_calc_odd_parity_bit')+'\n'+f('cp_type7_packet')
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu_writeback.h"
typedef uint32_t uint;
typedef uintptr_t vm_offset_t;
#define CP_TYPE7_PKT (7u<<28)
#define VM_WIMG_WCOMB 6
#define WAFFLE_GMU_REG(x) (x)
#define NSEC_PER_USEC 1000
struct waffle_gmu_plan {unsigned dummy;};
struct waffle_gmu_region {uint32_t address,size;vm_offset_t memory;bool gpu_only,readonly;};
static _Alignas(16384) uint32_t arena[4096];
static struct waffle_gmu_region region={0x80074000,16384,(uintptr_t)arena,true,false};
static unsigned mode,sends,maps,unmaps,delays;
static bool indirect_mode;
static bool ib_requested(void) {return indirect_mode;}
static jmp_buf reset;
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,unsigned va,unsigned size) {
 assert(p && va==0x80074000 && size==16384);return mode==1?NULL:&region;
}
static unsigned rd(uintptr_t gpu,unsigned reg) {assert(gpu==1 && reg==0xf400*4);return mode==2?1:0;}
static uint64_t kvtophys(uintptr_t p) {return 0x1230000+p-(uintptr_t)arena;}
static void clean(uintptr_t p) {assert(p>=(uintptr_t)arena && p<(uintptr_t)arena+16384);}
static void barrier(void) {}
static uintptr_t ml_io_map_unmappable(uint64_t pa,unsigned size,unsigned attr) {
 assert(pa==0x1230000 && size==16384 && attr==6);++maps;return mode==3?0:(uintptr_t)arena;
}
static void ml_io_unmap(uintptr_t va,unsigned size) {assert(va==(uintptr_t)arena && size==16384);++unmaps;}
static uint64_t waffle_gpu_plan_alias(struct waffle_gmu_plan *p,uint64_t va) {assert(p);return waffle_gpu_compact_alias(va);}
static bool wait_for(uintptr_t gmu,unsigned reg,unsigned mask,unsigned expected,unsigned loops) {
 assert(gmu==2 && reg==0x23b0c && mask==(1u<<23) && !expected && loops==2000);return mode!=5;
}
static void delay_for_interval(unsigned us,unsigned unit) {assert(us==100 && unit==1000);++delays;}
static void say(const char *fmt,...) {(void)fmt;}
static void stop_unsafe(const char *reason) {assert(reason);longjmp(reset,1);}
'''
exchange=r'''
static bool hfi_exchange_watch(uintptr_t gmu,uintptr_t hfi,const uint32_t *p,unsigned words,const char *name,bool zero,struct waffle_gmu_plan *plan) {
 assert(gmu==2 && hfi==3 && words==(indirect_mode?5:9) && !strcmp(name,"GPU_WRITEBACK") && zero && plan);
 if(indirect_mode) {
  assert(p[0]==((44u<<20)|(5u<<8)|131u) && p[1]==cp_type7_packet(0x3f,3));
  assert(((uint64_t)p[3]<<32|p[2])==waffle_gpu_compact_alias(0x80074400) && p[4]==8);
  /* The simulated GPU must fetch the actual staged IB, not host expected values. */
  static uint32_t fetched[9];fetched[0]=(44u<<20)|(9u<<8)|131u;
  for(unsigned i=0;i<8;++i)fetched[1+i]=arena[256+i];
  p=fetched;
 }
 assert(p[0]==((44u<<20)|(9u<<8)|131u));
 assert(p[1]==cp_type7_packet(0x3d,6) && p[8]==cp_type7_packet(0x12,0));
 assert(((uint64_t)p[3]<<32|p[2])==waffle_gpu_compact_alias(0x80074100));
 for(unsigned i=0;i<4;++i){assert(arena[64+i]==0);assert(p[4+i]==waffle_writeback_values[i]);}
 ++sends;
 if(mode==4)return false;
 if(mode!=6)for(unsigned i=0;i<4;++i)arena[64+i]=p[4+i];
 if(mode==7)arena[63]=0;
 if(mode==8)arena[4095]=1;
 return true;
}
'''
t=r'''
int main(void) {
 struct waffle_gmu_plan plan={0};
 for(unsigned indirect_case=0;indirect_case<2;++indirect_case)for(mode=0;mode<=8;++mode){
  indirect_mode=indirect_case;
  sends=maps=unmaps=delays=0;memset(arena,0,sizeof(arena));
  if(!setjmp(reset)) {
   bool ok=gen7_memory_writeback(1,2,3,&plan);
   assert(ok==(mode==0));assert(mode!=4 && mode!=5);
  }else assert(mode==4 || mode==5);
  assert(sends==(mode==0 || mode>=4));
  assert(unmaps==((mode==0 || mode>=6)?1u:0u));
  assert(delays==(mode==6?2000u:0u));
 }
 uint32_t ib[5];
 assert(!waffle_writeback_ib_packet(ib,4,44,0x1000,8));
 assert(!waffle_writeback_ib_packet(ib,5,44,0x1000,0));
 assert(!waffle_writeback_ib_packet(ib,5,44,0x1001,8));
 assert(!waffle_writeback_ib_packet(ib,5,0,0x1000,8));
 assert(!waffle_writeback_ib_packet(ib,5,44,UINT64_MAX-3,8));
 uint32_t packet[9];assert(!waffle_writeback_packet(packet,8,44,0x1000));
 assert(!waffle_writeback_packet(packet,9,0,0x1000));
 assert(!waffle_writeback_packet(packet,9,44,0x1001));
 assert(!waffle_writeback_packet(packet,9,44,UINT64_MAX-3));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+native+exchange+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual GPU writeback helper: native packet/VA, initial zero, full-buffer guards, missing transfer, ACK/idle failure and alias lifetime passed (host only)')
