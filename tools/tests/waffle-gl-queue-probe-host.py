"""Actual queue diagnostic on historical and current cdev; physical GPU mocked."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
def load(name):
 ns={'__file__':str(root/'tools/tests'/name)}
 s=(root/'tools/tests'/name).read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
 return ns
queue=load('waffle-queue-generations-candidate-host.py')
probe=load('waffle-gl-recycle-probe-host.py')
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_queue anchor={0};
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&anchor,0,&owner) && anchor.id==1);
 struct waffle_msm_gem_new bo={.size=16384,.flags=WAFFLE_GPU_BO_WC|2};
 assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&bo,0,&owner));
 uint32_t *memory=(void *)drm_buffer(bo.handle)->memory->memory;memory[0]=0x12345678;
 bool ok=waffle_gl_queue_probe_begin(42);
 assert(ok==CANDIDATE && drm_queue_valid(anchor.id));
 if(ok){
  assert(waffle_gl_recycle_queue==3170 && waffle_gl_recycle_stale_queue==2);
  assert(!drm_queue_valid(2) && drm_queue_valid(3170));
  assert(waffle_gl_recycle_buffers(42,9000));
  assert(copies==1 && context.fence==1 && memory[0]==0x12345678 && !mapped);
  assert(waffle_gl_queue_probe_end(42) && !drm_queue_valid(3170));
 }else assert(!copies && drm_queues==1 && memory[0]==0x12345678);
 assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&anchor.id,0,&owner));
 struct waffle_msm_close close={.handle=bo.handle};
 assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
 assert(!drm_close(0,0,0,&owner));return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for candidate,source in [(False,queue['ns']['strip']((root/'tools/tests/fixtures/waffle-drm-before-queue-reuse.c').read_text()).replace('__asm__ volatile("dsb sy":::"memory");','')),(True,queue['source'])]:
  (p/'test.c').write_text('#define _DEFAULT_SOURCE\n#define WAFFLE_GL_QUEUE_RECYCLE 1\n'+
   f'#define CANDIDATE {int(candidate)}\n#include "waffle_gpu_writeback.h"\n'+probe['h']+
   queue['ns']['parts']['ioc']+queue['ns']['uapi']+source+probe['callbacks']+probe['body']+test)
  subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',
   '-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined',
   '-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('HOST actual diagnostic:pinned historical cdev fails queue churn with anchored queue; unmodified actual cdev passes100 queue generations plus9000 BOcycles, stalequeue2 submit refused before GPU, activequeue3170 submits exact writeback/waits/checks poison+guards, anchor preserved/cleanup balanced. Actual queue runtime wired; GPU mocked.')
