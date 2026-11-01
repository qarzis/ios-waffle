"""Actual recycling diagnostic and cdev; GPU completion/physical BOs mocked."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-generation-handles-candidate-host.py')}
s=(root/'tools/tests/waffle-generation-handles-candidate-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h'].replace('job->commands[0].bytes==1240','job->commands[0].bytes==32')
h=h.replace('#define _DEFAULT_SOURCE\n','')
h=h.replace('for(unsigned i=0;i<stored;i++)free((void *)storage[i].memory);',
            'for(unsigned i=0;i<stored;i++){free((void *)storage[i].memory);memset(&storage[i],0,sizeof(storage[i]));}')
h=h.replace('job->fence=++context.fence;copies++;return true;',r'''
 const struct waffle_gpu_memory *bo=job->commands[0].buffer;
 const uint32_t *words=(const uint32_t *)(bo->memory+job->commands[0].offset);
 uint32_t expected[9];assert(waffle_writeback_packet(expected,9,1,bo->gpu_va+4096)==9);
 assert(!memcmp(words,expected+1,32));
 memcpy((void *)(bo->memory+4096),waffle_writeback_values,sizeof(waffle_writeback_values));
 job->fence=++context.fence;copies++;return true;''')
body=re.sub(r'^#include .*$', '', (root/'userland/src/waffle_gl_recycle_probe.h').read_text(),flags=re.M)
callbacks=r'''
static unsigned long fail_command;static bool fault_fired,bad_values,accept_stale;
static int probe_ioctl(int fd,unsigned long command,void *data){
 assert(fd==42);
 if(command==fail_command && !fault_fired){fault_fired=true;errno=EIO;return -1;}
 if(accept_stale && command==WAFFLE_MSM_INFO && !drm_buffer(((struct waffle_msm_gem_info *)data)->handle))return 0;
 int error=drm_ioctl(0,command,data,0,&owner);
 if(error){errno=error;return -1;}
 if(bad_values && command==WAFFLE_MSM_SUBMIT){
  struct waffle_msm_submit *submit=data;
  struct waffle_msm_submit_bo *ref=(void *)(uintptr_t)submit->bos;
  uint32_t *memory=(void *)drm_buffer(ref->handle)->memory->memory;memory[1024]^=1;
 }
 return 0;
}
#define ioctl probe_ioctl
#define usleep(value) ((void)(value))
'''
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());
 const unsigned long failures[]={0,WAFFLE_MSM_NEW,WAFFLE_MSM_INFO,WAFFLE_MSM_MAP,
  WAFFLE_MSM_SUBMIT,WAFFLE_MSM_WAIT,WAFFLE_MSM_UNMAP,WAFFLE_MSM_CLOSE,0,0};
 for(unsigned mode=0;mode<sizeof(failures)/sizeof(failures[0]);mode++){
  assert(!drm_open(0,0,0,&owner));fail_command=failures[mode];fault_fired=false;
  bad_values=mode==8;accept_stale=mode==9;
  struct waffle_msm_gem_new anchor={.size=16384,.flags=WAFFLE_GPU_BO_WC|2};
  assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&anchor,0,&owner));
  struct drm_bo *a=drm_buffer(anchor.handle);uint32_t *memory=(void *)a->memory->memory;memory[0]=0x12345678;
  unsigned previous_copies=copies;
  bool ok=waffle_gl_recycle_buffers(42,9000);
  assert(ok==(mode==0));assert(a->live && memory[0]==0x12345678 && !mapped);
  if(ok)assert(drm_issued==9001 && drm_count==2 && stored==2 && copies==previous_copies+1);
  assert(!drm_close(0,0,0,&owner) && !stored);
 }
 assert(!drm_open(0,0,0,&owner));assert(!waffle_gl_recycle_buffers(42,1) && !stored);
 assert(!drm_close(0,0,0,&owner));return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 (p/'test.c').write_text('#define _DEFAULT_SOURCE\n#include "waffle_gpu_writeback.h"\n'+h+
                        ns['ns']['parts']['ioc']+ns['ns']['uapi']+ns['source']+callbacks+body+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',
  '-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined',
  '-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual diagnostic/cdev:9000 recycle cycles with persistent readonly anchor; last recycled BO submits exact qualified writeback packet and checks poisoned output/guards; allocation/info/map/submit/wait/unmap/close/stale-handle/wrong-result failures reject and clean mappings. GPU/storage mocked; not a hardware result.')
