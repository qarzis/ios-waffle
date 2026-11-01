/* General BO and bounded root-IB transport. Mode13 is kept gated off until the
 * controlled graphics test is complete; this is not an untrusted GL service. */
#include <kern/locks.h>
#include <libkern/libkern.h>
#include <miscfs/devfs/devfs.h>
#include <sys/conf.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include <sys/systm.h>
#include <sys/waffle_gpu_service.h>
#include <sys/waffle_gpu_msm.h>
#include <sys/waffle_gpu_map.h>
#include <sys/waffle_gpu_registry.h>
#include <sys/waffle_gpu_va.h>
extern void redwood_tl(const char *,...) __printflike(1,2);
extern void loader_return(void);
static LCK_GRP_DECLARE(drm_group,"waffle-gpu-general");
static LCK_MTX_DECLARE(drm_lock,&drm_group);
struct drm_bo {
 struct waffle_gpu_memory *memory;
 uintptr_t user_map;
 uint64_t user_address;
 bool live;
};
static struct drm_bo drm_bos[WAFFLE_GPU_BO_LIMIT];
static struct waffle_gpu_context *drm_context;
static unsigned drm_count,drm_fence;
static int drm_pid;
static uint32_t drm_queues;
static unsigned drm_next_queue;
static bool drm_queue_valid(uint32_t id)
{
 return id==0 || (id<=32 && (drm_queues&(1u<<(id-1))));
}
static struct drm_bo *drm_buffer(unsigned handle)
{
 return handle && handle<=drm_count && drm_bos[handle-1].live?&drm_bos[handle-1]:NULL;
}
static void drm_unmap(struct drm_bo *bo)
{
 if(!waffle_gpu_map_revoke(&bo->user_map)){
  redwood_tl("waffle-gpu: REBOOT REQUIRED: general BO user mapping retained\n");loader_return();for(;;);
 }
 bo->user_address=0;
}
static int drm_open(dev_t dev,int flags,int type,struct proc *p)
{
 (void)dev;(void)flags;(void)type;lck_mtx_lock(&drm_lock);int error=0;
 if(drm_context){error=EBUSY;goto done;}
 drm_context=waffle_gpu_context_begin();if(!drm_context){error=ENXIO;goto done;}
 drm_count=drm_fence=0;drm_queues=0;drm_next_queue=0;drm_pid=proc_pid(p);bzero(drm_bos,sizeof(drm_bos));
 redwood_tl("waffle-gpu: GENERAL open pid=%d BO_limit=32 heap_bytes=33554432\n",drm_pid);
done:lck_mtx_unlock(&drm_lock);return error;
}
static int drm_param(struct waffle_msm_param *r)
{
 if(r->pipe!=0x10 || r->len || r->pad)return EINVAL;
 /* Actual PJD110 live DT and matching Qualcomm gen7_9_1 core table; see
  * forensic-audit/E35-board-params.json. No no-op shim values are inferred. */
 switch(r->param){
 case 1:r->value=750;break;
 case 2:r->value=3u*1024u*1024u;break;
 case 3:r->value=0x43051401u;break;
 case 4:r->value=903000000u;break; /* Native available maximum, not current clock. */
 case 6:r->value=0x01000000;break; /* Programmed GEN7_UCHE_GMEM_RANGE_MIN. */
 case 7:r->value=1;break; /* One synchronous diagnostic queue. */
 case 15:r->value=WAFFLE_GPU_LOWER_LIMIT;break;
 case 20:r->value=0x1fffffffff000ULL;break; /* Programmed UCHE trap base. */
 default:return ENOTSUP;
 }
 return 0;
}
static int drm_submit(struct waffle_msm_submit *r)
{
 redwood_tl("waffle-gpu: GENERAL request flags=%x fence=%u bos=%u roots=%u queue=%u\n",r->flags,r->fence,r->nr_bos,r->nr_cmds,r->queueid);
 if(r->flags!=0x10 || r->fence || !r->nr_bos || r->nr_bos>32 || !r->nr_cmds || r->nr_cmds>WAFFLE_GPU_SUBMIT_COMMANDS ||
    r->in_syncobjs || r->out_syncobjs || r->nr_in_syncobjs || r->nr_out_syncobjs || r->syncobj_stride || r->pad ||
    !drm_queue_valid(r->queueid))return EINVAL;
 struct waffle_msm_submit_bo bos[32];struct waffle_msm_submit_cmd commands[WAFFLE_GPU_SUBMIT_COMMANDS];
 struct waffle_gpu_command roots[WAFFLE_GPU_SUBMIT_COMMANDS];
 if(copyin(r->bos,bos,r->nr_bos*sizeof(*bos)) || copyin(r->cmds,commands,r->nr_cmds*sizeof(*commands)))return EFAULT;
 uint32_t seen=0,total=0;
 for(unsigned i=0;i<r->nr_bos;i++){
  struct drm_bo *bo=drm_buffer(bos[i].handle);
  if(!bo || !bos[i].flags || (bos[i].flags&~7u) || (seen&(1u<<(bos[i].handle-1))) ||
     (bos[i].presumed && bos[i].presumed!=bo->memory->gpu_va))return EINVAL;
  seen|=1u<<(bos[i].handle-1);
 }
 for(unsigned i=0;i<r->nr_cmds;i++){
  struct waffle_msm_submit_cmd *cmd=&commands[i];
  struct drm_bo *bo=cmd->submit_idx<r->nr_bos?drm_buffer(bos[cmd->submit_idx].handle):NULL;
  redwood_tl("waffle-gpu: GENERAL root index=%u type=%u bo_index=%u offset=%u bytes=%u reloc_count=%u unused_reloc_pointer=%llx\n",i,cmd->type,cmd->submit_idx,cmd->submit_offset,cmd->size,cmd->nr_relocs,(unsigned long long)cmd->relocs);
  /* Mesa softpin leaves relocs uninitialized when nr_relocs is zero.
   * A zero-length array has no pointer to validate or dereference. */
  if(!bo || cmd->type!=1 || cmd->pad || cmd->nr_relocs)return EINVAL;
  roots[i]=(struct waffle_gpu_command){.buffer=bo->memory,.offset=cmd->submit_offset,.bytes=cmd->size};
  if(!waffle_gpu_command_valid(&roots[i]) || cmd->size/4>WAFFLE_GPU_SUBMIT_WORDS-total)return EINVAL;
  total+=cmd->size/4;
 }
 /* Controlled caller owns data consistency. Root bytes are snapshotted into
  * the private kernel command BO; persistent Mesa data mappings stay stable. */
 __asm__ volatile("dsb sy":::"memory");
 struct waffle_gpu_submit_job job={.commands=roots,.count=r->nr_cmds};
 if(!waffle_gpu_context_submit(drm_context,&job) || job.fence!=drm_fence+1)return EIO;
 drm_fence=job.fence;r->fence=job.fence;
 redwood_tl("waffle-gpu: GENERAL submitted fence=%u bos=%u roots=%u words=%u\n",drm_fence,r->nr_bos,r->nr_cmds,total);
 return 0;
}
static int drm_ioctl(dev_t dev,u_long command,caddr_t data,int flags,struct proc *p)
{
 (void)dev;(void)flags;lck_mtx_lock(&drm_lock);int error=0;
 if(!drm_context || proc_pid(p)!=drm_pid){error=EPERM;goto done;}
 if(command==WAFFLE_MSM_PARAM){error=drm_param((void *)data);
 }else if(command==WAFFLE_MSM_NEW){
  struct waffle_msm_gem_new *r=(void *)data;
  if(r->handle || !waffle_gpu_registry_flags(r->size,r->flags)){error=EINVAL;goto done;}
  if(drm_count>=32){error=ENOSPC;goto done;}
  struct waffle_gpu_memory *bo=waffle_gpu_context_memory_new(drm_context,r->size,r->flags);
  if(!bo){error=ENOMEM;goto done;}
  drm_bos[drm_count]=(struct drm_bo){.memory=bo,.live=true};r->handle=++drm_count;
  redwood_tl("waffle-gpu: GENERAL gem_new handle=%u bytes=%u allocated=%u flags=%x VA=%llx\n",r->handle,bo->bytes,bo->allocation_bytes,bo->flags,(unsigned long long)bo->gpu_va);
 }else if(command==WAFFLE_MSM_INFO){
  struct waffle_msm_gem_info *r=(void *)data;struct drm_bo *bo=drm_buffer(r->handle);
  if(!bo || r->pad){error=EINVAL;goto done;}
  if(r->info==2){if(r->len>64)error=EINVAL;goto done;} /* Optional debug label. */
  if(r->len){error=EINVAL;goto done;}
  if(r->info==0)r->value=(uint64_t)r->handle<<32;
  else if(r->info==1)r->value=bo->memory->gpu_va;
  else if(r->info==5)r->value=bo->memory->flags;
  else error=ENOTSUP;
 }else if(command==WAFFLE_MSM_MAP || command==WAFFLE_MSM_UNMAP){
  struct waffle_msm_map *r=(void *)data;struct drm_bo *bo=drm_buffer(r->handle);
  if(!bo || r->pad || r->flags>1){error=EINVAL;goto done;}
  if(command==WAFFLE_MSM_MAP){
   if(!r->bytes || r->bytes>bo->memory->bytes || r->address || bo->user_map){error=EINVAL;goto done;}
   if(!waffle_gpu_memory_map(bo->memory,r->flags==1,&r->address,&bo->user_map)){error=ENOMEM;goto done;}
   bo->user_address=r->address;
  }else{if(r->address!=bo->user_address || !bo->user_map){error=EINVAL;goto done;}drm_unmap(bo);}
 }else if(command==WAFFLE_MSM_SUBMIT){error=drm_submit((void *)data);
 }else if(command==WAFFLE_MSM_WAIT){
  struct waffle_msm_wait *r=(void *)data;if(!r->fence || r->fence>drm_fence || r->flags || r->pad || !drm_queue_valid(r->queueid))error=EINVAL;
 }else if(command==WAFFLE_MSM_CPU_PREP){
  struct waffle_msm_cpu_prep *r=(void *)data;if(!drm_buffer(r->handle) || (r->op&~15u))error=EINVAL;
 }else if(command==WAFFLE_MSM_CPU_FINI){if(!drm_buffer(((struct waffle_msm_cpu_fini *)data)->handle))error=EINVAL;
 }else if(command==WAFFLE_MSM_MADVISE){
  struct waffle_msm_madvise *r=(void *)data;if(!drm_buffer(r->handle) || r->madv>1){error=EINVAL;goto done;}r->retained=1;
 }else if(command==WAFFLE_MSM_QUEUE_NEW){
  struct waffle_msm_queue *r=(void *)data;if(r->flags || r->prio || r->id){error=EINVAL;goto done;}
  if(drm_next_queue==32){error=ENOSPC;goto done;}
  r->id=++drm_next_queue;drm_queues|=1u<<(r->id-1);
  redwood_tl("waffle-gpu: GENERAL queue_new id=%u priority=0 serialized=1\n",r->id);
 }else if(command==WAFFLE_MSM_QUEUE_CLOSE){uint32_t id=*(uint32_t *)data;
  if(!id || !drm_queue_valid(id)){error=EINVAL;goto done;}
  drm_queues&=~(1u<<(id-1));
 }else if(command==WAFFLE_MSM_QUEUE_QUERY){
  struct waffle_msm_queue_query *r=(void *)data;uint64_t zero=0;
  if(!r->id || !drm_queue_valid(r->id) || r->param || r->pad || r->len!=8){error=EINVAL;goto done;}
  if(copyout(&zero,r->data,8))error=EFAULT;
 }else if(command==WAFFLE_MSM_CLOSE){
  struct waffle_msm_close *r=(void *)data;struct drm_bo *bo=drm_buffer(r->handle);
  if(!bo || r->pad){error=EINVAL;goto done;}drm_unmap(bo);bo->live=false;
 }else error=ENOTTY;
done:
 if(error)redwood_tl("waffle-gpu: GENERAL ioctl_refused op=%x error=%d pid=%d\n",(unsigned)(command&255),error,proc_pid(p));
 lck_mtx_unlock(&drm_lock);return error;
}
static int drm_close(dev_t dev,int flags,int type,struct proc *p)
{
 (void)dev;(void)flags;(void)type;(void)p;lck_mtx_lock(&drm_lock);
 if(!drm_context){lck_mtx_unlock(&drm_lock);return 0;}
 for(unsigned i=0;i<drm_count;i++)drm_unmap(&drm_bos[i]);
 bool ok=waffle_gpu_context_end(&drm_context);
 if(drm_context){redwood_tl("waffle-gpu: REBOOT REQUIRED: general GPU context retained\n");loader_return();for(;;);}
 redwood_tl("waffle-gpu: GENERAL close passed=%u completed=%u buffers=%u context_null=1\n",ok,drm_fence,drm_count);
 bzero(drm_bos,sizeof(drm_bos));drm_pid=0;lck_mtx_unlock(&drm_lock);return ok?0:EIO;
}
static const struct cdevsw drm_cdev={
 .d_open=drm_open,.d_close=drm_close,.d_read=eno_rdwrt,.d_write=eno_rdwrt,
 .d_ioctl=drm_ioctl,.d_stop=eno_stop,.d_reset=eno_reset,.d_select=eno_select,
 .d_mmap=eno_mmap,.d_strategy=eno_strat,.d_type=0
};
bool waffle_gpu_drm_register(void)
{
 int major=cdevsw_add(-1,&drm_cdev);if(major<0)return false;
 if(!devfs_make_node(makedev(major,0),DEVFS_CHAR,UID_ROOT,GID_WHEEL,0600,"waffle-gpu-drm")){
  cdevsw_remove(major,&drm_cdev);return false;
 }
 redwood_tl("waffle-gpu: GENERAL registered root_only=1 gated=1 BO_limit=32\n");return true;
}
