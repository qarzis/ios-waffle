/* Bounded kernel context around the verified A750 parent and copy-job API. */
#include <kern/clock.h>
#include <kern/locks.h>
#include <kern/thread.h>
#include <vm/vm_kern.h>
#include <libkern/libkern.h>
#include <sys/systm.h>
#include <sys/waffle_gpu_service.h>
/* Same in-kernel thread API as waffle_synaptics.c; implementation in kern/thread_act.c. */
extern kern_return_t thread_terminate(thread_t);
extern void loader_log_putc(char);
extern void loader_return(void);
static void service_log(const char *fmt,...) __printflike(1,2);
static void service_log(const char *fmt,...)
{
    char line[256];va_list ap;va_start(ap,fmt);vsnprintf(line,sizeof(line),fmt,ap);va_end(ap);
    for(const char *p=line;*p;p++)loader_log_putc(*p);
    printf("%s",line);
}
static LCK_GRP_DECLARE(service_group,"waffle-gpu-context");
static LCK_MTX_DECLARE(service_lock,&service_group);
struct waffle_gpu_context {
    struct waffle_gpu_parent *parent;
    vm_offset_t allocation;
};
static struct waffle_gpu_context *active_context;
/* Diagnostic-only first-request barrier, before command publication. */
static unsigned probe_gate;
static bool probe_active;
static void service_stop(const char *why)
{
    service_log("waffle-gpu: REBOOT REQUIRED: %s; retain service and parent\n",why);
    loader_return();for(;;)delay_for_interval(1000,NSEC_PER_USEC);
}
struct waffle_gpu_context *waffle_gpu_context_begin(void)
{
    if(!lck_mtx_try_lock(&service_lock))return NULL;
    if(active_context){lck_mtx_unlock(&service_lock);return NULL;}
    vm_offset_t memory=0;
    if(kmem_alloc(kernel_map,&memory,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS){
        lck_mtx_unlock(&service_lock);return NULL;
    }
    struct waffle_gpu_context *context=(struct waffle_gpu_context *)memory;
    context->allocation=memory;context->parent=waffle_gpu_parent_begin();
    if(!context->parent){kmem_free(kernel_map,memory,PAGE_SIZE);lck_mtx_unlock(&service_lock);return NULL;}
    active_context=context;
    service_log("waffle-gpu: SERVICE begin root_live=1 serialized=1\n");
    lck_mtx_unlock(&service_lock);return context;
}
bool waffle_gpu_context_copy(struct waffle_gpu_context *context,struct waffle_gpu_copy_job *job)
{
    if(job)job->fence=0;
    if(!job || job->words!=256 || !job->input || !job->output || !lck_mtx_try_lock(&service_lock))return false;
    if(!context || active_context!=context || !context->parent){lck_mtx_unlock(&service_lock);return false;}
    if(probe_active && __atomic_load_n(&probe_gate,__ATOMIC_ACQUIRE)==0){
        __atomic_store_n(&probe_gate,1,__ATOMIC_RELEASE);
        unsigned tries=0;
        while(__atomic_load_n(&probe_gate,__ATOMIC_ACQUIRE)==1 && tries++<2000)delay_for_interval(1000,NSEC_PER_USEC);
        if(__atomic_load_n(&probe_gate,__ATOMIC_ACQUIRE)!=2)service_stop("serialization gate timed out");
    }
    bool ok=waffle_gpu_parent_copy(context->parent,job);
    lck_mtx_unlock(&service_lock);return ok;
}
bool waffle_gpu_context_buffers(struct waffle_gpu_context *context,struct waffle_gpu_buffer buffers[2])
{
    if(!buffers || !lck_mtx_try_lock(&service_lock))return false;
    bool ok=context && active_context==context && context->parent && waffle_gpu_parent_buffers(context->parent,buffers);
    lck_mtx_unlock(&service_lock);return ok;
}
struct waffle_gpu_memory *waffle_gpu_context_memory_new(struct waffle_gpu_context *context,uint64_t bytes,uint32_t flags)
{
    if(!context || !lck_mtx_try_lock(&service_lock))return NULL;
    struct waffle_gpu_memory *bo=active_context==context && context->parent?
        waffle_gpu_parent_memory_new(context->parent,bytes,flags):NULL;
    lck_mtx_unlock(&service_lock);return bo;
}
bool waffle_gpu_context_submit(struct waffle_gpu_context *context,struct waffle_gpu_submit_job *job)
{
    if(job)job->fence=0;
    if(!context || !job || !lck_mtx_try_lock(&service_lock))return false;
    bool ok=active_context==context && context->parent && waffle_gpu_parent_submit(context->parent,job);
    lck_mtx_unlock(&service_lock);return ok;
}
bool waffle_gpu_context_end(struct waffle_gpu_context **context)
{
    if(!context || !*context || !lck_mtx_try_lock(&service_lock))return false;
    struct waffle_gpu_context *current=*context;
    if(active_context!=current){lck_mtx_unlock(&service_lock);return false;}
    bool ok=waffle_gpu_parent_end(current->parent);
    current->parent=NULL;active_context=NULL;*context=NULL;
    kmem_free(kernel_map,current->allocation,PAGE_SIZE);
    service_log("waffle-gpu: SERVICE end consumed=1 result=%u\n",ok);
    lck_mtx_unlock(&service_lock);return ok;
}
struct service_work {
    struct waffle_gpu_context *context;
    vm_offset_t allocation;
    unsigned done;
    bool ok;
};
static void service_worker(void *arg,wait_result_t result)
{
    (void)result;struct service_work *work=arg;
    uint32_t input[256],output[256];
    work->ok=true;
    service_log("waffle-gpu: SERVICE worker started separate_thread=1\n");
    service_log("waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1\n");
    for(unsigned fence=1;fence<=3;fence++){
        for(unsigned i=0;i<256;i++){input[i]=waffle_job_test_pixel(fence,i);output[i]=0xbad00000u+i;}
        struct waffle_gpu_copy_job job={.input=input,.output=output,.words=256};
        if(!waffle_gpu_context_copy(work->context,&job) || job.fence!=fence){work->ok=false;break;}
        unsigned wrong=0;for(unsigned i=0;i<256;i++)if(output[i]!=input[i])++wrong;
        service_log("waffle-gmu: COPY_CALLER fence=%u checked=256 wrong=%u\n",job.fence,wrong);
        if(wrong){work->ok=false;break;}
    }
    if(work->ok)service_log("waffle-gmu: SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session\n");
    service_log("waffle-gpu: SERVICE worker finished result=%u\n",work->ok);
    __atomic_store_n(&work->done,1,__ATOMIC_RELEASE);
    thread_terminate(current_thread());
}
bool waffle_gpu_service_probe(void)
{
    struct waffle_gpu_context *context=waffle_gpu_context_begin();
    if(!context)return false;
    vm_offset_t memory=0;
    if(kmem_alloc(kernel_map,&memory,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS){
        (void)waffle_gpu_context_end(&context);return false;
    }
    struct service_work *work=(struct service_work *)memory;
    work->allocation=memory;work->context=context;
    __atomic_store_n(&probe_gate,0,__ATOMIC_RELEASE);probe_active=true;
    thread_t thread;
    if(kernel_thread_start(service_worker,work,&thread)!=KERN_SUCCESS){
        probe_active=false;kmem_free(kernel_map,memory,PAGE_SIZE);(void)waffle_gpu_context_end(&context);return false;
    }
    unsigned tries=0;
    while(__atomic_load_n(&probe_gate,__ATOMIC_ACQUIRE)==0 && !__atomic_load_n(&work->done,__ATOMIC_ACQUIRE) && tries++<3000)
        delay_for_interval(1000,NSEC_PER_USEC);
    if(__atomic_load_n(&probe_gate,__ATOMIC_ACQUIRE)!=1)service_stop("worker did not reach serialization gate");
    uint32_t input[256]={0},output[256]={0};
    struct waffle_gpu_copy_job competing={.input=input,.output=output,.words=256,.fence=99};
    bool submit_refused=!waffle_gpu_context_copy(context,&competing) && competing.fence==0;
    struct waffle_gpu_context *saved=context;
    bool close_refused=!waffle_gpu_context_end(&context) && context==saved;
    service_log("waffle-gpu: SERVICE busy submit_refused=%u close_refused=%u retained=%u\n",submit_refused,close_refused,context==saved);
    if(!submit_refused || !close_refused)service_stop("busy ownership or serialization violated");
    __atomic_store_n(&probe_gate,2,__ATOMIC_RELEASE);
    tries=0;
    while(!__atomic_load_n(&work->done,__ATOMIC_ACQUIRE) && tries++<10000)delay_for_interval(1000,NSEC_PER_USEC);
    if(!__atomic_load_n(&work->done,__ATOMIC_ACQUIRE))service_stop("worker completion unknown");
    bool ok=work->ok;
    thread_deallocate(thread);probe_active=false;
    kmem_free(kernel_map,work->allocation,PAGE_SIZE);
    bool stopped=waffle_gpu_context_end(&context);
    service_log("waffle-gpu: SERVICE probe passed=%u context_null=%u\n",ok&&stopped,context==NULL);
    return ok && stopped && !context;
}
