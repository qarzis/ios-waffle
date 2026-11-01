/* General BO and bounded root-IB transport. Mode13 is kept gated off until the
 * controlled graphics test is complete; this is not an untrusted GL service. */
#include <kern/locks.h>
#include <kern/kalloc.h>
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
_Static_assert(WAFFLE_GPU_SUBMIT_BUFFERS<=WAFFLE_GPU_BO_LIMIT,"Submit references fit the context registry");
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
static void drm_allocation_refused(uint64_t bytes,uint32_t flags,const char *reason)
{
 uint64_t live_bytes=0,retired_bytes=0;unsigned live_count=0,retired_count=0;
 for(unsigned i=0;i<drm_count;i++){
  if(drm_bos[i].live){live_count++;live_bytes+=drm_bos[i].memory->allocation_bytes;}
  else{retired_count++;retired_bytes+=drm_bos[i].memory->allocation_bytes;}
 }
 redwood_tl("waffle-gpu: GENERAL allocation_refused bytes=%llu flags=%x count=%u limit=%u reason=%s live_count=%u live_bytes=%llu retired_count=%u retired_bytes=%llu heap_limit=%u\n",
  (unsigned long long)bytes,flags,drm_count,WAFFLE_GPU_BO_LIMIT,reason,live_count,
  (unsigned long long)live_bytes,retired_count,(unsigned long long)retired_bytes,WAFFLE_GPU_BO_HEAP_BYTES);
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
 redwood_tl("waffle-gpu: GENERAL open pid=%d BO_limit=%u heap_bytes=%u VA_bytes=%u\n",drm_pid,WAFFLE_GPU_BO_LIMIT,WAFFLE_GPU_BO_HEAP_BYTES,WAFFLE_GPU_BO_VA_BYTES);
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
 if(r->flags!=0x10 || r->fence || !r->nr_bos || r->nr_bos>WAFFLE_GPU_BO_LIMIT || !r->nr_cmds ||
    r->in_syncobjs || r->out_syncobjs || r->nr_in_syncobjs || r->nr_out_syncobjs || r->syncobj_stride || r->pad ||
    !drm_queue_valid(r->queueid))return EINVAL;
 /* Snapshot one bounded CPU page of request metadata. Real UI requests are
  * larger than an individual private-BO execution window; keep these two
  * budgets independent and keep request arrays off the kernel stack. */
 uint64_t bytes=(uint64_t)r->nr_bos*sizeof(struct waffle_msm_submit_bo)+
  (uint64_t)r->nr_cmds*(sizeof(struct waffle_msm_submit_cmd)+sizeof(struct waffle_gpu_command));
 if(bytes>16384)return EINVAL;
 void *snapshot=kalloc_data((size_t)bytes,Z_WAITOK|Z_ZERO);
 if(!snapshot)return ENOMEM;
 int error=0;
 struct waffle_msm_submit_bo *bos=snapshot;
 struct waffle_msm_submit_cmd *commands=(void *)(bos+r->nr_bos);
 struct waffle_gpu_command *roots=(void *)(commands+r->nr_cmds);
 if(copyin(r->bos,bos,r->nr_bos*sizeof(*bos)) || copyin(r->cmds,commands,r->nr_cmds*sizeof(*commands))){error=EFAULT;goto done;}
 uint64_t seen[(WAFFLE_GPU_BO_LIMIT+63)/64]={0};uint32_t total=0;
 for(unsigned i=0;i<r->nr_bos;i++){
  struct drm_bo *bo=drm_buffer(bos[i].handle);
  if(!bo || !bos[i].flags || (bos[i].flags&~7u) || (seen[(bos[i].handle-1)/64]&(1ULL<<((bos[i].handle-1)%64))) ||
     (bos[i].presumed && bos[i].presumed!=bo->memory->gpu_va)){error=EINVAL;goto done;}
  seen[(bos[i].handle-1)/64]|=1ULL<<((bos[i].handle-1)%64);
 }
 for(unsigned i=0;i<r->nr_cmds;i++){
  struct waffle_msm_submit_cmd *cmd=&commands[i];
  struct drm_bo *bo=cmd->submit_idx<r->nr_bos?drm_buffer(bos[cmd->submit_idx].handle):NULL;
  redwood_tl("waffle-gpu: GENERAL root index=%u type=%u bo_index=%u offset=%u bytes=%u reloc_count=%u unused_reloc_pointer=%llx\n",i,cmd->type,cmd->submit_idx,cmd->submit_offset,cmd->size,cmd->nr_relocs,(unsigned long long)cmd->relocs);
  /* Mesa softpin leaves relocs uninitialized when nr_relocs is zero.
   * A zero-length array has no pointer to validate or dereference. */
  if(!bo || cmd->type!=1 || cmd->pad || cmd->nr_relocs){error=EINVAL;goto done;}
  roots[i]=(struct waffle_gpu_command){.buffer=bo->memory,.offset=cmd->submit_offset,.bytes=cmd->size};
  if(!waffle_gpu_command_valid(&roots[i]) || cmd->size/4>WAFFLE_GPU_SUBMIT_WORDS){error=EINVAL;goto done;}
  total+=cmd->size/4;
 }
 /* Controlled caller owns data consistency. Root bytes are snapshotted into
  * the private kernel command BO; persistent Mesa data mappings stay stable. */
 __asm__ volatile("dsb sy":::"memory");
 /* All metadata/ranges are checked before the first window. Each whole root
  * retains its position; the existing synchronous completion tail separates
  * adjacent windows without adding an IB level or growing the private BO. */
 unsigned cursor=0,windows=0;
 while(cursor<r->nr_cmds){
  unsigned first=cursor,words=0;
  while(cursor<r->nr_cmds && cursor-first<WAFFLE_GPU_SUBMIT_COMMANDS &&
        roots[cursor].bytes/4<=WAFFLE_GPU_SUBMIT_WORDS-words){
   words+=roots[cursor].bytes/4;cursor++;
  }
  struct waffle_gpu_submit_job job={.commands=roots+first,.count=cursor-first};
  if(!waffle_gpu_context_submit(drm_context,&job) || job.fence!=drm_fence+1){error=EIO;goto done;}
  drm_fence=job.fence;windows++;
  redwood_tl("waffle-gpu: GENERAL submitted fence=%u bos=%u roots=%u words=%u\n",drm_fence,r->nr_bos,job.count,words);
 }
 r->fence=drm_fence;
 redwood_tl("waffle-gpu: GENERAL request_completed fence=%u bos=%u roots=%u words=%u windows=%u metadata_bytes=%llu\n",drm_fence,r->nr_bos,r->nr_cmds,total,windows,(unsigned long long)bytes);
done:
 kfree_data(snapshot,(size_t)bytes);
 return error;
}
static int drm_ioctl(dev_t dev,u_long command,caddr_t data,int flags,struct proc *p)
{
 (void)dev;(void)flags;lck_mtx_lock(&drm_lock);int error=0;
 if(!drm_context || proc_pid(p)!=drm_pid){error=EPERM;goto done;}
 if(command==WAFFLE_MSM_PARAM){error=drm_param((void *)data);
 }else if(command==WAFFLE_MSM_NEW){
  struct waffle_msm_gem_new *r=(void *)data;
  if(r->handle || !waffle_gpu_registry_flags(r->size,r->flags)){error=EINVAL;goto done;}
  if(drm_count>=WAFFLE_GPU_BO_LIMIT){
   drm_allocation_refused(r->size,r->flags,"slots");
   error=ENOSPC;goto done;
  }
  struct waffle_gpu_memory *bo=waffle_gpu_context_memory_new(drm_context,r->size,r->flags);
  if(!bo){
   drm_allocation_refused(r->size,r->flags,"registry");
   error=ENOMEM;goto done;
  }
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
  if(!bo || r->pad){error=EINVAL;goto done;}
  uint32_t bytes=bo->memory->allocation_bytes;
  drm_unmap(bo);
  if(!waffle_gpu_context_memory_reclaim(drm_context,bo->memory,!bo->user_map && !bo->user_address)){error=EIO;goto done;}
  bo->live=false;
  redwood_tl("waffle-gpu: GENERAL bo_retired handle=%u bytes=%u backing_retained=0\n",r->handle,bytes);
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
 redwood_tl("waffle-gpu: GENERAL registered root_only=1 gated=1 BO_limit=%u\n",WAFFLE_GPU_BO_LIMIT);return true;
}
