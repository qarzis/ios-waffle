#!/usr/bin/env python3
"""Require actual native import, ordered replacement, submission and pixels."""
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[2]
check=runpy.run_path(str(root/'scripts/run_waffle_ios.py'))['validate_surface_detach_log']
text='''SURFACE_SAMPLE imported=1 sid=1 handle=28 index=4 GPU_readonly=1
waffle-gl-surface-detach: begin texture=2 sid=1 readonly_native=1
waffle-gl-surface-detach: replaced=1 texture=2 error=0 before_draw=1
GENERAL submitted fence=5
waffle-gl-surface-detach: passed=1 texture=2 checked=1218000 wrong=0 status=8cd5 error=0 owned_write=1 sibling_retained=1 flush_before_read=1
'''
check(text)
for bad in [text.replace(line+'\n','') for line in text.splitlines()]+[text.replace('wrong=0','wrong=1'),text.replace('checked=1218000','checked=1'),text.replace('replaced=1 texture=2','replaced=1 texture=3'),text.replace('GPU_readonly=1','GPU_readonly=0')]:
 try:check(bad)
 except RuntimeError:pass
 else:raise AssertionError('incomplete storage replacement evidence admitted')
print('PASS native replacement log: missing/mismatched import, replacement, GPU submission and pixels refused; synthetic only')
