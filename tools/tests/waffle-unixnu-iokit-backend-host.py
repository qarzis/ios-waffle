"""Actual cdev-backed IOKit connection identity and CPU lease ownership."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2];ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
t=r'''
int main(void){
 void *cookie=(void*)0x1234,*other=(void*)0x5678;
 host_current=&foreign;assert(waffle_gpu_iokit_open(cookie)==EPERM && !drm_context);
 host_current=&owner;assert(!waffle_gpu_iokit_open(cookie));assert(drm_open(0,0,0,&owner)==EBUSY);
 struct waffle_unixnu_call c={.version=2,.method=1,.output_bytes=24};
 assert(waffle_gpu_iokit_call(other,&c)==EPERM);assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EPERM);
 assert(!waffle_gpu_iokit_call(cookie,&c));
 c.method=2;c.input_bytes=16;c.output_bytes=8;struct waffle_unixnu_alloc a={4096,12,0};memcpy(c.payload,&a,16);assert(!waffle_gpu_iokit_call(cookie,&c));uint64_t handle;memcpy(&handle,c.payload,8);
 c.method=13;c.input_bytes=8;c.output_bytes=16;assert(!waffle_gpu_iokit_call(cookie,&c));struct waffle_unixnu_cpu_reply reply;memcpy(&reply,c.payload,16);assert(reply.token==handle && reply.bytes==16384 && !reply.reserved);
 memcpy(c.payload,&handle,8);assert(!waffle_gpu_iokit_call(cookie,&c));assert(drm_buffer(handle)->native_views==2 && waffle_gpu_iokit_memory(cookie,reply.token)==drm_buffer(handle)->memory->object);
 assert(!waffle_gpu_iokit_memory(other,reply.token));host_current=&foreign;assert(!waffle_gpu_iokit_memory(cookie,reply.token) && waffle_gpu_iokit_call(cookie,&c)==EPERM);host_current=&owner;
 c.method=4;c.input_bytes=8;c.output_bytes=0;memcpy(c.payload,&handle,8);assert(waffle_gpu_iokit_call(cookie,&c)==EBUSY && !live_reclaims);
 c.method=14;c.input_bytes=16;struct waffle_unixnu_cpu_unmap u={handle,reply.token+1,0};memcpy(c.payload,&u,16);assert(waffle_gpu_iokit_call(cookie,&c)==EINVAL && drm_buffer(handle)->native_views==2);
 u.token=reply.token;memcpy(c.payload,&u,16);assert(!waffle_gpu_iokit_call(cookie,&c));assert(waffle_gpu_iokit_memory(cookie,reply.token));assert(!waffle_gpu_iokit_call(cookie,&c));assert(!waffle_gpu_iokit_memory(cookie,reply.token));assert(waffle_gpu_iokit_call(cookie,&c)==EINVAL);
 struct waffle_unixnu_map map={handle,0x10f000000ULL,3,0,2,0};c.method=3;c.input_bytes=sizeof(map);c.output_bytes=8;memcpy(c.payload,&map,sizeof(map));assert(!waffle_gpu_iokit_call(cookie,&c));
 for(unsigned n=0;n<300;n++){
  struct waffle_unixnu_submit submit={.count=1,.wait_fence=n,.buffers={{handle,map.iova,1240}}};c.method=5;c.input_bytes=sizeof(submit);c.output_bytes=8;memcpy(c.payload,&submit,sizeof(submit));assert(!waffle_gpu_iokit_call(cookie,&c));uint64_t fence;memcpy(&fence,c.payload,8);assert(fence==n+1);
 }
 assert(!drm_native_count && drm_fence==300);
 struct waffle_unixnu_wait wait={301,0};c.method=6;c.input_bytes=sizeof(wait);c.output_bytes=0;memcpy(c.payload,&wait,sizeof(wait));assert(waffle_gpu_iokit_call(cookie,&c)==EINVAL);wait.fence=1;memcpy(c.payload,&wait,sizeof(wait));assert(!waffle_gpu_iokit_call(cookie,&c));
 c.method=4;c.input_bytes=8;memcpy(c.payload,&handle,8);assert(!waffle_gpu_iokit_call(cookie,&c) && live_reclaims==1);
 c.output_bytes=0;
 assert(waffle_gpu_iokit_close(other)==EPERM && drm_context);host_current=&foreign;assert(!waffle_gpu_iokit_close(cookie) && !drm_context && !drm_iokit_owner);assert(waffle_gpu_iokit_close(cookie)==EPERM);
 host_current=&owner;assert(!drm_open(0,0,0,&owner));assert(!drm_close(0,0,0,&owner));return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+ns['source']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual IOKit backend: exclusive cookie/PID, cdev exclusion, two CPU leases, exact token, free blocked until last unmap, foreign call denial, cookie-only worker teardown and cdev reopening; GPU/IOKit objects mocked')
