#!/usr/bin/env python3
"""Reject incomplete private surface GPU-write evidence without weakening GEM ABI."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-log-host.py')}
exec((root/'tools/tests/waffle-surface-log-host.py').read_text(),ns)
m=ns['m'];text=ns['text'];marker=ns['marker']
audit='''SURFACE_BO published index=2 VA=100004000 bytes=4898816 cached=1 pages=1196
GENERAL_BO published index=3 VA=1004b0000 bytes=4096 allocated=16384 flags=20000 pages=4
SURFACE_WRITE_COMMAND_BO index=3 VA=1004b0000 bytes=4096 allocated=16384
GENERAL submitted fence=2 private_surface_write=1
GENERAL_BO reclaimed index=3 VA=1004b0000 bytes=16384 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=4915200
GENERAL_BO reclaimed index=2 VA=100004000 bytes=4898816 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=16384
SURFACE_WRITE_TEST passed=1 sid=1 VA=100004000 bytes=4898816 fence=2 checked=4 wrong=0 restored=1 retired=1
SURFACE_WRITE_DATA values=57414646/4c454750/13579bdf/2468ace0 cached=1 GPU_memory_access=1
waffle-gl-surface-write: passed=1 GPU_memory_access=1 restored=1
waffle-gl-surface: sid=1 bytes=4898816 stride=3008 width=750 height=1624 format=42475241 metadata_expected=1
waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1
'''
combined=text.replace(marker,audit+marker+' reclaimed_earlier=2 total=3')
def validate(t):return m.validate_gl_bo_lifetimes(t,32,33554432)
assert len(validate(combined)[0])==1
assert validate(combined)==validate(combined+'\n'+combined)
bad=[combined.replace(line,'') for line in audit.splitlines(True)]
for before,after in [('values=57414646','values=00000000'),('fence=2 checked','fence=0 checked'),('wrong=0 restored','wrong=1 restored'),('restored=1 retired','restored=0 retired'),('bytes=4096 allocated=16384 flags=20000','bytes=4096 allocated=16384 flags=80000'),('used=4915200','used=16384'),('bytes=4096 allocated=16384\n','bytes=8192 allocated=16384\n')]:bad.append(combined.replace(before,after))
for marker in ['SURFACE_WRITE_TEST uncertain=1','SURFACE_WRITE_TEST command_revoke_failed=1','waffle-gl-surface-write: passed=0']:bad.append(combined+'\n'+marker)
for t in bad:
 try:validate(t)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete GPU write evidence accepted')
print(f'PASS private write lifetime evidence/replay and {len(bad)} missing/corrupt proof refusals; synthetic only')
