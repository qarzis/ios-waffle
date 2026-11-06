"""Actual cdev native submit/wait translation and pre-publication refusals."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')};s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=re.sub(r'^bool waffle_gpu_context_submit.*$','',ns['h'],flags=re.M)
h+=r'''
static unsigned fail_submit,commands_seen;
bool waffle_gpu_context_submit(struct waffle_gpu_context *c,struct waffle_gpu_submit_job *j){
 assert(held && c==&context && j->count && j->count<=16);copies++;
 for(unsigned i=0;i<j->count;i++)assert(j->commands[i].buffer && j->commands[i].bytes==32);
 commands_seen+=j->count;if(fail_submit)return false;j->fence=++context.fence;return true;
}
'''
t=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_unixnu_call c={.version=2,.method=2,.input_bytes=16,.output_bytes=8};
 struct waffle_unixnu_alloc a={16384,12,0};memcpy(c.payload,&a,16);assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner));uint64_t handle;memcpy(&handle,c.payload,8);
 struct waffle_unixnu_map map={handle,0x10f000000ULL,3,0,2,0};c.method=3;c.input_bytes=sizeof(map);memcpy(c.payload,&map,sizeof(map));assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner));
 struct waffle_unixnu_submit s={.count=1,.buffers={{handle,0x10f000000ULL,32}}};
 c.method=5;c.input_bytes=sizeof(s);memcpy(c.payload,&s,sizeof(s));
 s.buffers[0].bytes=0;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies && !snapshot_live);
 s.buffers[0].bytes=32;s.buffers[0].iova=map.iova+16384;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies && !snapshot_live);
 s.buffers[0].iova=map.iova;s.queue=1;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==ENOTSUP && !copies);
 s.queue=0;s.wait_fence=1;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies);
 s.wait_fence=0;s.count=2;s.buffers[1]=(struct waffle_unixnu_ib){handle,map.iova,3};memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies && !snapshot_live);
 s.count=129;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies);
 s.count=1;s.buffers[0].handle=handle+(1ULL<<32);memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies && !snapshot_live);
 s.buffers[0].handle=handle;drm_buffer(handle)->unixnu_mapped=false;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL && !copies && !snapshot_live);drm_buffer(handle)->unixnu_mapped=true;
 snapshot_fail=1;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==ENOMEM && !copies && !snapshot_live);snapshot_fail=0;
 s.count=1;memcpy(c.payload,&s,sizeof(s));assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner) && copies==1 && !snapshot_live);uint64_t f;memcpy(&f,c.payload,8);assert(f==1 && drm_native_count==1);
 struct waffle_unixnu_wait w={f,0};c.method=6;c.input_bytes=sizeof(w);c.output_bytes=0;memcpy(c.payload,&w,sizeof(w));assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner));w.fence=2;memcpy(c.payload,&w,sizeof(w));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL);
 s.count=128;s.wait_fence=f;for(unsigned i=0;i<128;i++)s.buffers[i]=(struct waffle_unixnu_ib){handle,map.iova,32};c.method=5;c.input_bytes=sizeof(s);c.output_bytes=8;memcpy(c.payload,&s,sizeof(s));assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner) && copies==9 && commands_seen==129 && !snapshot_live);memcpy(&f,c.payload,8);assert(f==9 && drm_native_count==2);
 s.count=1;s.wait_fence=0;fail_submit=1;memcpy(c.payload,&s,sizeof(s));assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EIO && drm_native_lost && !snapshot_live);assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EIO);
 assert(!drm_close(0,0,0,&owner) && !stored);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+ns['parts']['ioc']+ns['uapi']+ns['source']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual native submit/wait: all roots prevalidated, chosen IOVA range/size/queue/dependency refusal, fence history,128IB8windows, submit failure loses context, metadata released; GPU mocked')
