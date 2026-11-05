/* Isolated PID1 lease contention probe. No GPU command runs while manually held. */
#include <pthread.h>
struct waffle_lease_writer {
 IOSurfaceRef surface;
 kern_return_t locked,unlocked;
};
static void *waffle_lease_writer_main(void *p)
{
 struct waffle_lease_writer *writer=p;
 writer->locked=IOSurfaceLock(writer->surface,0,NULL);
 if(writer->locked==KERN_SUCCESS)writer->unlocked=IOSurfaceUnlock(writer->surface,0,NULL);
 return NULL;
}
static bool check_surface_lease(void)
{
 int fd=existing_gpu_fd();if(fd<0)return false;
 bool ok=false,leased=false,started=false,saw_waiter=false;
 pthread_t thread;struct waffle_lease_writer writer={.surface=hook_surface,.locked=KERN_FAILURE,.unlocked=KERN_FAILURE};
 struct waffle_msm_surface imported={.surface=IOSurfaceGetID(hook_surface)};
 struct waffle_msm_surface_lease lease={0};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,&imported) || !imported.handle)goto done;
 lease=(struct waffle_msm_surface_lease){.handle=imported.handle,.operation=1};
 if(IOSurfaceLock(hook_surface,0,NULL)!=KERN_SUCCESS)goto done;
 int busy=ioctl(fd,WAFFLE_MSM_SURFACE_LEASE_TEST,&lease),busy_errno=errno;
 kern_return_t unlocked=IOSurfaceUnlock(hook_surface,0,NULL);
 if(busy!=-1 || busy_errno!=EBUSY || unlocked!=KERN_SUCCESS)goto done;
 if(ioctl(fd,WAFFLE_MSM_SURFACE_LEASE_TEST,&lease) || lease.active!=1 || lease.waiting_writers)goto done;
 leased=true;
 kern_return_t avoid=IOSurfaceLock(hook_surface,kIOSurfaceLockAvoidSync,NULL);
 if(avoid==KERN_SUCCESS)IOSurfaceUnlock(hook_surface,0,NULL);
 if(avoid!=kIOReturnCannotLock)goto done;
 if(IOSurfaceLock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)goto done;
 if(IOSurfaceUnlock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)goto done;
 if(pthread_create(&thread,NULL,waffle_lease_writer_main,&writer))goto done;
 started=true;
 for(unsigned i=0;i<200;i++){
  lease=(struct waffle_msm_surface_lease){.handle=imported.handle,.operation=3};
  if(ioctl(fd,WAFFLE_MSM_SURFACE_LEASE_TEST,&lease) || lease.active!=1)goto done;
  if(lease.waiting_writers==1){saw_waiter=true;break;}
  usleep(1000);
 }
 if(!saw_waiter)goto done;
 lease=(struct waffle_msm_surface_lease){.handle=imported.handle,.operation=2};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_LEASE_TEST,&lease) || lease.active || lease.waiting_writers)goto done;
 leased=false;
 if(pthread_join(thread,NULL))goto done;started=false;
 ok=writer.locked==KERN_SUCCESS && writer.unlocked==KERN_SUCCESS;
done:
 if(leased){lease=(struct waffle_msm_surface_lease){.handle=imported.handle,.operation=2};if(ioctl(fd,WAFFLE_MSM_SURFACE_LEASE_TEST,&lease))ok=false;}
 if(started && pthread_join(thread,NULL))ok=false;
 printf("waffle-gl-surface-lease: passed=%u sid=%u CPU_writer_refused_GPU_lease=%u AvoidSync_refused=%u reader_allowed=%u kernel_waiter_seen=%u writer_resumed=%u manual_no_GPU=1\n",ok,imported.surface,ok,ok,ok,saw_waiter,writer.locked==KERN_SUCCESS && writer.unlocked==KERN_SUCCESS);
 close(fd);return ok;
}
