#!/usr/bin/env python3
"""Exercise actual pre-USB source admission with mutable local artifacts."""
from pathlib import Path
import copy
import hashlib
import runpy
import tempfile
root=Path(__file__).resolve().parents[2]
check=runpy.run_path(str(root/'tools/run-waffle-auto.py'))['check_surface_metadata_binding']
with tempfile.TemporaryDirectory() as t:
    r=Path(t)/'repo';a=Path(t)/'artifact'
    names=['kernel/files/bsd/sys/waffle_gpu_msm.h','kernel/files/bsd/dev/waffle_gpu_drm.c','kernel/files/iokit/Kernel/MiniIOSurface.cpp','tools/mesa/drm-shim/drm_shim.c']
    bindings={}
    for n in names:
        for base in [r,a/'source']:
            p=base/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(n)
        bindings[n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
    m={'surface_metadata_describe':True,'surface_description_source_sha256':bindings}
    g={'surface_describe':True,'fullsize_probe':True,'source_sha256':{'tools/mesa/drm-shim/drm_shim.c':bindings[names[-1]]}}
    check(r,a,m,g)
    count=0
    def reject(m,g,ui=False):
        global count
        try:check(r,a,m,g,ui)
        except (ValueError,OSError):count+=1
        else:raise AssertionError('unsafe artifact admitted')
    reject(m,g,True)
    x=copy.deepcopy(m);x['surface_metadata_describe']=False;reject(x,g)
    x=copy.deepcopy(g);x['fullsize_probe']=False;reject(m,x)
    for n in names[:3]:
        x=copy.deepcopy(m);del x['surface_description_source_sha256'][n];reject(x,g)
        p=r/n;old=p.read_bytes();p.write_bytes(b'changed');reject(m,g);p.write_bytes(old)
        p=a/'source'/n;old=p.read_bytes();p.write_bytes(b'compiled stale');reject(m,g);p.unlink();reject(m,g);p.write_bytes(old)
    p=r/names[-1];old=p.read_bytes();p.write_bytes(b'candidate changed');reject(m,g);p.write_bytes(old)
    x=copy.deepcopy(g);x['source_sha256'][names[-1]]='0'*64;reject(m,x)
    x=copy.deepcopy(g);x['surface_map_test']=True;reject(m,x)
    q=copy.deepcopy(m);q['surface_map_audit']=True;reject(q,x)
    check(r,a,m,g)
    w=copy.deepcopy(g);w['surface_map_test']=True;w['surface_write_test']=True
    v=copy.deepcopy(m);v['surface_map_audit']=True
    reject(v,w)
    v['surface_gpu_write_audit']=True
    extra=['kernel/files/bsd/sys/waffle_gpu_memory.h','kernel/files/bsd/sys/waffle_gpu_registry.h',
           'kernel/files/bsd/sys/waffle_gpu_surface.h','kernel/files/iokit/Kernel/WaffleGPUMemory.cpp',
           'kernel/files/bsd/dev/waffle_gpu_service.c','kernel/files/bsd/dev/waffle_adreno.c',
           'kernel/files/bsd/dev/waffle_smmu.c','kernel/files/bsd/sys/waffle_gpu_surface_write.h',
           'kernel/files/bsd/sys/waffle_gpu_writeback.h']
    for n in extra:
        for base in [r,a/'source']:
            p=base/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(n)
        v['surface_description_source_sha256'][n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
    check(r,a,v,w)
    for n in extra:
        x=copy.deepcopy(v);del x['surface_description_source_sha256'][n];reject(x,w)
    x=copy.deepcopy(w);x['surface_map_test']=False;reject(v,x)
    read=copy.deepcopy(w);read['surface_write_test']=False;read['surface_read_test']=True
    reject(v,read)
    v['surface_gpu_read_audit']=True
    n='kernel/files/bsd/sys/waffle_gpu_surface_read.h'
    for base in [r,a/'source']:
        p=base/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(n)
    v['surface_description_source_sha256'][n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
    check(r,a,v,read)
    x=copy.deepcopy(read);x['surface_describe']=False;reject(v,x)
    x=copy.deepcopy(read);x['surface_write_test']=True;reject(v,x)
    x=copy.deepcopy(v);del x['surface_description_source_sha256'][n];reject(x,read)
    imp=copy.deepcopy(g);imp['surface_map_test']=True;imp['surface_import_test']=True
    reject(v,imp)
    v['surface_import_lifetime_audit']=True
    reject(v,imp)
    n='kernel/files/bsd/sys/waffle_gpu_handles.h'
    for base in [r,a/'source']:
        p=base/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(n)
    v['surface_description_source_sha256'][n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
    check(r,a,v,imp)
    x=copy.deepcopy(imp);x['surface_read_test']=True;reject(v,x)
    x=copy.deepcopy(imp);x['surface_describe']=False;reject(v,x)
    res=copy.deepcopy(g);res['surface_map_test']=True;res['surface_resource_test']=True
    reject(v,res)
    v['surface_resource_audit']=True
    check(r,a,v,res)
    x=copy.deepcopy(res);x['surface_import_test']=True;reject(v,x)
    x=copy.deepcopy(res);x['surface_describe']=False;reject(v,x)
    sample=copy.deepcopy(res);sample['surface_sample_test']=True
    reject(v,sample)
    v['surface_sample_audit']=True
    reject(v,sample)
    for n in ['userland/src/waffle_surface_sample.c','userland/src/waffle_surface_sample.h']:
        p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(n)
        sample['source_sha256'][n]=hashlib.sha256(p.read_bytes()).hexdigest()
    check(r,a,v,sample)
    check(r,a,{}, {}) # Existing unrelated probe has no metadata opt-in.
print(f'PASS actual surface admission:{count} metadata/UI/missing/current/compiled/Mesa-source mismatch refusals before USB; bound and unrelated artifacts preserved')
