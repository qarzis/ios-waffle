#!/usr/bin/env python3
"""Actual SMMU map/adopt/reclaim adapters with retained cached-surface metadata."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-registry-smmu-host.py')}
s=(root/'tools/tests/waffle-registry-smmu-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h'].replace('static unsigned objects,reclaimed;','static unsigned objects;');h=re.sub(r'^bool waffle_gpu_memory_destroy.*$','',h,flags=re.M)
test=r'''
static unsigned released;
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){
 assert(bo->object==79 && bo->storage==WAFFLE_GPU_STORAGE_SURFACE && !storage_frees);
 if(!detached){assert(!bo->published && tlbs>=4);for(unsigned off=0;off<bo->allocation_bytes;off+=4096)assert(!pte(&active->pool,bo->gpu_va+off));}
 released++;memset(bo,0,sizeof(*bo));return true;
}
int main(void){
 struct smmu_owner owner={.compute_image=13,.child=&child,.permission_context={.cb=1,.lpac_cb=2}};
 active=&owner;assert(new_table(&owner.pool));owner.permission_context.tables=&owner.pool;live=true;
 struct waffle_gpu_memory prepared={.object=79,.memory=0x40000000,.bytes=32768,.allocation_bytes=32768,.flags=WAFFLE_GPU_BO_CACHED,.storage=WAFFLE_GPU_STORAGE_SURFACE};
 struct waffle_gpu_memory *bo=smmu_registry_adopt(&owner,&prepared);
 assert(bo && !prepared.object && bo->published && bo->storage==WAFFLE_GPU_STORAGE_SURFACE && !objects && !released && tlbs==2);
 for(unsigned off=0;off<32768;off+=4096){uint64_t e=pte(&owner.pool,bo->gpu_va+off);assert((e&PTE_ADDRESS)==waffle_gpu_memory_page(bo,off) && (e&0xc3)==0x43);}
 uint64_t address=bo->gpu_va;
 assert(smmu_registry_reclaim(&owner,bo,true) && tlbs==4 && released==1 && !owner.registry.used && !owner.registry.poisoned);
 for(unsigned off=0;off<32768;off+=4096)assert(!pte(&owner.pool,address+off));
 assert(waffle_gpu_registry_destroy(&owner.registry,true) && released==1 && storage_frees==1);
}
'''
parts=ns['parts']
with tempfile.TemporaryDirectory() as t:
 p=Path(t)
 for readonly in (False,True):
  candidate=test.replace('.flags=WAFFLE_GPU_BO_CACHED,','.flags=WAFFLE_GPU_BO_CACHED|WAFFLE_GPU_BO_READONLY,').replace('(e&0xc3)==0x43','(e&0xc3)==0xc3') if readonly else test
  (p/'test.c').write_text(h+parts['mapping']+parts['types']+parts['dynamic']+candidate)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('PASS actual retained-surface SMMU adapter: noncontiguous physical pages/AP, unchanged ordinary allocator, GPU+LPAC publication and revocation TLB syncs, all PTEs cleared before native-surface release; hardware I/O modeled')
