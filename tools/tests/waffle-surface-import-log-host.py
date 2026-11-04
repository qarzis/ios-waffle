#!/usr/bin/env python3
"""Imported GEMs must have native lifetime plus ordinary generation accounting."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-gl-log-host.py')}
s=(root/'tools/tests/waffle-gl-log-host.py').read_text();exec(s[:s.index('assert m.validate_gl_log(text)==pixels')],ns)
m=ns['m'];text=ns['text'];pixels=ns['pixels']
text=text.replace('heap_bytes=33554432','heap_bytes=33554432 generation_handles=1').replace('waffle-gl-user: renderer=FD750','GENERAL gem_new handle=1 bytes=4096 allocated=16384 flags=20000 VA=100000000\nwaffle-gl-user: renderer=FD750')
audit=''
for index,handle in [(2,2),(3,34)]:
 audit+=f'''SURFACE_BO published index={index} VA=100004000 bytes=4898816 cached=1 pages=1196
GENERAL gem_new handle={handle} bytes=4898816 allocated=4898816 flags=80000 VA=100004000
SURFACE_IMPORT created=1 sid=1 handle={handle} index={index} VA=100004000 bytes=4898816 lifetime_only=1
'''
 if index==2:audit+='SURFACE_IMPORT reused=1 sid=1 handle=2\n'
 audit+=f'''GENERAL_BO reclaimed index={index} VA=100004000 bytes=4898816 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=16384
GENERAL bo_retired handle={handle} bytes=4898816 backing_retained=0
'''
audit+='''waffle-gl-surface-import: passed=1 sid=1 first=2 second=34 duplicate_same=1 stale_refused=1 CPU_map_refused=1 closed=2 GPU_memory_access=0
waffle-gl-surface: sid=1 bytes=4898816 stride=3008 width=750 height=1624 format=42475241 metadata_expected=1
waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1
'''
marker='GENERAL_BO released after GPU stop and context detach count=1'
combined=text.replace(marker,audit+marker+' reclaimed_earlier=2 total=3').replace('completed=1 buffers=1','completed=1 buffers=3')
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[combined.replace(line,'') for line in audit.splitlines(True)]
for before,after in [('second=34','second=2'),('stale_refused=1','stale_refused=0'),('handle=34 bytes=4898816 allocated','handle=2 bytes=4898816 allocated'),('generation_handles=1','generation_handles=0'),('flags=20000','flags=80000'),('used=16384','used=0'),('CPU_map_refused=1','CPU_map_refused=0')]:bad.append(combined.replace(before,after))
for marker in ['waffle-gl-surface-import: passed=0','SURFACE_IMPORT cleanup_refused=1','SURFACE_WRITE_TEST passed=1']:bad.append(combined+'\n'+marker)
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete native import evidence accepted')
print(f'PASS imported GEM/native backing/generation accounting, replay, {len(bad)} missing/corrupt proof refusals; synthetic only')
