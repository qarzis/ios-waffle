#!/usr/bin/env python3
"""Strict lifetime parser accepts separate surface audit without relaxing GEM checks."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-gl-log-host.py')}
s=(root/'tools/tests/waffle-gl-log-host.py').read_text();exec(s[:s.index('assert m.validate_gl_log(text)==pixels')],ns)
m=ns['m'];text=ns['text'];pixels=ns['pixels']
audit='''SURFACE_BO published index=2 VA=100004000 bytes=4898816 cached=1 pages=1196
GENERAL_BO reclaimed index=2 VA=100004000 bytes=4898816 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=16384
SURFACE_MAP_TEST passed=1 sid=1 VA=100004000 bytes=4898816 header_excluded=1 cached=1 retired=1 GPU_memory_access=0
waffle-gl-surface-map: passed=1 native_registry=1 mapped_then_revoked=1 GPU_memory_access=0
waffle-gl-surface: sid=1 bytes=4898816 stride=3008 width=750 height=1624 format=42475241 metadata_expected=1
waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1
'''
marker='GENERAL_BO released after GPU stop and context detach count=1'
combined=text.replace(marker,audit+marker+' reclaimed_earlier=1 total=2')
assert m.validate_gl_log(combined)==pixels
# Exact duplicate console replay must not double-count surface ownership.
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[]
for line in audit.splitlines(True):bad.append(combined.replace(line,''))
for before,after in [('cached=1 pages=1196','cached=0 pages=1196'),('pages=1196','pages=1195'),('CPU_unmapped=1','CPU_unmapped=0'),('dual_ASID_TLBI=1','dual_ASID_TLBI=0'),('used=16384','used=0'),('header_excluded=1','header_excluded=0'),('retired=1 GPU_memory_access=0','retired=0 GPU_memory_access=0'),('GPU_memory_access=0','GPU_memory_access=1'),('sid=1 bytes=4898816 stride','sid=2 bytes=4898816 stride'),('flags=20000','flags=80000'),('buffers=1 context_null=1','buffers=2 context_null=1'),('reclaimed_earlier=1 total=2','reclaimed_earlier=0 total=1')]:bad.append(combined.replace(before,after))
bad.append(combined+'\nwaffle-gl-surface-map: passed=0\n')
bad.append(combined+'\nSURFACE_MAP_TEST revoke_failed=1 backing_retained=1\n')
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Corrupt/missing surface proof accepted')
print(f'PASS strict surface/GEM lifetime parser: complete map+revoke+metadata+pixel proof and exact replay;{len(bad)} missing/changed proof, stale/cached ordinary GEM, budget/close and failure-marker refusals; synthetic logs only')
