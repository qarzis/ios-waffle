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
    check(r,a,m,g)
    check(r,a,{}, {}) # Existing unrelated probe has no metadata opt-in.
print(f'PASS actual surface admission:{count} metadata/UI/missing/current/compiled/Mesa-source mismatch refusals before USB; bound and unrelated artifacts preserved')
