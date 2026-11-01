"""Execute actual owned session code: multiple results, ownership and unsafe exits."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('enum submit_phase {'):]
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(a):"memory");','clean(a);').replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu_writeback.h"
#include "waffle_gpu_compute.h"
#include "waffle_gpu_image.h"
#include "waffle_gpu_copy.h"
#include "waffle_gpu_job.h"
#include "waffle_gpu_data.h"
#include "waffle_gpu_submit.h"
#include "waffle_gpu_buffer.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
#define VM_WIMG_WCOMB 6
#define WAFFLE_GMU_REG(x) (x)
#define NSEC_PER_USEC 1000
#define WAFFLE_GEN7_STOP_SLUMBER 1
#define WAFFLE_GEN7_STOP_CM3_RESET 2
#define WAFFLE_GEN7_STOP_RSC_ASLEEP 4
#define WAFFLE_GEN7_STOP_GX_OFF 8
#define WAFFLE_GEN7_STOP_GBIF_DRAINED 16
#define WAFFLE_GEN7_STOP_QTB_DRAINED 32
struct waffle_submit_session;
struct waffle_gmu_plan {struct waffle_submit_session *submit_session;unsigned session_slumber_sequence,compute_mode,compute_image;bool raw_stage_pause;};
struct waffle_gmu_owner {struct waffle_gmu_plan *plan;bool exercise_ok;};
struct waffle_gmu_region {uint32_t address,size;uintptr_t memory;bool gpu_only,readonly;};
static _Alignas(16384) uint32_t arena[4096],dynamic_arena[4096],data_arena[4096];
static uint32_t *active_arena=arena;
static uint64_t active_address=0x80074400;
static _Alignas(16384) uint8_t heap[16384];
static struct waffle_gmu_region region={0x80074000,16384,(uintptr_t)arena,true,false};
static unsigned mode,sends,allocs,frees,maps,unmaps,releases,waits,delays;
static bool after_open,compute_case,job_case,separate_case,glsl_case,glsl_prepare_case;
static uint32_t caller_input[256],caller_output[256],old_output[256];
bool waffle_gmu_owner_copy(struct waffle_gmu_owner *,struct waffle_gpu_copy_job *);
static uint32_t first_token[4];
static jmp_buf trap;
static bool ib_requested(void){return mode!=1;}
static uint64_t loader_return_remaining_us(void){return mode==12 && sends==1 ? 1000000:60000000;}
static unsigned rd(uintptr_t base,unsigned offset){
 if(base==1){assert(offset==0xf400*4);return mode==2?1:0;}
 assert(base==2 && offset==0x1f8d0);return mode==11 && after_open?3:0;
}
static void wr(uintptr_t base,unsigned offset,uint32_t value){assert(base==2 && offset==0x1f994 && value==(1u<<31));++releases;}
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,unsigned address,unsigned size){assert(p && address==0x80074000 && size==16384);return mode==13?NULL:&region;}
static uint64_t kvtophys(uintptr_t p){if(p>=(uintptr_t)data_arena && p<(uintptr_t)data_arena+16384)return 0x1250000+p-(uintptr_t)data_arena;if(p>=(uintptr_t)dynamic_arena && p<(uintptr_t)dynamic_arena+16384)return 0x1240000+p-(uintptr_t)dynamic_arena;return 0x1230000+p-(uintptr_t)arena;}
static uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *p,uint64_t va){assert(p);return waffle_gpu_compact_alias(va);}
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5);if(mode==3)return 1;
 assert(!allocs);++allocs;memset(heap,0,sizeof(heap));*out=(uintptr_t)heap;return 0;
}
static void kmem_free(unsigned map,uintptr_t p,unsigned size){assert(map==7 && p==(uintptr_t)heap && size==16384 && allocs==1 && !frees);++frees;}
static void clean(uintptr_t a){assert((a>=(uintptr_t)data_arena && a<(uintptr_t)data_arena+16384) || (a>=(uintptr_t)arena && a<(uintptr_t)arena+16384) || (a>=(uintptr_t)dynamic_arena && a<(uintptr_t)dynamic_arena+16384));}
static void barrier(void){}
static uintptr_t ml_io_map_unmappable(uint64_t pa,unsigned size,unsigned attr){assert((pa==0x1230000 || pa==0x1240000 || pa==0x1250000) && size==16384 && attr==6);++maps;return mode==4?0:pa==0x1250000?(uintptr_t)data_arena:pa==0x1230000?(uintptr_t)arena:(uintptr_t)dynamic_arena;}
static void ml_io_unmap(uintptr_t alias,unsigned size){assert((alias==(uintptr_t)arena || alias==(uintptr_t)dynamic_arena || alias==(uintptr_t)data_arena) && size==16384 && unmaps<3);++unmaps;}
static void delay_for_interval(unsigned amount,unsigned unit){assert((amount==100 || amount==1000000) && unit==1000);++delays;}
static bool wait_for(uintptr_t gmu,unsigned off,unsigned mask,unsigned expected,unsigned loops){
 assert(gmu==2 && off==0x23b0c && mask==(1u<<23) && !expected && loops==2000);++waits;
 return mode!=34 && mode!=6 && mode!=24 && !(mode==15 && waits==4);
}
static void say(const char *fmt,...){(void)fmt;}
static void stop_unsafe(const char *reason){assert(reason);longjmp(trap,1);}
static bool present_gpu_pixels(const volatile uint32_t *pixels){assert(pixels==active_arena+3072);for(unsigned i=0;i<256;i++)assert(pixels[i]==waffle_copy_expected(2,3072+i));return mode!=27;}
static bool hfi_exchange_watch(uintptr_t,uintptr_t,const uint32_t *,unsigned,const char *,bool,struct waffle_gmu_plan *);
'''
callback=r'''
static bool hfi_exchange_watch(uintptr_t gmu,uintptr_t hfi,const uint32_t *p,unsigned words,const char *name,bool zero,struct waffle_gmu_plan *watch){
 assert(gmu==2 && hfi==3 && words==5 && !strcmp(name,compute_case?"COMPUTE_IB":"SESSION_IB") && zero);
 struct waffle_submit_session *session=watch->submit_session;
 assert(session && watch!=session->plan && !watch->raw_stage_pause && session->plan->raw_stage_pause);
 assert(session->phase==SUBMIT_BUSY && session->owns_oob && !releases && !frees && unmaps==(active_arena==dynamic_arena?1u:0u));
 if(job_case){
  unsigned fence=session->submitted;
  assert(fence==sends+1 && session->completed==fence-1 && session->next_sequence==44+fence);
  assert(p[4]==(glsl_case?WAFFLE_GLSL_WORDS:WAFFLE_COPY_WORDS) && p[0]==(((43+fence)<<20)|(5u<<8)|131u));
  assert(active_arena[glsl_case?WAFFLE_GLSL_EVENT_WORD:WAFFLE_JOB_EVENT_WORD]==fence && active_arena[glsl_case?WAFFLE_GLSL_WAIT_WORD:WAFFLE_JOB_WAIT_WORD]==fence && active_arena[2048]==0);
  for(unsigned i=0;i<256;i++)assert(active_arena[3072+i]==0xdead0000u+i);
  if(separate_case){
   assert(session->data_alias==(uintptr_t)data_arena && session->data_va==(watch->compute_image>=10?WAFFLE_GPU_USER_TEST_VA:waffle_gpu_compact_alias(WAFFLE_GPU_DATA_ADDRESS)));
   for(unsigned i=0;i<4096;i++){
    assert(active_arena[i]==(glsl_case?waffle_glsl_command_word(fence,i,session->data_va,false,glsl_prepare_case):waffle_data_command_word(caller_input,fence,i,session->data_va,false)));
    assert(data_arena[i]==waffle_data_word(caller_input,i,false));
   }
   sends++;if(mode==33)return false;
   if(!glsl_prepare_case && mode!=36)for(unsigned i=0;i<256;i++)data_arena[i]=mode==31 && fence==2?old_output[i]:data_arena[256+i];
   active_arena[2048]=mode==30?fence-1:fence;
   if(mode==32)data_arena[256]^=1;
   if(mode==35)data_arena[4095]^=1;
   if(mode==37)active_arena[3072]^=1;
   return true;
  }
  sends++;
  if(mode==33)return false;
  for(unsigned i=0;i<256;i++)active_arena[3072+i]=(mode==31 && fence==2)?old_output[i]:active_arena[3328+i];
  active_arena[2048]=mode==30?fence-1:fence;
  if(mode==32)active_arena[3328]^=1;
  if(mode==35)active_arena[4095]^=1;
  return true;
 }
 if(compute_case){
  assert(watch->compute_mode==1 || watch->compute_mode==2);
  assert(p[4]==WAFFLE_COMPUTE_WORDS && ((uint64_t)p[3]<<32|p[2])==waffle_gpu_compact_alias(0x80078400));
  assert(session->submitted==1 && session->completed==0 && session->next_sequence==45);
  for(unsigned i=0;i<4096;i++)assert(active_arena[i]==(watch->compute_image>=2?waffle_copy_initial:watch->compute_image?waffle_image_initial:waffle_compute_initial)(watch->compute_mode,i));
  sends++;
  if(mode!=20)active_arena[2048]=1;
  if(watch->compute_mode==2 && mode!=21)for(unsigned i=0;i<(watch->compute_image?256u:8u);i++)active_arena[(watch->compute_image?3072:64)+i]=watch->compute_image>=2?active_arena[3328+i]:watch->compute_image?(0xff000000u|i):i;
  if(mode==22)active_arena[4095]^=1;
  if(mode==26)active_arena[3328]^=1;
  return mode!=23;
 }
 unsigned fence=++sends;
 assert(session->submitted==fence && session->completed==fence-1 && session->next_sequence==44+fence);
 assert(p[0]==(((43+fence)<<20)|(5u<<8)|131u) && p[1]==0x70bf8003 && p[4]==8);
 assert(((uint64_t)p[3]<<32|p[2])==waffle_gpu_compact_alias(active_address));
 for(unsigned i=0;i<4;++i){assert(active_arena[64+i]==0);assert(active_arena[259+i]==(waffle_writeback_values[i]^(fence*0x01010101)));}
 if(mode==5)return false;
 for(unsigned i=0;i<4;++i) {
  uint32_t value=active_arena[259+i];
  if(fence==1)first_token[i]=value;
  if(mode!=7)active_arena[64+i]=mode==10 && fence==2?first_token[i]:value;
 }
 if(mode==8)active_arena[63]=0;
 if(mode==9)active_arena[4095]=1;
 return true;
}
'''
t=r'''
int main(void){
 for(mode=0;mode<=17;++mode){
  sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
  struct waffle_gmu_plan plan={.raw_stage_pause=true};
  bool opened=submit_session_open(1,2,3,&plan);
  if(mode==1 || mode==2 || mode==3 || mode==4 || mode==13){
   assert(!opened && !plan.submit_session && !releases);
   assert(frees==(mode==4));continue;
  }
  assert(opened && plan.submit_session && !frees && !unmaps && !releases);
  struct waffle_submit_session *session=plan.submit_session;after_open=true;
  assert(session->allocation==(uintptr_t)heap && session->phase==SUBMIT_READY);
  if(mode==17)assert(!submit_session_open(1,2,3,&plan));
  if(mode==14){session->submitted=1;assert(!submit_session_close(&plan) && !releases);continue;}
  if(mode==16){session->next_sequence=4095;assert(!submit_session_submit(session));assert(submit_session_close(&plan));submit_session_destroy(&plan,63);continue;}
  bool ran=submit_session_run(&plan);
  if(mode==0 || mode==15 || mode==17){assert(ran && sends==3 && session->completed==3 && plan.session_slumber_sequence==47);}
  else assert(!ran);
  bool closed=submit_session_close(&plan);
  if(mode==0 || mode==12 || mode==17){
   assert(closed && releases==1 && !frees && !unmaps && session->phase==SUBMIT_CLOSED);
   assert(!submit_session_close(&plan) && releases==1);
   if(mode==12)assert(sends==1 && session->completed==1 && plan.session_slumber_sequence==45);
   for(unsigned bit=0;bit<6;++bit){
    if(!setjmp(trap)){submit_session_destroy(&plan,63&~(1u<<bit));assert(0);}
    assert(!frees && !unmaps && plan.submit_session==session);
   }
   submit_session_destroy(&plan,63);assert(!plan.submit_session && frees==1 && unmaps==1);
  }else{
   assert(!closed && !releases && !frees && !unmaps && session->phase==SUBMIT_POISONED);
   if(mode==10)assert(session->submitted==2 && session->completed==1);
   if(!setjmp(trap)){submit_session_destroy(&plan,63);assert(0);}
   assert(!frees && !unmaps);
  }
 }
 /* Bind a new backing BO after startup; real session must stage/read the
  * new alias, and the former BO must remain untouched until parent cleanup. */
 for(unsigned failure=0;failure<2;failure++){
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
  active_arena=arena;active_address=0x80074400;
  struct waffle_gmu_plan plan={.raw_stage_pause=true};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan};
  struct waffle_gmu_region fresh={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  assert(waffle_gmu_owner_can_bind_bo(&owner));
  assert(!waffle_gmu_owner_can_bind_bo(NULL));
  fresh.readonly=true;assert(!waffle_gmu_owner_bind_bo(&owner,&fresh));fresh.readonly=false;
  fresh.memory+=4;assert(!waffle_gmu_owner_bind_bo(&owner,&fresh));fresh.memory-=4;
  if(failure){
   mode=4;assert(!waffle_gmu_owner_bind_bo(&owner,&fresh));mode=0;
   assert(plan.submit_session->alias==(uintptr_t)arena && !unmaps);
  }else{
   assert(waffle_gmu_owner_bind_bo(&owner,&fresh));
   assert(plan.submit_session->alias==(uintptr_t)dynamic_arena && unmaps==1 && maps==2);
   active_arena=dynamic_arena;active_address=0x80078400;
   uint32_t before[4096];memcpy(before,arena,sizeof(before));
   assert(submit_session_run(&plan) && sends==3 && plan.submit_session->completed==3);
   assert(!memcmp(before,arena,sizeof(before)) && !waffle_gmu_owner_can_bind_bo(&owner));
  }
  assert(submit_session_close(&plan));submit_session_destroy(&plan,63);
  assert(frees==1 && unmaps==(failure?1u:2u));
 }
 compute_case=true;
 for(unsigned image=0;image<4;image++)for(unsigned dispatch=1;dispatch<=2;dispatch++)for(unsigned failure=0;failure<9;failure++){
  if(image==3 && dispatch==1)continue;
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
  struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=dispatch,.compute_image=image};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan};
  struct waffle_gmu_region fresh={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  assert(waffle_gmu_owner_bind_bo(&owner,&fresh));active_arena=dynamic_arena;active_address=0x80078400;
  mode=failure?19+failure:0;
  if(mode==25)plan.submit_session->ib_va=waffle_gpu_compact_alias(0x80074400);
  bool success=mode==0 || (dispatch==1 && mode==21) || (mode==27 && image!=3);
  assert(submit_session_run(&plan)==success);
  if(success){assert(plan.submit_session->completed==1 && plan.session_slumber_sequence==45 && sends==1);assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1 && unmaps==2);}
  else if(mode==27 && image==3){assert(plan.submit_session->phase==SUBMIT_READY && plan.submit_session->completed==1 && plan.session_slumber_sequence==45);assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1 && unmaps==2);}
  else if(mode==25){assert(!sends && plan.submit_session->phase==SUBMIT_READY);mode=0;assert(submit_session_close(&plan));submit_session_destroy(&plan,63);}
  else{assert(sends==1 && plan.submit_session->phase==SUBMIT_POISONED && !submit_session_close(&plan) && !frees && unmaps==1);}
 }

 job_case=true;
 for(unsigned failure=0;failure<7;failure++){
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
  struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=4};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
  struct waffle_gmu_region fresh={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  assert(waffle_gmu_owner_bind_bo(&owner,&fresh));active_arena=dynamic_arena;active_address=0x80078400;
  struct waffle_gpu_copy_job invalid={.input=caller_input,.output=caller_output,.words=255,.fence=99};
  assert(!waffle_gmu_owner_copy(&owner,&invalid) && !invalid.fence && !sends && owner.exercise_ok);
  invalid.words=256;invalid.input=(uint32_t *)dynamic_arena;
  assert(!waffle_gmu_owner_copy(&owner,&invalid) && !invalid.fence && !sends);
  invalid.input=caller_input;invalid.output=(uint32_t *)(UINTPTR_MAX-3);
  assert(!waffle_gmu_owner_copy(&owner,&invalid) && !invalid.fence && !sends);
  assert(!waffle_gmu_owner_copy(NULL,&invalid) && !waffle_gmu_owner_copy(&owner,NULL));
  assert(!waffle_job_buffer_valid((uintptr_t)dynamic_arena-512,(uintptr_t)dynamic_arena));
  assert(!waffle_job_buffer_valid((uintptr_t)dynamic_arena+16380,(uintptr_t)dynamic_arena));
  assert(waffle_job_buffer_valid((uintptr_t)dynamic_arena-1024,(uintptr_t)dynamic_arena));
  assert(waffle_job_buffer_valid((uintptr_t)dynamic_arena+16384,(uintptr_t)dynamic_arena));
  if(!failure){
   assert(owner_copy_sequence(&owner) && sends==3 && plan.submit_session->completed==3 && plan.session_slumber_sequence==47);
   assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1 && unmaps==2);continue;
  }
  bool failed=false;
  for(unsigned fence=1;fence<=3;fence++){
   for(unsigned i=0;i<256;i++){caller_input[i]=0xff000000u|(fence<<20)|(i*937u);caller_output[i]=0xbad00000u+i;}
   if(fence==2)mode=29+failure;
   struct waffle_gpu_copy_job job={.input=caller_input,.output=caller_output,.words=256,.fence=99};
   bool ok=waffle_gmu_owner_copy(&owner,&job);
   if(fence==2){
    assert(!ok && !job.fence && !owner.exercise_ok && plan.submit_session->phase==SUBMIT_POISONED);
    for(unsigned i=0;i<256;i++)assert(caller_output[i]==0xbad00000u+i);
    unsigned count=sends;assert(!waffle_gmu_owner_copy(&owner,&job) && sends==count && !submit_session_close(&plan));
    assert(!frees && unmaps==1);failed=true;break;
   }
   assert(ok && job.fence==fence && !memcmp(caller_input,caller_output,sizeof(caller_input)));
   memcpy(old_output,caller_output,sizeof(old_output));
  }
  assert(failed);
 }

 separate_case=true;
 for(unsigned glsl=0;glsl<4;glsl++)for(unsigned failure=0;failure<9;failure++){
  glsl_case=glsl;
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
  struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=glsl==3?11:glsl==2?10:glsl?8:7};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
  struct waffle_gmu_region fresh={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  struct waffle_gmu_region data={WAFFLE_GPU_DATA_ADDRESS,16384,(uintptr_t)data_arena,true,false};
  assert(waffle_gmu_owner_bind_bo(&owner,&fresh));active_arena=dynamic_arena;active_address=0x80078400;
  data.readonly=true;assert(!waffle_gmu_owner_bind_data_bo(&owner,&data));data.readonly=false;
  data.size=4096;assert(!waffle_gmu_owner_bind_data_bo(&owner,&data));data.size=16384;
  mode=4;assert(!waffle_gmu_owner_bind_data_bo(&owner,&data) && !plan.submit_session->data_alias && unmaps==1);mode=0;
  if(glsl>=2){
   struct waffle_gpu_buffer buffer={WAFFLE_GPU_USER_TEST_VA,(uintptr_t)data_arena,16384,false};
   buffer.gpu_va=0x1000;assert(!waffle_gmu_owner_bind_user_buffer(&owner,&buffer));buffer.gpu_va=WAFFLE_GPU_USER_TEST_VA;
   buffer.readonly=true;assert(!waffle_gmu_owner_bind_user_buffer(&owner,&buffer));buffer.readonly=false;
   assert(waffle_gmu_owner_bind_user_buffer(&owner,&buffer));assert(!waffle_gmu_owner_bind_user_buffer(&owner,&buffer));
  }else{assert(waffle_gmu_owner_bind_data_bo(&owner,&data));assert(!waffle_gmu_owner_bind_data_bo(&owner,&data));}
  struct waffle_gpu_copy_job invalid={data_arena,caller_output,256,99,false};
  assert(!waffle_gmu_owner_copy(&owner,&invalid) && !invalid.fence && !sends);
  for(unsigned fence=1;fence<=3;fence++){
   for(unsigned i=0;i<256;i++){caller_input[i]=0xff000000u|(fence<<20)|(i*937u);caller_output[i]=0xbad00000u+i;}
   if(fence==2 && failure)mode=29+failure;
   struct waffle_gpu_copy_job job={caller_input,caller_output,256,99,false};
   if(glsl==3){
    job.uploaded=true;
    for(unsigned i=0;i<4096;i++){data_arena[i]=waffle_data_word(caller_input,i,false);dynamic_arena[i]=waffle_glsl_command_word(fence,i,WAFFLE_GPU_USER_TEST_VA,false,false);}
    dynamic_arena[256]^=1;
    assert(!waffle_gmu_owner_copy(&owner,&job) && !job.fence && plan.submit_session->phase==SUBMIT_READY);
    dynamic_arena[256]^=1;
   }
   bool ok=waffle_gmu_owner_copy(&owner,&job);
   if(fence==2 && failure){
    assert(!ok && !job.fence && plan.submit_session->phase==SUBMIT_POISONED && !owner.exercise_ok);
    for(unsigned i=0;i<256;i++)assert(caller_output[i]==0xbad00000u+i);
    assert(!submit_session_close(&plan) && !frees && unmaps==1);break;
   }
   assert(ok && job.fence==fence && !memcmp(caller_input,caller_output,sizeof(caller_input)));
   memcpy(old_output,caller_output,sizeof(old_output));
  }
  if(!failure){assert(sends==3 && plan.submit_session->completed==3);assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1 && unmaps==3);}
 }

 glsl_case=glsl_prepare_case=true;
 mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;
 struct waffle_gmu_plan prepare_plan={.raw_stage_pause=true,.compute_mode=1,.compute_image=9};
 assert(submit_session_open(1,2,3,&prepare_plan));after_open=true;
 struct waffle_gmu_owner prepare_owner={.plan=&prepare_plan,.exercise_ok=true};
 struct waffle_gmu_region prepare_command={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
 struct waffle_gmu_region prepare_data={WAFFLE_GPU_DATA_ADDRESS,16384,(uintptr_t)data_arena,true,false};
 assert(waffle_gmu_owner_bind_bo(&prepare_owner,&prepare_command));active_arena=dynamic_arena;
 assert(waffle_gmu_owner_bind_data_bo(&prepare_owner,&prepare_data));
 for(unsigned i=0;i<256;i++)caller_input[i]=waffle_job_test_pixel(1,i);
 assert(owner_glsl_prepare(&prepare_owner) && sends==1 && prepare_plan.session_slumber_sequence==45);
 assert(submit_session_close(&prepare_plan));submit_session_destroy(&prepare_plan,63);assert(frees==1 && unmaps==3);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+code+callback+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual owned session: heap/OOB lifetime, 3 unique fence results, stale transfer, first-failure retention, safe refusal and all stop-evidence gates passed (host only)')
