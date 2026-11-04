#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-reuse-log-host.py')}
exec((root/'tools/tests/waffle-surface-reuse-log-host.py').read_text(),ns)
m=ns['m'];pixels=ns['pixels'];combined=ns['combined']
marker="waffle-gl-eagl-native-input: bound=2 sid=1 selector_present=1 input_only=1\n"
stat="redwood-gl: after 1 frames: 2 IOSurfaces were the textures' memory, 1 had to be copied\n"
combined=combined.replace('waffle-gl-surface-sample: passed=1',marker+'waffle-gl-surface-sample: passed=1')+stat
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[combined.replace(stat,''),combined.replace('bound=2','bound=1'),combined.replace('selector_present=1','selector_present=0'),combined.replace('input_only=1','input_only=0'),combined.replace("2 IOSurfaces were", "0 IOSurfaces were"),combined.replace('sid=1 selector','sid=2 selector')]
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Missing EAGL native input proof accepted')
print('PASS EAGL native input: selector plus hook-native counter and full shader/reuse proof required;6 corrupt evidence refusals; synthetic only')
