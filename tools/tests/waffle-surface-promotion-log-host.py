#!/usr/bin/env python3
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[2]
f=runpy.run_path(str(root/'scripts/run_waffle_ios.py'))['validate_surface_promotion_log']
s='''SURFACE_SAMPLE imported=1 sid=1 handle=28 index=29 GPU_readonly=1
waffle-gl-surface-promotion: begin texture=3 sibling=2 sid=1 native_readonly=1
waffle-readonly-promote: passed=1 texture=3 sid=1 owned_upload=1 native_GPU_writes=0
GENERAL submitted fence=2
waffle-gl-surface-promotion: native_checked=1218000 wrong=0 before_sibling=1
SURFACE_SAMPLE sync=1 handle=28
GENERAL submitted fence=3
waffle-gl-surface-promotion: sibling_checked=256 wrong=0 native_cache_sync=1
waffle-gl-surface-promotion: passed=1 texture=3 owned_wrong=0 native_wrong=0 sibling_wrong=0 restored=1 pixels=1218000
'''
f(s)
for bad in [s.replace(line+'\n','') for line in s.splitlines() if line!='GENERAL submitted fence=2']+[s.replace('sibling=2','sibling=3'),s.replace('native_wrong=0','native_wrong=1'),s.replace('restored=1','restored=0'),s.replace('native_GPU_writes=0','native_GPU_writes=1')]:
 try:f(bad)
 except RuntimeError:pass
 else:raise AssertionError('incomplete promotion evidence admitted')
print('PASS promotion proof: actual RO import, owned replacement, full native pixels, ordered cache-clean/GPU sibling and restoration required; synthetic only')
