"""Prototype generation handles against actual cdev code; runtime unchanged.

Temporary source adaptations are explicitly a design candidate, not a claim
that the runtime allocator/registry already supports descriptor recycling.
"""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
source=ns['source']
source=source.replace('bool live;','bool live;uint32_t handle;')
begin=source.index('static struct drm_bo *drm_buffer(');end=source.index('static void drm_allocation_refused(',begin)
source=source[:begin]+'''static struct drm_bo *drm_buffer(unsigned handle){
 unsigned slot=waffle_gpu_handle_slot(handle);
 return slot<drm_count && drm_bos[slot].live && drm_bos[slot].handle==handle?&drm_bos[slot]:NULL;
}
'''+source[end:]
source=source.replace('(bos[i].handle-1)/64','waffle_gpu_handle_slot(bos[i].handle)/64').replace('(bos[i].handle-1)%64','waffle_gpu_handle_slot(bos[i].handle)%64')
begin=source.index('  if(drm_count>=WAFFLE_GPU_BO_LIMIT)');end=source.index('  struct waffle_gpu_memory *bo=waffle_gpu_context_memory_new',begin)
source=source[:begin]+'''  unsigned slot=WAFFLE_GPU_BO_LIMIT;uint32_t handle=0;
  for(unsigned i=0;i<drm_count;i++)if(!drm_bos[i].live && (handle=waffle_gpu_handle_next(drm_bos[i].handle,i))){slot=i;break;}
  if(slot==WAFFLE_GPU_BO_LIMIT && drm_count<WAFFLE_GPU_BO_LIMIT){slot=drm_count;handle=waffle_gpu_handle_next(0,slot);}
  if(slot==WAFFLE_GPU_BO_LIMIT){error=ENOSPC;goto done;}
'''+source[end:]
old='drm_bos[drm_count]=(struct drm_bo){.memory=bo,.live=true};r->handle=++drm_count;'
assert old in source
source=source.replace(old,'drm_bos[slot]=(struct drm_bo){.memory=bo,.live=true,.handle=handle};if(slot==drm_count)drm_count++;r->handle=handle;')
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
  assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner)==EINVAL && !snapshot_live);
  submit.nr_bos=1;
  assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&submit,0,&owner) && submit.fence==i+1 && !snapshot_live);
  struct waffle_msm_close close={.handle=n.handle};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
  assert(!storage[0].object && live_reclaims==i+1);previous=n.handle;
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
 close.handle=n.handle;assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner));
 assert(!drm_close(0,0,0,&owner) && !stored);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(h+'\n#include "waffle_gpu_handles.h"\n'+ns['parts']['ioc']+ns['uapi']+source+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation',
  '-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST PROTOTYPE cdev:100000 allocate/submit/close cycles reuse one slot, monotonic generations reject stale INFO/CLOSE and duplicate high handles, failed allocation preserves generation, overflow quarantines slot. Registry/fences GPU mocked; temporary source adaptations only, runtime not wired.')
