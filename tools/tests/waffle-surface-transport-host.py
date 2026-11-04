#!/usr/bin/env python3
"""Actual Waffle cdev describe admission plus actual Mesa opt-in caller."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h'].replace('#define _DEFAULT_SOURCE\n','');h=re.sub(r'int waffle_gpu_surface_describe\(struct waffle_msm_surface \*r\)\{[^\n]+\}\n','',h)
helper=r'''
static unsigned describes;
int waffle_gpu_surface_describe(struct waffle_msm_surface *r){
 assert(held && r->handle==UINT32_MAX);describes++;
 if(r->surface!=79)return ENOENT;
 *r=(struct waffle_msm_surface){.surface=79,.size=4997120,.width=750,.height=1624,.row_bytes=3072,.pixel_format=0x42475241};return 0;
}
'''
test=r'''
int main(void){
 struct proc owner={.pid=9},other={.pid=10};
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct {uint64_t a;struct waffle_msm_surface r;uint64_t b;} wrapped={.a=0xaabbccdd,.b=0x11223344,.r={.surface=79,.handle=UINT32_MAX}};
 assert(drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&wrapped.r,0,&other)==EPERM && !describes);
 assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&wrapped.r,0,&owner) && describes==1);
 assert(!wrapped.r.handle && wrapped.r.width==750 && wrapped.r.row_bytes==3072 && wrapped.a==0xaabbccdd && wrapped.b==0x11223344);
 assert(!stored && !mapped && !drm_count && !drm_issued && !drm_fence);
 wrapped.r.handle=0;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&wrapped.r,0,&owner)==ENOTSUP && describes==1);
 wrapped.r.handle=42;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&wrapped.r,0,&owner)==ENOTSUP && describes==1);
 wrapped.r.handle=UINT32_MAX;wrapped.r.surface=999;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&wrapped.r,0,&owner)==ENOENT && describes==2);
 assert(!drm_close(0,0,0,&owner));
}
'''
def function(s,sig):
 a=s.index(sig);at=s.index('{',a);b=at+1;depth=1
 while depth:depth+=(s[b]=='{')-(s[b]=='}');b+=1
 return s[a:b]
shim=(root/'tools/mesa/drm-shim/drm_shim.c').read_text()
mesa=(root/'tools/mesa/drm-shim/xf86drm.h').read_text()
struct=re.search(r'struct redwood_drm_surface \{.*?\n\};',mesa,re.S)[0]
caller=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
'''+struct+r'''
#define REDWOOD_GPU_SURFACE 0x7e
#define REDWOOD_GPU_DESCRIBE UINT32_MAX
static int waffle_general=1,calls;static int call(unsigned n,void *data,size_t bytes){
 assert(n==0x7e && bytes==40);calls++;struct redwood_drm_surface *r=data;
 if(r->handle!=UINT32_MAX)return ENOTSUP;
 r->handle=0;r->width=750;r->height=1624;r->row_bytes=3072;return 0;
}
'''+function(shim,'int\nredwood_drm_surface(')+'\n'+function(shim,'int\ndrmPrimeFDToHandle(')+r'''
int main(void){
 struct redwood_drm_surface r={.surface=79};
 unsetenv("WAFFLE_GPU_SURFACE_AUDIT");assert(redwood_drm_surface(3,&r)==-1 && errno==ENOTSUP && !calls);
 setenv("WAFFLE_GPU_SURFACE_AUDIT","0",1);assert(redwood_drm_surface(3,&r)==-1 && !calls);
 setenv("WAFFLE_GPU_SURFACE_AUDIT","1",1);assert(!redwood_drm_surface(3,&r) && r.width==750 && !r.handle && calls==1);
 uint32_t handle=0x12345678;assert(drmPrimeFDToHandle(3,79,&handle)==-1 && errno==ENOTSUP && handle==0x12345678);
 waffle_general=0;unsetenv("WAFFLE_GPU_SURFACE_AUDIT");assert(!redwood_drm_surface(3,&r));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t)
 for name,code in [('cdev',h+ns['parts']['ioc']+ns['uapi']+helper+ns['source']+test),('caller',caller)]:
  (p/(name+'.c')).write_text(code)
  subprocess.run(['cc','-D_DEFAULT_SOURCE','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/(name+'.c')),'-o',str(p/name)],check=True)
  subprocess.run([str(p/name)],check=True)
print('PASS actual cdev/Mesa metadata route: owner PID, describe-only sentinel, canaries, no GEM/maps/fences; opt-in environment, donor preservation and import refusal. C++ lookup tested separately, transport/owner mocked')
