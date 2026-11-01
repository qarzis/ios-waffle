"""Reproduce historical queue exhaustion with a pinned pre-queue-fix cdev."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
ns['source']=ns['strip']((root/'tools/tests/fixtures/waffle-drm-before-queue-reuse.c').read_text()).replace('__asm__ volatile("dsb sy":::"memory");','')
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 for(unsigned i=0;i<32;i++){
  struct waffle_msm_queue q={0};
  assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner) && q.id==i+1);
  uint32_t id=q.id;
  assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&id,0,&owner));
  assert(!drm_queues && !drm_queue_valid(id) && drm_queue_valid(0));
 }
 struct waffle_msm_queue q={0};
 assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner)==ENOSPC && !q.id && !drm_queues);
 assert(!stored && !mapped && !copies);
 assert(!drm_close(0,0,0,&owner));return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+ns['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
  '-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined',
  '-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST pinned pre-queue-fix cdev:32 create/close queue cycles leave zero live queues,33rd NEW returns ENOSPC; no GPU jobs or BOs. Persistent-lifetime gap, not an observed hardware failure; runtime unchanged.')
