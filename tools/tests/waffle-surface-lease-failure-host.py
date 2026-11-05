#!/usr/bin/env python3
"""Actual cdev keeps native read leases when submission completion is uncertain."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(Path(__file__).resolve())}
s=(root/'tools/tests/waffle-surface-sample-submit-host.py').read_text()
exec(s[:s.index("\ntest=r'''")],ns)
h=ns['h'].replace('#define _DEFAULT_SOURCE\n','').replace('static void loader_return(void){longjmp(reset_trap,1);}', 'static void loader_return(void){assert(expect_return);longjmp(return_point,1);}')
h='#define _DEFAULT_SOURCE\n#include <setjmp.h>\nstatic jmp_buf return_point;static int expect_return;static void *retained[2];static unsigned retained_count;\n'+h
h=h.replace('snapshot_live++;return p;', 'snapshot_live++;assert(retained_count<2);retained[retained_count++]=p;return p;')
h=h.replace('assert(held && c==&context && job->count==1 && job->commands[0].bytes==1240);job->fence=', 'assert(held && c==&context && job->count==1 && job->commands[0].bytes==1240);if(expect_return)return false;job->fence=')
test=r'''
int main(void){
 struct proc owner={.pid=1};assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_surface r={.surface=79};assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,(char *)&r,0,&owner));
 struct waffle_msm_gem_new command={.size=4096,.flags=WAFFLE_GPU_BO_WC};assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&command,0,&owner));
 struct waffle_msm_submit_bo bos[2]={{.handle=r.handle,.flags=3},{.handle=command.handle,.flags=1}};
 struct waffle_msm_submit_cmd cmd={.type=1,.submit_idx=1,.size=1240};
 struct waffle_msm_submit sub={.flags=0x10,.nr_bos=2,.nr_cmds=1,.bos=(uintptr_t)bos,.cmds=(uintptr_t)&cmd};
 expect_return=1;
 if(!setjmp(return_point)){drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner);assert(0);}
 assert(read_held && read_begins==1 && !read_ends && source_cleans==1 && snapshot_live==2 && holds==1 && !copies && held);
 /* Model device reset only after observing retention, to release host allocations. */
 for(unsigned i=0;i<retained_count;i++)free(retained[i]);snapshot_live=retained_count=0;
 held=false;read_held=false;expect_return=0;assert(!drm_close(0,0,0,&owner));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+ns['ns']['ns']['parts']['ioc']+ns['ns']['ns']['uapi']+ns['helper']+ns['ns']['ns']['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual cdev uncertain completion: loader return with read lease/backing retained, no premature end/free; reset modeled, no hardware claim.')
