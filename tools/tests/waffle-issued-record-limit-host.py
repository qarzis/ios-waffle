"""Reproduce the historical cumulative limit using a pinned pre-fix fixture."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
ns['source']=ns['strip']((root/'tools/tests/fixtures/waffle-drm-before-generations.c').read_text()).replace('__asm__ volatile("dsb sy":::"memory");','')
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 for(unsigned i=0;i<WAFFLE_GPU_BO_LIMIT;i++){
  struct waffle_msm_gem_new n={.size=16384,.flags=WAFFLE_GPU_BO_WC};
  assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner) && n.handle==i+1);
  struct waffle_msm_close c={.handle=n.handle};
  assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&c,0,&owner));
  assert(!storage[i].object && live_reclaims==i+1);
 }
 assert(!mapped && live_reclaims==WAFFLE_GPU_BO_LIMIT);
 struct waffle_msm_gem_new n={.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner)==ENOSPC);
 assert(!n.handle && drm_count==WAFFLE_GPU_BO_LIMIT);
 assert(!drm_close(0,0,0,&owner) && !stored);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+ns['source']+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',
  '-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST pinned pre-generation cdev reproduces cumulative8192-record exhaustion despite immediate successful modeled reclamation of every BO and zero live backing. This is a proved persistent-session gap, not a newly observed hardware failure.')
