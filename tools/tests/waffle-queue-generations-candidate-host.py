"""Queue slot/generation recycling against unmodified actual cdev."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
source=ns['source']
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 uint32_t ids[32];
 for(unsigned i=0;i<32;i++){
  struct waffle_msm_queue q={0};assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner) && q.id==i+1);
  ids[i]=q.id;
 }
 struct waffle_msm_queue q={0};assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner)==ENOSPC && !q.id);
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&ids[0],0,&owner));
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner) && q.id==33);
 assert(!drm_queue_valid(1) && drm_queue_valid(33) && drm_queue_valid(0));
 struct waffle_msm_gem_new bo={.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&bo,0,&owner));
 struct waffle_msm_submit_bo ref={.handle=bo.handle,.flags=3};
 struct waffle_msm_submit_cmd cmd={.type=1,.size=1240};
 struct waffle_msm_submit request={.flags=0x10,.nr_bos=1,.nr_cmds=1,.bos=(uintptr_t)&ref,.cmds=(uintptr_t)&cmd,.queueid=33};
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner) && request.fence==1 && copies==1);
 request.fence=0;request.queueid=1;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && copies==1 && !snapshot_live);
 struct waffle_msm_wait wait={.fence=1,.queueid=33};
 assert(!drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&wait,0,&owner));wait.queueid=1;
 assert(drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&wait,0,&owner)==EINVAL);
 uint64_t zero=0xdeadbeef;
 struct waffle_msm_queue_query query={.data=(uintptr_t)&zero,.len=8,.id=33};
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_QUERY,(char *)&query,0,&owner) && !zero);
 query.id=1;assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_QUERY,(char *)&query,0,&owner)==EINVAL);
 assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&ids[0],0,&owner)==EINVAL);
 ids[0]=33;
 for(unsigned i=0;i<32;i++)assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&ids[i],0,&owner));
 for(unsigned i=0;i<100000;i++){
  q=(struct waffle_msm_queue){0};assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner));
  assert(q.id==65+i*32 && drm_queue_valid(q.id) && !drm_queue_valid(q.id-32));
  assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&q.id,0,&owner) && !drm_queues);
 }
 drm_queue_generations[0]=1+((UINT32_MAX-1)/32)*32;
 q=(struct waffle_msm_queue){0};assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner) && q.id==34);
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&q.id,0,&owner));
 for(unsigned i=0;i<32;i++)drm_queue_generations[i]=i+1+((UINT32_MAX-(i+1))/32)*32;
 q=(struct waffle_msm_queue){0};assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner)==ENOSPC && !q.id && !drm_queues);
 assert(!drm_close(0,0,0,&owner));return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+source+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',
  '-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined',
  '-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual cdev queues:100000 create/close cycles,32-live bound retained; generation33 submits/waits/queries, stale1 refused before GPU work; generation overflow quarantines instead of wrapping,default0 valid. Unmodified current cdev; GPU mocked.')
