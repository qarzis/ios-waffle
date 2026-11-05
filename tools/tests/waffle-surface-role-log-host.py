#!/usr/bin/env python3
from pathlib import Path
import runpy
r=Path(__file__).resolve().parents[2];check=runpy.run_path(str(r/'scripts/run_waffle_ios.py'))['validate_surface_role_log']
text='''SURFACE_SAMPLE imported=1 sid=1 handle=27 index=28 GPU_readonly=1
waffle-gl-surface-role: begin sid=1 handle=27 readonly_native=1
waffle-gl-surface-role: passed=1 sid=1 handle=27 framebuffer_status=8cd5 GL_error=0 readonly_native=1 attachment_allowed=1 draw_calls=0 restored_binding=1
'''
check(text);check(text+text)
for bad in [text.replace('passed=1','passed=0'),text.replace('GPU_readonly=1','GPU_readonly=0'),text.replace('framebuffer_status=8cd5','framebuffer_status=8cd6'),text.replace('GL_error=0','GL_error=502'),text.replace('draw_calls=0','draw_calls=1'),text.replace('waffle-gl-surface-role: passed','GENERAL_SUBMIT begin fence=3\nwaffle-gl-surface-role: passed')]:
 try:check(bad)
 except RuntimeError:pass
 else:raise AssertionError('Invalid native role query accepted')
print('PASS readonly role proof: native RO handle, FBO complete without any GPU submission; six corrupt proofs refused, synthetic only.')
