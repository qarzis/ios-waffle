#!/usr/bin/env python3
"""Actual private cdev map/revoke audit; lower layers independently tested."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h']
for name in ['waffle_gpu_surface_describe','waffle_gpu_memory_surface','waffle_gpu_context_memory_adopt','waffle_gpu_memory_destroy','waffle_gpu_context_memory_reclaim']:
 h=re.sub(r'^.*\b'+name+r'\([^\n]*\)\{[^\n]*\}\n','',h,flags=re.M)
h=h.replace('static void loader_return(void){assert(0);}','static void loader_return(void){longjmp(reset_trap,1);}')
helper=r'''
static unsigned audit_mode,holds,releases,adopts,revokes;static struct waffle_gpu_memory imported;
int waffle_gpu_surface_describe(struct waffle_msm_surface *r){assert(held && r->handle==UINT32_MAX);if(r->surface!=79)return ENOENT;*r=(struct waffle_msm_surface){.surface=79,.size=32768,.row_bytes=3072,.width=750,.height=8,.pixel_format=0x42475241};return 0;}
bool waffle_gpu_memory_surface(uint32_t sid,struct waffle_gpu_memory *b){assert(held && sid==79 && !b->object);if(audit_mode==1)return false;holds++;*b=(struct waffle_gpu_memory){.object=79,.memory=0x2000000,.bytes=32768,.allocation_bytes=32768,.flags=WAFFLE_GPU_BO_CACHED,.storage=WAFFLE_GPU_STORAGE_SURFACE};return true;}
struct waffle_gpu_memory *waffle_gpu_context_memory_adopt(struct waffle_gpu_context *c,struct waffle_gpu_memory *b){assert(held && c==&context && b->object==79 && holds==1);adopts++;if(audit_mode==2)return NULL;imported=*b;memset(b,0,sizeof(*b));imported.published=true;imported.gpu_va=0x100000000ULL;return &imported;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *b,bool detached){assert(held && holds==1 && (!b->published || detached));holds--;releases++;memset(b,0,sizeof(*b));return true;}
bool waffle_gpu_context_memory_reclaim(struct waffle_gpu_context *c,struct waffle_gpu_memory *b,bool unmap){assert(held && c==&context && b==&imported && unmap && b->published);revokes++;if(audit_mode==3)return false;b->published=false;return waffle_gpu_memory_destroy(b,false);}
'''
test=r'''
int main(void){
 struct proc owner={.pid=1},other={.pid=9};assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 struct waffle_msm_surface r={.surface=79};assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&other)==EPERM && !holds && !adopts);
 drm_pid=9;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&other)==EPERM && !adopts);drm_pid=1;
 r.handle=1;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner)==EINVAL && !adopts);r.handle=0;
 r.surface=99;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner)==ENOENT && !holds);r.surface=79;
 audit_mode=1;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner)==ENOTSUP && !holds && !releases);
 audit_mode=2;assert(drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner)==EIO && !holds && releases==1 && !revokes);
 audit_mode=0;assert(!drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner) && !holds && releases==2 && revokes==1 && !r.handle && r.size==32768);
 assert(!drm_count && !drm_issued && !drm_fence && !mapped && !copies); /* No GEM handles, submissions or CPU maps. */
 r=(struct waffle_msm_surface){.surface=79};audit_mode=3;
 if(!setjmp(reset_trap)){drm_ioctl(0,WAFFLE_MSM_SURFACE_MAP_TEST,(char *)&r,0,&owner);assert(0);}
 assert(held && holds==1 && releases==2 && imported.object && imported.published); /* Failed revoke retains backing until reset. */
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(h+ns['parts']['ioc']+ns['uapi']+helper+ns['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual private map audit:PID1/owner/reserved admission, describe/hold/adopt/revoke order, pre-adopt cleanup, no GEM/CPU-map/submission, failed revoke traps with published backing retained; SMMU and memory implementations tested separately')
