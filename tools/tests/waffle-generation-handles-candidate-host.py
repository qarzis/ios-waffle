"""Generation handles against unmodified actual cdev; GPU allocation mocked."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
source=ns['source']
h=ns['h'];begin=h.index('struct waffle_gpu_memory *waffle_gpu_context_memory_new(');end=h.index('bool waffle_gpu_memory_map(',begin)
h=h[:begin]+r'''
static bool fail_memory;
struct waffle_gpu_memory *waffle_gpu_context_memory_new(struct waffle_gpu_context *c,uint64_t bytes,uint32_t flags){
 assert(held && c==&context);if(fail_memory)return NULL;
 unsigned slot=0;while(slot<WAFFLE_GPU_BO_LIMIT && storage[slot].object)slot++;
 assert(slot<WAFFLE_GPU_BO_LIMIT);if(slot>=stored)stored=slot+1;
 struct waffle_gpu_memory *bo=&storage[slot];
 *bo=(struct waffle_gpu_memory){.object=slot+1,.bytes=bytes,.allocation_bytes=(bytes+16383)&~16383,.flags=flags,.gpu_va=0x100000000ULL+slot*16384,.published=true};
 bo->memory=(uintptr_t)calloc(1,bo->allocation_bytes);assert(bo->memory);return bo;
}
'''+h[end:]
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 uint32_t previous=0;
 for(unsigned i=0;i<100000;i++){
  struct waffle_msm_gem_new n={.size=16384,.flags=WAFFLE_GPU_BO_WC};
  assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner));
  assert(n.handle==(i?previous+WAFFLE_GPU_BO_LIMIT:1) && drm_count==1);
  assert(waffle_gpu_handle_slot(n.handle)==0 && drm_buffer(n.handle));
  if(previous){
   struct waffle_msm_gem_info stale={.handle=previous};
   assert(!drm_buffer(previous) && drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&stale,0,&owner)==EINVAL);
   struct waffle_msm_close close={.handle=previous};assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EINVAL);
  }
  struct waffle_msm_submit_bo refs[2]={{.handle=n.handle,.flags=3},{.handle=n.handle,.flags=3}};
  struct waffle_msm_submit_cmd cmd={.type=1,.size=1240};
  struct waffle_msm_submit submit={.flags=0x10,.nr_bos=2,.nr_cmds=1,.bos=(uintptr_t)refs,.cmds=(uintptr_t)&cmd};
  if(i==1){
   struct waffle_msm_map stale_map={.handle=previous,.bytes=16384};
   assert(drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&stale_map,0,&owner)==EINVAL && !mapped);
   refs[0].handle=previous;submit.nr_bos=1;
   assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner)==EINVAL && copies==i && !snapshot_live);
   refs[0].handle=n.handle;submit.nr_bos=2;
  }
  assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner)==EINVAL && !snapshot_live);
  submit.nr_bos=1;
  assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner) && submit.fence==i+1 && !snapshot_live);
  struct waffle_msm_close close={.handle=n.handle};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
  assert(!storage[0].object && !drm_bos[0].memory && live_reclaims==i+1);previous=n.handle;
 }
 assert(stored==1 && copies==100000 && drm_count==1);
 /* A failed allocation must leave the slot's generation unchanged. */
 fail_memory=true;struct waffle_msm_gem_new n={.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner)==ENOMEM && !n.handle && drm_bos[0].handle==previous);
 fail_memory=false;assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner) && n.handle==previous+WAFFLE_GPU_BO_LIMIT);
 struct waffle_msm_close close={.handle=n.handle};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
 /* Exhausted generations quarantine the slot instead of wrapping. */
 drm_bos[0].handle=1+((UINT32_MAX-1)/WAFFLE_GPU_BO_LIMIT)*WAFFLE_GPU_BO_LIMIT;
 assert(!waffle_gpu_handle_next(drm_bos[0].handle,0));
 n=(struct waffle_msm_gem_new){.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner) && n.handle==2 && drm_count==2);
 assert(!drm_bos[0].memory && drm_bos[1].memory==&storage[0]);
 drm_allocation_refused(16384,WAFFLE_GPU_BO_WC,"test");
 close.handle=n.handle;assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
 unsigned issued=drm_issued;drm_issued=UINT32_MAX;
 n=(struct waffle_msm_gem_new){.size=16384,.flags=WAFFLE_GPU_BO_WC};
 assert(drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&n,0,&owner)==ENOSPC && !n.handle);
 drm_issued=issued;
 assert(!drm_close(0,0,0,&owner) && !stored);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(h+'\n#include "waffle_gpu_handles.h"\n'+ns['parts']['ioc']+ns['uapi']+source+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation',
  '-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual cdev:100000 allocate/submit/close cycles reuse one slot, monotonic generations reject stale INFO/CLOSE and duplicate high handles, failed allocation preserves generation, overflow quarantines slot. Registry/fences GPU mocked; no cdev source adaptations.')
