"""Actual cdev replay of E53 metadata, with GPU execution mocked."""
from pathlib import Path
import json,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
record=json.loads((root/'work/waffle/gpu/forensic-audit/E53-first-submit.json').read_text())
h=ns['h'];begin=h.index('bool waffle_gpu_context_submit(');end=h.index('bool waffle_gpu_context_end(',begin)
h=h[:begin]+r'''
static struct waffle_gpu_command expected_commands[57];
static unsigned next_root,attempted,fail_at;
bool waffle_gpu_context_submit(struct waffle_gpu_context *c,struct waffle_gpu_submit_job *job){
 assert(held && c==&context && job->count && job->count<=16);
 unsigned words=0;
 for(unsigned i=0;i<job->count;i++){
  assert(next_root<57);const struct waffle_gpu_command *a=&job->commands[i],*b=&expected_commands[next_root++];
  assert(a->buffer==b->buffer && a->offset==b->offset && a->bytes==b->bytes);
  words+=a->bytes/4;
 }
 assert(words<=1536);attempted++;
 if(fail_at && attempted==fail_at)return false;
 job->fence=++context.fence;return true;
}
'''+h[end:]
fixture='static const unsigned descriptors[][3]={'+','.join(
 '{%d,%d,%d}'%(c['submit_idx'],c['offset'],c['bytes']) for c in record['commands'])+'};\n'
t=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_submit_bo bos[233];struct waffle_msm_submit_cmd commands[57];
 for(unsigned i=0;i<233;i++){
  struct waffle_msm_gem_new r={.size=(i==9 || i==232)?4194304:16384,.flags=WAFFLE_GPU_BO_WC};
  assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner));
  bos[i]=(struct waffle_msm_submit_bo){.handle=r.handle,.flags=3};
 }
 for(unsigned i=0;i<57;i++){
  commands[i]=(struct waffle_msm_submit_cmd){.type=1,.submit_idx=descriptors[i][0],
   .submit_offset=descriptors[i][1],.size=descriptors[i][2]};
  expected_commands[i]=(struct waffle_gpu_command){.buffer=&storage[descriptors[i][0]],
   .offset=descriptors[i][1],.bytes=descriptors[i][2]};
 }
 struct waffle_msm_submit r={.flags=0x10,.nr_bos=233,.nr_cmds=57,.bos=(uintptr_t)bos,.cmds=(uintptr_t)commands};
 snapshot_fail=1;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==ENOMEM && !snapshot_live && !attempted);snapshot_fail=0;
 uint64_t valid=r.cmds;r.cmds=1;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EFAULT && !snapshot_live && !attempted);r.cmds=valid;
 r.nr_cmds=0xffffffffu;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EINVAL && !snapshot_live && !attempted);r.nr_cmds=57;
 r.nr_bos=4096;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EINVAL && !snapshot_live && !attempted);r.nr_bos=233;
 /* A malformed LAST root prevents all earlier windows from being published. */
 unsigned bytes=commands[56].size;commands[56].size=1537*4;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EINVAL && !snapshot_live && !attempted);commands[56].size=bytes;
 unsigned index=commands[56].submit_idx;commands[56].submit_idx=233;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EINVAL && !snapshot_live && !attempted);commands[56].submit_idx=index;
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner));
 assert(r.fence==5 && context.fence==5 && next_root==57 && attempted==5 && !snapshot_live);
 struct waffle_msm_wait w={.fence=5};assert(!drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&w,0,&owner));
 w.fence=6;assert(drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&w,0,&owner)==EINVAL);
 /* Failure in the third window stops publication, frees CPU metadata, and
  * leaves backing to the existing parent teardown. */
 r.fence=0;next_root=attempted=0;fail_at=3;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&r,0,&owner)==EIO);
 assert(!r.fence && attempted==3 && context.fence==7 && drm_fence==7 && !snapshot_live && stored==233);
 assert(!drm_close(0,0,0,&owner) && !stored && !drm_context);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(h+ns['parts']['ioc']+ns['uapi']+ns['source']+fixture+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',
  '-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual cdev:233 BO references/57 measured roots admitted using bounded offstack metadata; five ordered windows/final fence5/wait; allocation/copyin/metadata budget/invalid-last-root failures submit nothing; third-window failure stops later work/frees snapshot/retains233 BOs until parent stop. GPU mocked, no hardware claim.')
