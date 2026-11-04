#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-import-log-host.py')}
exec((root/'tools/tests/waffle-surface-import-log-host.py').read_text(),ns)
m=ns['m'];text=ns['text'];pixels=ns['pixels'];marker=ns['marker']
# ns marker is overwritten by the imported test's failure loop.
marker='GENERAL_BO released after GPU stop and context detach count=1'
audit=ns['audit'].split('SURFACE_BO published index=3')[0]+'''waffle-gl-surface-resource: passed=1 sid=1 textures=2 width=750 height=1624 deleted=2 GPU_memory_access=0
waffle-gl-surface: sid=1 bytes=4898816 stride=3008 width=750 height=1624 format=42475241 metadata_expected=1
waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1
'''
combined=text.replace(marker,audit+marker+' reclaimed_earlier=1 total=2').replace('completed=1 buffers=1','completed=1 buffers=2')
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[combined.replace(line,'') for line in audit.splitlines(True)]
for before,after in [('textures=2','textures=1'),('deleted=2','deleted=0'),('width=750 height=1624 deleted','width=749 height=1624 deleted'),('handle=2 index=2','handle=3 index=2'),('GPU_memory_access=0','GPU_memory_access=1')]:bad.append(combined.replace(before,after))
for marker in ['waffle-gl-surface-resource: passed=0','SURFACE_IMPORT cleanup_refused=1','SURFACE_WRITE_TEST passed=1','waffle-gl-surface-import: passed=1']:bad.append(combined+'\n'+marker)
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete Mesa resource evidence accepted')
print(f'PASS Mesa resource import/native GEM lifetime and replay; {len(bad)} missing/corrupt proof refusals; synthetic only')
