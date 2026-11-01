"""Actual GEM_CLOSE ordering/stale handles; physical reclamation is mocked."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h']
for signature in ['bool waffle_gpu_context_memory_reclaim','bool waffle_gpu_map_revoke']:
 h=re.sub(r'^'+signature+r'.*$','',h,flags=re.M)
h=h.replace('static void loader_return(void){assert(0);}','static void loader_return(void){longjmp(reset_trap,1);}')
h='#define _DEFAULT_SOURCE 1\n#include <setjmp.h>\nstatic jmp_buf reset_trap;\n'+h.replace('#define _DEFAULT_SOURCE\n','')
h+=r'''
static bool fail_revoke;static unsigned reclaim_calls;
bool waffle_gpu_context_memory_reclaim(struct waffle_gpu_context *,struct waffle_gpu_memory *,bool);
bool waffle_gpu_map_revoke(uintptr_t *token){
 assert(held);if(fail_revoke)return false;
 if(*token){assert(mapped);mapped--;*token=0;}return true;
}
'''
callback=r'''
bool waffle_gpu_context_memory_reclaim(struct waffle_gpu_context *c,struct waffle_gpu_memory *b,bool cpu_unmapped){
 assert(held && c==&context && cpu_unmapped);reclaim_calls++;
 unsigned found=0;
 for(unsigned i=0;i<drm_count;i++)if(drm_bos[i].memory==b){
  assert(drm_bos[i].live && !drm_bos[i].user_map && !drm_bos[i].user_address);found++;
 }
 assert(found==1 && b->object);
 if(reclaim_fail)return false;
 free((void *)b->memory);memset(b,0,sizeof(*b));live_reclaims++;return true;
}
'''
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_gem_new n={.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner));
 struct waffle_msm_map m={.handle=n.handle,.bytes=16384};
 assert(!drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&m,0,&owner) && mapped==1);
 struct waffle_msm_close close={.handle=n.handle,.pad=1};
 assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EINVAL && !reclaim_calls && mapped==1);
 close.pad=0;reclaim_fail=1;
 assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EIO);
 assert(reclaim_calls==1 && !mapped && storage[0].object && drm_bos[0].live && !live_reclaims);
 reclaim_fail=0;assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
 assert(reclaim_calls==2 && live_reclaims==1 && !storage[0].object && !drm_bos[0].live);
 assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EINVAL && reclaim_calls==2);
 struct waffle_msm_gem_info info={.handle=1};assert(drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&info,0,&owner)==EINVAL);
 m.address=0;assert(drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&m,0,&owner)==EINVAL);
 struct waffle_msm_submit_bo bo={.handle=1,.flags=3};
 struct waffle_msm_submit_cmd cmd={.type=1,.size=4};
 struct waffle_msm_submit submit={.flags=0x10,.nr_bos=1,.nr_cmds=1,.bos=(uintptr_t)&bo,.cmds=(uintptr_t)&cmd};
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner)==EINVAL && !copies && !snapshot_live);
 assert(!drm_close(0,0,0,&owner) && !stored);
 /* A failed CPU revoke goes to the fatal reset path before the owner can
  * reclaim anything. Only host-fixture cleanup follows the trapped reset. */
 assert(!drm_open(0,0,0,&owner));n=(struct waffle_msm_gem_new){.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner));
 m=(struct waffle_msm_map){.handle=1,.bytes=16384};assert(!drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&m,0,&owner));
 fail_revoke=true;close=(struct waffle_msm_close){.handle=1};
 if(!setjmp(reset_trap)){(void)drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner);assert(0);}
 assert(reclaim_calls==2 && mapped==1 && drm_bos[0].user_map && storage[0].object && drm_bos[0].live);
 free((void *)storage[0].memory);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(h+ns['parts']['ioc']+ns['uapi']+ns['source']+callback+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',
  '-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual cdev:CPU mappings revoked before owner reclaim; owner refusal retains live backing; successful close invalidates INFO/MAP/SUBMIT/double-close handles; failed CPU revoke traps fatal reset before any reclamation. Physical/SMMU reclaim mocked.')
