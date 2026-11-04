#!/usr/bin/env python3
"""Actual private native import lifetime API, without GPU memory access."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-map-audit-host.py')}
s=(root/'tools/tests/waffle-surface-map-audit-host.py').read_text();exec(s[:s.index("test=r'''")],ns)
helper=ns['helper'].replace('imported.gpu_va=0x100000000ULL;','imported.gpu_va=0x100000000ULL;imported.serial=adopts;')
test=r'''
int main(void){
 struct proc owner={.pid=1},other={.pid=9};assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_surface r={.surface=79};assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&other)==EPERM && !holds);
 drm_pid=9;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&other)==EPERM);drm_pid=1;
 r.handle=1;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner)==EINVAL && !adopts);r.handle=0;
 audit_mode=1;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner)==ENOTSUP && !holds);
 audit_mode=2;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner)==EIO && !holds && releases==1);
 audit_mode=0;drm_issued=UINT32_MAX;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner)==ENOSPC && !holds);drm_issued=0;
 assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner));uint32_t first=r.handle;
 assert(first==1 && drm_issued==1 && drm_count==1 && holds==1 && adopts==2 && !revokes);
 r=(struct waffle_msm_surface){.surface=79};assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner) && r.handle==first);
 assert(drm_issued==1 && holds==1 && adopts==2);
 struct waffle_msm_gem_info info={.handle=first,.info=1};assert(!drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&info,0,&owner) && info.value==0x100000000ULL);
 struct waffle_msm_map map={.handle=first,.bytes=32768};assert(drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&map,0,&owner)==ENOTSUP && !mapped);
 struct waffle_msm_cpu_prep prep={.handle=first};assert(drm_ioctl(0,WAFFLE_MSM_CPU_PREP,(char *)&prep,0,&owner)==ENOTSUP);
 struct waffle_msm_cpu_fini fini={.handle=first};assert(drm_ioctl(0,WAFFLE_MSM_CPU_FINI,(char *)&fini,0,&owner)==ENOTSUP);
 struct waffle_msm_submit_bo sb={.handle=first,.flags=1};struct waffle_msm_submit_cmd cmd={0};
 struct waffle_msm_submit sub={.flags=0x10,.nr_bos=1,.nr_cmds=1,.bos=(uintptr_t)&sb,.cmds=(uintptr_t)&cmd};
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&sub,0,&owner)==ENOTSUP && !copies && !snapshot_live);
 struct waffle_msm_close close={.handle=first};audit_mode=3;assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EIO && holds==1 && drm_buffer(first));
 audit_mode=0;assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner) && !holds && !drm_buffer(first));
 assert(drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&info,0,&owner)==EINVAL);
 assert(drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner)==EINVAL);
 r=(struct waffle_msm_surface){.surface=79};assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_IMPORT_TEST,(char *)&r,0,&owner));
 assert(r.handle==first+WAFFLE_GPU_BO_LIMIT && holds==1 && drm_issued==2);
 assert(drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&info,0,&owner)==EINVAL);
 close.handle=r.handle;assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&close,0,&owner) && !holds);
 r=(struct waffle_msm_surface){.surface=79};assert(drm_ioctl(0,WAFFLE_MSM_SURFACE,(char *)&r,0,&owner)==ENOTSUP);
 assert(!drm_fence && !copies && !mapped);assert(!drm_close(0,0,0,&owner));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(ns['h']+ns['ns']['parts']['ioc']+ns['ns']['uapi']+helper+ns['ns']['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual private import cdev: PID1/reserved/ownership, hold/adopt failures, descriptor exhaustion, duplicate handle reuse without hold, GPU VA, close/revoke failure retention, stale handle rejection and generation reimport; submit/CPU-map/PREP/FINI refused; normal import disabled; host only')
