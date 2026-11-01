"""Exercise actual cdev handles above64 and unchanged registry heap budget."""
from pathlib import Path
import subprocess,tempfile,json
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
source=(root/'tools/tests/waffle-general-drm-host.py').read_text()
exec(source[:source.index('\nwith tempfile.TemporaryDirectory()')],ns)
t=ns['t']
at=t.index(' for(unsigned i=1;i<=13;i++)')
t=t[:at]+r'''
 /* Existing13 actual GL buffers stay live. Exercise the complete bounded
  * object space within the configured heap or recycling handles. */
 for(unsigned i=14;i<=WAFFLE_GPU_BO_LIMIT;i++){
  struct waffle_msm_gem_new r={.size=16384,.flags=WAFFLE_GPU_BO_WC};
  assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner) && r.handle==i);
 }
 assert(stored==WAFFLE_GPU_BO_LIMIT);
 struct waffle_msm_gem_new extra={.size=4096,.flags=WAFFLE_GPU_BO_WC};
 assert(drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&extra,0,&owner)==ENOSPC && stored==WAFFLE_GPU_BO_LIMIT);
 struct waffle_msm_submit_bo all[WAFFLE_GPU_SUBMIT_BUFFERS+1];
 for(unsigned i=0;i<=WAFFLE_GPU_SUBMIT_BUFFERS;i++)all[i]=(struct waffle_msm_submit_bo){.handle=i+1,.flags=3};
 all[63].handle=WAFFLE_GPU_BO_LIMIT;
 memcpy((void *)storage[WAFFLE_GPU_BO_LIMIT-1].memory,actual_root,sizeof(actual_root));
 cmd.submit_idx=63;request.bos=(uintptr_t)all;request.nr_bos=64;request.fence=0;
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner) && request.fence==2);
 all[62].handle=WAFFLE_GPU_BO_LIMIT;request.fence=0;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && copies==2);
 all[62].handle=63;
 request.nr_bos=WAFFLE_GPU_SUBMIT_BUFFERS+1;
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner) && request.fence==3 && copies==3);
 all[0].handle=65;request.nr_bos=1;cmd.submit_idx=0;request.fence=0;
 memcpy((void *)storage[64].memory,actual_root,sizeof(actual_root));
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner) && request.fence==4);
 for(unsigned i=1;i<=WAFFLE_GPU_BO_LIMIT;i++){struct waffle_msm_close r={.handle=i};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&r,0,&owner));}
 assert(!mapped && stored==WAFFLE_GPU_BO_LIMIT);
 assert(!drm_close(0,0,0,&owner) && !stored && !drm_context);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+ns['source']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual budget-derived context:highest handle/handle65 submit,duplicatehighhandle refused,65 references admitted in bounded CPU snapshot,context-cap+1 refused,GEM_CLOSE forwards modeled reclamation; fake allocator host model only')

# Reuse the actual SMMU adapter harness, seeded with the observed25 boot tables.
model={'__file__':str(root/'tools/tests/waffle-table-budget-host.py')}
src=(root/'tools/tests/waffle-table-budget-host.py').read_text()
exec(src[:src.index('\nwith tempfile.TemporaryDirectory()')],model)
requests=json.loads((root/'work/waffle/gpu/forensic-audit/E46-result.json').read_text())['BO_prefix']
t='int main(void){struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};active=&owner;for(unsigned i=0;i<25;i++)assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;\n'
for r in requests:t+=f"assert(smmu_registry_new(&owner,{r['bytes']}u,{r['flags']}u));\n"
t+='assert(owner.registry.count==32 && owner.registry.used==23625728 && !owner.registry.poisoned && owner.pool.count<=64);assert(smmu_registry_new(&owner,16384,WAFFLE_GPU_BO_WC));assert(owner.registry.count==33 && owner.registry.used<WAFFLE_GPU_BO_HEAP_BYTES);assert(waffle_gpu_registry_destroy(&owner.registry,true));return 0;}'
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);parts=model['parts'];(p/'tables.c').write_text(model['h']+parts['mapping']+parts['types']+parts['dynamic']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'tables.c'),'-o',str(p/'tables')],check=True)
 subprocess.run([str(p/'tables')],check=True)
print('Actual SMMU replays32 observed UI BOs/23625728bytes after25 boot tables, admits extra16KiB BO33 within current heap/64table bounds; extra request is host model only')
