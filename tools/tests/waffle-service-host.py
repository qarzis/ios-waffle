"""Run actual context/parent adapter with a real host worker and mutex."""
from pathlib import Path
import importlib.util,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'kernel/files/bsd/dev/waffle_gpu_service.c').read_text()
source=re.sub(r'^#include .*$','',source,flags=re.M)
adreno=(root/'kernel/files/bsd/dev/waffle_adreno.c').read_text()
adapter=adreno[adreno.index('/* Internal adapter;'):]
h=r'''
#define _DEFAULT_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <unistd.h>
#include "waffle_gpu_service.h"
#define __printflike(a,b) __attribute__((format(printf,a,b)))
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
#define NSEC_PER_USEC 1000
#define LCK_GRP_DECLARE(name,label) int name __attribute__((unused))
#define LCK_MTX_DECLARE(name,group) pthread_mutex_t name=PTHREAD_MUTEX_INITIALIZER
#define gpu_log service_log
typedef uintptr_t vm_offset_t;
typedef pthread_t thread_t;
typedef int wait_result_t;
typedef int kern_return_t;
static unsigned mode,attempts,allocs,frees,starts,ends,copies,started_thread,joined_thread;
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag){
 assert(map==7 && size==16384 && flags==7 && tag==5);attempts++;
 if((mode==1 && attempts==1)||(mode==3 && attempts==2))return 1;
 void *p=calloc(1,size);assert(p);*out=(uintptr_t)p;allocs++;return 0;
}
static void kmem_free(unsigned map,uintptr_t address,unsigned size){assert(map==7 && size==16384);free((void *)address);frees++;}
static bool lck_mtx_try_lock(pthread_mutex_t *lock){return pthread_mutex_trylock(lock)==0;}
static void lck_mtx_unlock(pthread_mutex_t *lock){assert(!pthread_mutex_unlock(lock));}
static void loader_log_putc(char c){(void)c;}
static void loader_return(void){assert(!"Unexpected unsafe reset in host context test");abort();}
static void delay_for_interval(unsigned amount,unsigned unit){assert(amount==1000 && unit==1000);usleep(1000);}
struct host_thread {void (*entry)(void *,int);void *arg;};
static void *host_entry(void *arg){struct host_thread request=*(struct host_thread *)arg;free(arg);request.entry(request.arg,0);return NULL;}
static int kernel_thread_start(void (*entry)(void *,int),void *arg,pthread_t *thread){
 if(mode==4)return 1;
 struct host_thread *request=malloc(sizeof(*request));assert(request);*request=(struct host_thread){entry,arg};
 int result=pthread_create(thread,NULL,host_entry,request);assert(!result);started_thread++;return result;
}
static void thread_deallocate(pthread_t thread){assert(!pthread_join(thread,NULL));joined_thread++;}
static pthread_t current_thread(void){return pthread_self();}
kern_return_t thread_terminate(pthread_t thread){assert(pthread_equal(thread,pthread_self()));pthread_exit(NULL);}
struct waffle_smmu_owner {unsigned marker;};
struct board_clock_owner {struct waffle_smmu_owner *child;bool ok,exercised;};
struct board_power_owner {struct board_clock_owner *child;};
struct aop_gpu_owner {struct board_power_owner *child;bool locked,exercised,exercise_ok;};
static struct waffle_smmu_owner smmu;
static struct board_clock_owner clocks,*active_board_clocks;
static struct board_power_owner power,*active_board_power;
static struct aop_gpu_owner root_owner,*active_aop_gpu;
static unsigned pll92_power=256;
static struct aop_gpu_owner *aop_gpu_owner_begin(unsigned);
static bool aop_gpu_owner_end(struct aop_gpu_owner *);
static bool waffle_smmu_owner_copy(struct waffle_smmu_owner *,struct waffle_gpu_copy_job *);
static bool waffle_smmu_owner_buffers(struct waffle_smmu_owner *,struct waffle_gpu_buffer [2]);
static struct waffle_gpu_memory *waffle_smmu_owner_memory_new(struct waffle_smmu_owner *,uint64_t,uint32_t);
static bool waffle_smmu_owner_memory_reclaim(struct waffle_smmu_owner *,struct waffle_gpu_memory *,bool);
static bool waffle_smmu_owner_submit(struct waffle_smmu_owner *,struct waffle_gpu_submit_job *);
static bool PE_parse_boot_argn(const char *name,void *value,unsigned size){assert(!strcmp(name,"waffle_image") && size==4);*(unsigned *)value=5;return true;}
'''
mocks=r'''
static struct waffle_gpu_memory *waffle_smmu_owner_memory_new(struct waffle_smmu_owner *s,uint64_t b,uint32_t f){(void)s;(void)b;(void)f;return NULL;}
static bool waffle_smmu_owner_memory_reclaim(struct waffle_smmu_owner *s,struct waffle_gpu_memory *b,bool u){(void)s;(void)b;(void)u;assert(0);return false;}
static bool waffle_smmu_owner_submit(struct waffle_smmu_owner *s,struct waffle_gpu_submit_job *j){(void)s;(void)j;return false;}

static bool waffle_smmu_owner_buffers(struct waffle_smmu_owner *o,struct waffle_gpu_buffer b[2]){(void)o;(void)b;return false;}

static void lock_held(void){assert(pthread_mutex_trylock(&service_lock)==EBUSY);}
static struct aop_gpu_owner *aop_gpu_owner_begin(unsigned probe){
 lock_held();assert(probe==94 && !active_aop_gpu);starts++;
 if(mode==2)return NULL;
 clocks=(struct board_clock_owner){.child=&smmu,.ok=true};power.child=&clocks;
 root_owner=(struct aop_gpu_owner){.child=&power};
 active_board_clocks=&clocks;active_board_power=&power;active_aop_gpu=&root_owner;
 return &root_owner;
}
static bool waffle_smmu_owner_copy(struct waffle_smmu_owner *parent,struct waffle_gpu_copy_job *job){
 lock_held();assert(parent==&smmu && active_aop_gpu==&root_owner && !root_owner.locked && !ends);
 copies++;if(mode==5 && copies==2)return false;
 for(unsigned i=0;i<256;i++)job->output[i]=job->input[i];job->fence=copies;return true;
}
static bool aop_gpu_owner_end(struct aop_gpu_owner *parent){
 lock_held();assert(parent==&root_owner && active_aop_gpu==parent && !parent->locked);
 bool ok=parent->exercise_ok && clocks.ok;ends++;
 active_aop_gpu=NULL;active_board_power=NULL;active_board_clocks=NULL;return ok;
}
int main(void){
 for(mode=0;mode<6;mode++){
  attempts=allocs=frees=starts=ends=copies=started_thread=joined_thread=0;
  assert(!active_context && !active_aop_gpu);
  bool result=waffle_gpu_service_probe();assert(result==(mode==0));
  assert(!active_context && !active_aop_gpu && allocs==frees);
  assert(started_thread==joined_thread);
  if(mode==0)assert(copies==3 && ends==1 && started_thread==1);
  if(mode==1)assert(!starts && !ends && !copies);
  if(mode==2)assert(starts==1 && !ends && !copies);
  if(mode==3 || mode==4)assert(ends==1 && !copies && !started_thread);
  if(mode==5)assert(copies==2 && ends==1 && started_thread==1);
 }
 mode=0;attempts=allocs=frees=starts=ends=copies=started_thread=joined_thread=0;
 struct waffle_gpu_context *context=waffle_gpu_context_begin();assert(context && !waffle_gpu_context_begin());
 uint32_t input[256]={0},output[256]={0};struct waffle_gpu_copy_job job={input,output,255,99,false};
 assert(!waffle_gpu_context_copy(context,&job) && !job.fence && !copies);
 job.words=256;assert(!waffle_gpu_context_copy(NULL,&job) && !job.fence);
 assert(lck_mtx_try_lock(&service_lock));
 assert(!waffle_gpu_context_copy(context,&job) && !job.fence);
 struct waffle_gpu_context *saved=context;assert(!waffle_gpu_context_end(&context) && context==saved);
 lck_mtx_unlock(&service_lock);
 assert(waffle_gpu_context_copy(context,&job) && job.fence==1);
 assert(waffle_gpu_context_end(&context) && !context && allocs==frees);
 assert(!waffle_gpu_context_end(&context));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+source+adapter+mocks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-pthread','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=15)
 if result.returncode:raise RuntimeError(result.stdout+result.stderr)
# Validate actual E25 GPU data supplemented with ordered service lifecycle proofs.
spec=importlib.util.spec_from_file_location('r',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
text=(root/'work/waffle/runs/20261101T074105Z/kernel-final.log').read_text()
text=text.replace('waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1','SERVICE begin root_live=1 serialized=1\nSERVICE worker started separate_thread=1\nwaffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1')
text=text.replace('waffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256','SERVICE busy submit_refused=1 close_refused=1 retained=1\nwaffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256')
text=text.replace('waffle-iommu: SMMU_OWNER released after child stop and context detach','SERVICE worker finished result=1\nwaffle-iommu: SMMU_OWNER released after child stop and context detach')
text+='\nSERVICE end consumed=1 result=1\nSERVICE probe passed=1 context_null=1\n'
assert r.validate_aop_owner_log(text,2,5)==r.extract_copy_jobs(text)[-1]
for marker in ['SERVICE worker started separate_thread=1','SERVICE busy submit_refused=1 close_refused=1 retained=1','SERVICE worker finished result=1','SERVICE end consumed=1 result=1']:
 try:r.validate_aop_owner_log(text.replace(marker,''),2,5)
 except RuntimeError:pass
 else:raise AssertionError('Missing service lifecycle proof accepted')
print('Actual top-level service + parent adapter: real pthread worker/mutex, busy submit/end refusal and retained context, 3 requests, allocator/constructor/thread/job failures, consumed pointer and strict lifecycle log validation passed (host only)')
