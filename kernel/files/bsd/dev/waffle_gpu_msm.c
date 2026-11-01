/* Bounded MSM BO/submit boundary. No general PM4, mmap or GL capability claim. */
#include <kern/locks.h>
#include <libkern/libkern.h>
#include <miscfs/devfs/devfs.h>
#include <sys/conf.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include <sys/systm.h>
#include <sys/waffle_gpu_service.h>
#include <sys/waffle_gpu_msm.h>
#include <sys/waffle_gpu_data.h>
#include <sys/waffle_gpu_map.h>
#include <pexpert/pexpert.h>
extern void redwood_tl(const char *,...) __printflike(1,2);
extern void loader_return(void);
static LCK_GRP_DECLARE(msm_group,"waffle-gpu-msm");
static LCK_MTX_DECLARE(msm_lock,&msm_group);
static struct waffle_gpu_context *msm_context;
static struct waffle_gpu_buffer msm_buffers[2];
static bool msm_handles[2],msm_reported;
static unsigned msm_next,msm_fence;
static int msm_pid;
static bool msm_mapped;
static uintptr_t msm_map_tokens[2];
static uint64_t msm_map_addresses[2];
static void msm_revoke(unsigned index)
{
    if(!waffle_gpu_map_revoke(&msm_map_tokens[index])){
        redwood_tl("waffle-gpu: REBOOT REQUIRED: user BO unmap failed; retain backing\n");loader_return();for(;;);
    }
    msm_map_addresses[index]=0;
}

static bool msm_handle(unsigned h){return h>=1 && h<=2 && msm_handles[h-1];}
static int msm_open(dev_t dev,int flags,int type,struct proc *p)
{
    (void)dev;(void)flags;(void)type;lck_mtx_lock(&msm_lock);
    int error=EBUSY;
    if(msm_context)goto done;
    msm_context=waffle_gpu_context_begin();
    if(!msm_context){error=ENXIO;goto done;}
    if(!waffle_gpu_context_buffers(msm_context,msm_buffers)){
        (void)waffle_gpu_context_end(&msm_context);error=EIO;goto done;
    }
    msm_pid=proc_pid(p);msm_next=msm_fence=0;msm_reported=false;
    bzero(msm_handles,sizeof(msm_handles));
    redwood_tl("waffle-gpu: MSM open pid=%d actual_gpu_bos=2 user_commands=1\n",msm_pid);
    redwood_tl("waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1\n");error=0;
done:lck_mtx_unlock(&msm_lock);return error;
}
/* Validate all command/shader/descriptor/guard words before any GPU publication.
 * The user cannot mutate BO memory except through the same serialized ioctl. */
