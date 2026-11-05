#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy,tempfile,copy
root=Path(__file__).resolve().parents[2];check=runpy.run_path(str(root/'tools/run-waffle-auto.py'))['check_surface_lock_policy']
with tempfile.TemporaryDirectory() as t:
 r=Path(t)/'repo';a=Path(t)/'artifact';m={'surface_lock_policy_sha256':{}};names=['loader/waffle.h','kernel/files/iokit/Kernel/MiniIOSurface.cpp']
 for n in names:
  for b in [r,a/'source']:
   p=b/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('waffle_surface_lock_audit=1 '+n)
  m['surface_lock_policy_sha256'][n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
 check(r,a,m);count=0
 def reject(x):
  global count
  try:check(r,a,x)
  except (ValueError,OSError):count+=1
  else:raise AssertionError('Stale/missing audit policy admitted')
 for n in names:
  x=copy.deepcopy(m);del x['surface_lock_policy_sha256'][n];reject(x)
  for b in [r,a/'source']:
   p=b/n;old=p.read_bytes();p.write_bytes(b'changed');reject(m);p.write_bytes(old)
 n=names[0]
 for b in [r,a/'source']:(b/n).write_text('old loader without token')
 m['surface_lock_policy_sha256'][n]=hashlib.sha256((r/n).read_bytes()).hexdigest();reject(m)
print(f'PASS diagnostic loader/kernel binding: {count} missing/stale/default-loader refusals before USB; synthetic files only')
