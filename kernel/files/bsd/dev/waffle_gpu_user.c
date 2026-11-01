/* Root-only bounded diagnostic client. XNU ioctl performs copyin/copyout. */
#include <kern/locks.h>
#include <libkern/libkern.h>
#include <miscfs/devfs/devfs.h>
#include <sys/conf.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include <sys/systm.h>
#include <sys/waffle_gpu_service.h>
#include <sys/waffle_gpu_user.h>
extern void redwood_tl(const char *,...) __printflike(1,2);
extern void loader_return(void);
static LCK_GRP_DECLARE(user_group,"waffle-gpu-user");
static LCK_MTX_DECLARE(user_lock,&user_group);
static struct waffle_gpu_context *user_context;
static int user_pid;
static unsigned user_fence;
static bool user_reported;
static int user_open(dev_t dev,int flags,int type,struct proc *p)
{
    (void)dev;(void)flags;(void)type;
    lck_mtx_lock(&user_lock);
    if(user_context){redwood_tl("waffle-gpu: USERDEV busy_open refused=1 pid=%d\n",proc_pid(p));lck_mtx_unlock(&user_lock);return EBUSY;}
    user_context=waffle_gpu_context_begin();
    if(!user_context){lck_mtx_unlock(&user_lock);return ENXIO;}
    user_pid=proc_pid(p);user_fence=0;user_reported=false;
    redwood_tl("waffle-gpu: USERDEV open pid=%d demand_context=1\n",user_pid);
    redwood_tl("waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1\n");
    lck_mtx_unlock(&user_lock);return 0;
}
static int user_ioctl(dev_t dev,u_long command,caddr_t data,int flags,struct proc *p)
{
    (void)dev;(void)flags;
    lck_mtx_lock(&user_lock);int error=0;
    if(!user_context || proc_pid(p)!=user_pid){error=EPERM;goto done;}
    if(command==WAFFLE_GPU_USER_COPY){
        struct waffle_gpu_user_copy *request=(void *)data;
        if(request->version!=1 || request->words!=256 || request->fence || request->reserved){
            redwood_tl("waffle-gpu: USERDEV invalid_copy refused=1 pid=%d version=%u words=%u\n",user_pid,request->version,request->words);error=EINVAL;goto done;
        }
        if(user_fence>=3){error=E2BIG;goto done;}
        uint32_t output[256];
        struct waffle_gpu_copy_job job={.input=request->input,.output=output,.words=256};
        if(!waffle_gpu_context_copy(user_context,&job) || job.fence!=user_fence+1){error=EIO;goto done;}
        unsigned wrong=0;for(unsigned i=0;i<256;i++)if(output[i]!=request->input[i])++wrong;
        redwood_tl("waffle-gmu: COPY_CALLER fence=%u checked=256 wrong=%u\n",job.fence,wrong);
        if(wrong){error=EIO;goto done;}
        memcpy(request->output,output,sizeof(output));request->fence=job.fence;user_fence=job.fence;
        redwood_tl("waffle-gpu: USERDEV returned pid=%d fence=%u words=256\n",user_pid,user_fence);
    }else if(command==WAFFLE_GPU_USER_REPORT){
        const struct waffle_gpu_user_report *report=(const void *)data;
        if(report->version!=1 || report->checks!=768 || report->wrong || report->last_fence!=3 || report->negative_checks!=5 || user_fence!=3){error=EINVAL;goto done;}
        user_reported=true;
        redwood_tl("waffle-gpu: USERDEV report pid=%d checks=768 wrong=0 fence=3 negative=5\n",user_pid);
    }else{redwood_tl("waffle-gpu: USERDEV unknown_ioctl refused=1 pid=%d\n",user_pid);error=ENOTTY;}
done:
    lck_mtx_unlock(&user_lock);return error;
}
static int user_close(dev_t dev,int flags,int type,struct proc *p)
{
    (void)dev;(void)flags;(void)type;(void)p;
    lck_mtx_lock(&user_lock);
    if(!user_context){lck_mtx_unlock(&user_lock);return 0;}
    bool reported=user_reported;int pid=user_pid;
    if(user_fence==3)redwood_tl("waffle-gmu: SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session\n");
    bool stopped=waffle_gpu_context_end(&user_context);
    if(user_context){redwood_tl("waffle-gpu: REBOOT REQUIRED: user close retains busy context\n");loader_return();for(;;);}
    redwood_tl("waffle-gpu: USERDEV close pid=%d passed=%u report=%u context_null=1\n",pid,stopped,reported);
    user_pid=0;user_fence=0;user_reported=false;
    lck_mtx_unlock(&user_lock);return stopped?0:EIO;
}
static const struct cdevsw user_cdev={
    .d_open=user_open,.d_close=user_close,.d_read=eno_rdwrt,.d_write=eno_rdwrt,
    .d_ioctl=user_ioctl,.d_stop=eno_stop,.d_reset=eno_reset,.d_select=eno_select,
    .d_mmap=eno_mmap,.d_strategy=eno_strat,.d_type=0
};
bool waffle_gpu_user_register(void)
{
    int major=cdevsw_add(-1,&user_cdev);
    if(major<0)return false;
    if(!devfs_make_node(makedev(major,0),DEVFS_CHAR,UID_ROOT,GID_WHEEL,0600,"waffle-gpu-copy")){
        cdevsw_remove(major,&user_cdev);return false;
    }
    redwood_tl("waffle-gpu: USERDEV registered abi=1 pixels=256 mode=0600; no GPU opened\n");
    return true;
}