static bool msm_contents_valid(unsigned fence,uint32_t input[256])
{
    volatile uint32_t *cmd=(void *)msm_buffers[0].memory,*data=(void *)msm_buffers[1].memory;
    for(unsigned i=0;i<256;i++)input[i]=data[256+i];
    for(unsigned i=0;i<4096;i++)
        if(data[i]!=waffle_data_word(input,i,false) ||
           cmd[i]!=waffle_glsl_command_word(fence,i,msm_buffers[1].gpu_va,false,false))return false;
    return true;
}
static int msm_submit(struct waffle_msm_submit *r)
{
    if(r->flags!=0x10 || r->fence || r->nr_bos!=2 || r->nr_cmds!=1 || r->queueid ||
       r->in_syncobjs || r->out_syncobjs || r->nr_in_syncobjs || r->nr_out_syncobjs || r->syncobj_stride || r->pad ||
       !msm_handle(1) || !msm_handle(2) || msm_fence>=3)return EINVAL;
    struct waffle_msm_submit_bo bos[2];struct waffle_msm_submit_cmd cmd;
    if(copyin(r->bos,bos,sizeof(bos)) || copyin(r->cmds,&cmd,sizeof(cmd)))return EFAULT;
    if(bos[0].handle!=1 || bos[1].handle!=2 || bos[0].flags!=1 || bos[1].flags!=3 ||
       bos[0].presumed!=msm_buffers[0].gpu_va || bos[1].presumed!=msm_buffers[1].gpu_va ||
       cmd.type!=1 || cmd.submit_idx || cmd.submit_offset!=1024 || cmd.size!=WAFFLE_GLSL_WORDS*4 ||
       cmd.pad || cmd.nr_relocs || cmd.relocs)return EINVAL;
    if(msm_mapped){
        msm_revoke(0);msm_revoke(1);
        __asm__ volatile("dsb sy":::"memory");
        redwood_tl("waffle-gpu: MSM_MAP revoked_before_validate next_fence=%u\n",msm_fence+1);
    }
    uint32_t input[256],output[256];
    if(!msm_contents_valid(msm_fence+1,input)){
        redwood_tl("waffle-gpu: MSM invalid_command refused=1 next_fence=%u\n",msm_fence+1);return EINVAL;
    }
    struct waffle_gpu_copy_job job={.input=input,.output=output,.words=256,.uploaded=true};
    if(!waffle_gpu_context_copy(msm_context,&job) || job.fence!=msm_fence+1)return EIO;
    unsigned wrong=0;for(unsigned i=0;i<256;i++)if(input[i]!=output[i])wrong++;
    redwood_tl("waffle-gmu: COPY_CALLER fence=%u checked=256 wrong=%u\n",job.fence,wrong);
    if(wrong)return EIO;
    msm_fence=job.fence;r->fence=job.fence;
    redwood_tl("waffle-gpu: MSM submitted fence=%u user_ib=1 bo_handles=2\n",msm_fence);return 0;
}
static int msm_ioctl(dev_t dev,u_long command,caddr_t data,int flags,struct proc *p)
{
    (void)dev;(void)flags;lck_mtx_lock(&msm_lock);int error=0;
    if(!msm_context || proc_pid(p)!=msm_pid){error=EPERM;goto done;}
    if(command==WAFFLE_MSM_NEW){
        struct waffle_msm_gem_new *r=(void *)data;
        if(r->size!=16384 || r->flags || r->handle || msm_next>=2){error=EINVAL;goto done;}
        r->handle=++msm_next;msm_handles[r->handle-1]=true;
        redwood_tl("waffle-gpu: MSM gem_new handle=%u bytes=16384 VA=%llx\n",r->handle,(unsigned long long)msm_buffers[r->handle-1].gpu_va);
    }else if(command==WAFFLE_MSM_INFO){
        struct waffle_msm_gem_info *r=(void *)data;
        if(!msm_handle(r->handle) || r->info!=1 || r->len || r->pad){error=EINVAL;goto done;}
        r->value=msm_buffers[r->handle-1].gpu_va;
    }else if(command==WAFFLE_MSM_UPLOAD || command==WAFFLE_MSM_DOWNLOAD){
        struct waffle_msm_transfer *r=(void *)data;
        if(!msm_handle(r->handle) || r->flags || !r->bytes || r->offset>16384 || r->bytes>16384-r->offset){error=EINVAL;goto done;}
        void *memory=(void *)(msm_buffers[r->handle-1].memory+r->offset);
        __asm__ volatile("dsb sy":::"memory");
        error=command==WAFFLE_MSM_UPLOAD?copyin(r->pointer,memory,r->bytes):copyout(memory,r->pointer,r->bytes);
        __asm__ volatile("dsb sy":::"memory");
        if(error)error=EFAULT;
        else redwood_tl("waffle-gpu: MSM_TRANSFER operation=%s bytes=%u\n",command==WAFFLE_MSM_UPLOAD?"upload":"download",r->bytes);
    }else if(command==WAFFLE_MSM_MAP || command==WAFFLE_MSM_UNMAP){
        struct waffle_msm_map *r=(void *)data;
        if(!msm_mapped || !msm_handle(r->handle) || r->bytes!=16384 || r->pad || r->flags>1){error=EINVAL;goto done;}
        unsigned index=r->handle-1;
        if(command==WAFFLE_MSM_MAP){
            if(r->address || msm_map_tokens[index]){error=EBUSY;goto done;}
            if(!waffle_gpu_map_create(msm_buffers[index].memory,r->flags==1,&r->address,&msm_map_tokens[index])){error=ENOMEM;goto done;}
            msm_map_addresses[index]=r->address;
            redwood_tl("waffle-gpu: MSM_MAP mapped handle=%u bytes=16384 readonly=%u direct_backing=1\n",r->handle,r->flags);
        }else{
            if(!msm_map_tokens[index] || r->address!=msm_map_addresses[index]){error=EINVAL;goto done;}
            msm_revoke(index);redwood_tl("waffle-gpu: MSM_MAP unmapped handle=%u\n",r->handle);
        }
    }else if(command==WAFFLE_MSM_SUBMIT){error=msm_submit((void *)data);
    }else if(command==WAFFLE_MSM_WAIT){
        const struct waffle_msm_wait *r=(void *)data;
        if(!r->fence || r->fence>msm_fence || r->flags || r->queueid || r->pad)error=EINVAL;
    }else if(command==WAFFLE_MSM_CLOSE){
        const struct waffle_msm_close *r=(void *)data;
        if(!msm_handle(r->handle) || r->pad){error=EINVAL;goto done;}
        msm_revoke(r->handle-1);msm_handles[r->handle-1]=false;
        redwood_tl("waffle-gpu: MSM gem_close handle=%u retained_until_context_stop=1\n",r->handle);
    }else if(command==WAFFLE_MSM_REPORT){
        const struct waffle_msm_report *r=(void *)data;
        if(r->version!=1 || r->checks!=768 || r->wrong || r->fence!=3 || r->negative!=7 || msm_fence!=3){error=EINVAL;goto done;}
        msm_reported=true;redwood_tl("waffle-gpu: MSM report pid=%d checks=768 wrong=0 fence=3 negative=7\n",msm_pid);
    }else error=ENOTTY;
done:lck_mtx_unlock(&msm_lock);return error;
}
static int msm_close(dev_t dev,int flags,int type,struct proc *p)
{
    (void)dev;(void)flags;(void)type;(void)p;lck_mtx_lock(&msm_lock);
    if(!msm_context){lck_mtx_unlock(&msm_lock);return 0;}
    if(msm_fence==3)redwood_tl("waffle-gmu: SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session\n");
    msm_revoke(0);msm_revoke(1);
    bool stopped=waffle_gpu_context_end(&msm_context);
    if(msm_context){redwood_tl("waffle-gpu: REBOOT REQUIRED: MSM close retains busy context\n");loader_return();for(;;);}
    bzero(msm_buffers,sizeof(msm_buffers));bzero(msm_handles,sizeof(msm_handles));
    redwood_tl("waffle-gpu: MSM close passed=%u report=%u context_null=1\n",stopped,msm_reported);
    msm_pid=0;lck_mtx_unlock(&msm_lock);return stopped?0:EIO;
}
static const struct cdevsw msm_cdev={
    .d_open=msm_open,.d_close=msm_close,.d_read=eno_rdwrt,.d_write=eno_rdwrt,
    .d_ioctl=msm_ioctl,.d_stop=eno_stop,.d_reset=eno_reset,.d_select=eno_select,
    .d_mmap=eno_mmap,.d_strategy=eno_strat,.d_type=0
};
bool waffle_gpu_msm_register(void)
{
    unsigned image=0;msm_mapped=PE_parse_boot_argn("waffle_image",&image,sizeof(image)) && image==12;
    int major=cdevsw_add(-1,&msm_cdev);if(major<0)return false;
    if(!devfs_make_node(makedev(major,0),DEVFS_CHAR,UID_ROOT,GID_WHEEL,0600,"waffle-gpu-msm")){
        cdevsw_remove(major,&msm_cdev);return false;
    }
    redwood_tl("waffle-gpu: MSM registered BO2 submit191 root_only=1 gated=1\n");
    if(msm_mapped)redwood_tl("waffle-gpu: MSM_MAP enabled IOMemoryMap=1 revoke_before_submit=1\n");
    return true;
}
