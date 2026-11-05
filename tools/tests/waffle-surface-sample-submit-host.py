#!/usr/bin/env python3
"""Private read-only import must clean source only after full submit admission."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-map-audit-host.py')}
s=(root/'tools/tests/waffle-surface-map-audit-host.py').read_text();exec(s[:s.index("test=r'''")],ns)
h=re.sub(r'^.*\bwaffle_gpu_memory_surface_sync\([^\n]*\)\{[^\n]*\}\n','',ns['h'],flags=re.M)
helper=ns['helper']+r'''
static unsigned source_cleans;static bool clean_failed;
bool waffle_gpu_memory_surface_sync(const struct waffle_gpu_memory *b,uint32_t off,uint32_t bytes,unsigned direction){
 assert(held && read_held && b==&imported && b->flags==(WAFFLE_GPU_BO_CACHED|WAFFLE_GPU_BO_READONLY));
 assert(off==0 && bytes==32768 && direction==WAFFLE_GPU_SURFACE_TO_GPU);source_cleans++;return !clean_failed;
}
'''
test=r'''
int main(void){
 struct proc owner={.pid=1},other={.pid=9};assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_surface r={.surface=79};assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,(char *)&r,0,&other)==EPERM);
 assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,(char *)&r,0,&owner));uint32_t source=r.handle;
 assert(imported.flags==(WAFFLE_GPU_BO_CACHED|WAFFLE_GPU_BO_READONLY));
 r=(struct waffle_msm_surface){.surface=79};assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner)==EINVAL);
 assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,(char *)&r,0,&owner) && r.handle==source && holds==1);
 struct waffle_msm_gem_new root={.size=4096,.flags=WAFFLE_GPU_BO_WC};assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&root,0,&owner));
 struct waffle_msm_submit_bo bos[2]={{.handle=source,.flags=2},{.handle=root.handle,.flags=1}};
 struct waffle_msm_submit_cmd cmd={.type=1,.submit_idx=1,.size=1240};
 struct waffle_msm_submit sub={.flags=0x10,.nr_bos=2,.nr_cmds=1,.bos=(uintptr_t)bos,.cmds=(uintptr_t)&cmd};
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==ENOTSUP && !source_cleans && !copies && !snapshot_live);
 bos[0].flags=1;imported.flags=WAFFLE_GPU_BO_CACHED;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==ENOTSUP && !source_cleans && !copies);
 imported.flags|=WAFFLE_GPU_BO_READONLY;cmd.submit_idx=0;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==EINVAL && !source_cleans && !copies);
 cmd.submit_idx=1;read_busy=true;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==EBUSY && !source_cleans && !copies && !snapshot_live && !read_held);
 read_busy=false;clean_failed=true;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==EIO && source_cleans==1 && !copies && !snapshot_live);
 clean_failed=false;bos[0].flags=3;assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner) && source_cleans==2 && copies==1 && sub.fence==1 && drm_fence==1);
 assert(read_begins==3 && read_ends==2 && !read_held && !snapshot_live);
 struct waffle_msm_surface_lease lease={.handle=source,.operation=1};
 assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&other)==EPERM);
 read_busy=true;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&owner)==EBUSY);read_busy=false;
 assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&owner) && lease.active==1);
 struct waffle_msm_close busy_close={.handle=source};assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&busy_close,0,&owner)==EBUSY && holds==1);
 sub.fence=0;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==EBUSY && copies==1 && !snapshot_live);
 lease=(struct waffle_msm_surface_lease){.handle=source,.operation=3};assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&owner) && lease.active==1 && !lease.waiting_writers);
 lease=(struct waffle_msm_surface_lease){.handle=source,.operation=2};assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&owner) && !lease.active && !read_held);
 assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_LEASE_TEST,(char *)&lease,0,&owner)==EINVAL);
 struct waffle_msm_map map={.handle=source,.bytes=32768};assert(drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&map,0,&owner)==ENOTSUP && !mapped);
 struct waffle_msm_close close={.handle=source};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner) && !holds);
 assert(!drm_close(0,0,0,&owner));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(h+ns['ns']['parts']['ioc']+ns['ns']['uapi']+helper+ns['ns']['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual cdev read-only sampler admission: exact readonly flags, duplicate/mixed import, write-only/root refusal before cache or GPU; conservative READ|WRITE allowed only with actual readonly flags, full-source clean and failure refusal, completed fence, no CPU alias, revoke; GPU modeled')
