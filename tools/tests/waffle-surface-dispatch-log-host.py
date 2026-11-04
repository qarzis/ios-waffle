#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-eagl-log-host.py')}
exec((root/'tools/tests/waffle-surface-eagl-log-host.py').read_text(),ns)
m=ns['m'];pixels=ns['pixels'];combined=ns['combined']
marker='waffle-gl-eagl-native-draw: dispatched=1 shader_draw_readback=1\n'
combined=combined.replace('waffle-gl-surface-sample: passed=1',marker+'waffle-gl-surface-sample: passed=1')
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
for bad in [combined.replace('dispatched=1','dispatched=0'),combined.replace('shader_draw_readback=1','shader_draw_readback=0'),combined+'\nwaffle-gl-eagl-native-draw: dispatched=0\n']:
 try:m.validate_gl_log(bad)
 except RuntimeError:pass
 else:raise AssertionError('Raw fallback accepted as EAGL draw dispatch')
print('PASS EAGL shader/draw/readback dispatch proof plus native input/update/complete GPU pixels;3 corrupt proof refusals; synthetic only')
