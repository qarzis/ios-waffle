#!/usr/bin/env python3
"""Strict native-output proof ordering; synthetic logs, not hardware evidence."""
from pathlib import Path
r=Path(__file__).resolve().parents[2]
ns={'__file__':str(r/'tools/tests/waffle-gl-log-host.py')}
s=(r/'tools/tests/waffle-gl-log-host.py').read_text();exec(s[:s.index('assert m.validate_gl_log(text)==pixels')],ns);m=ns['m']
text='''GENERAL gem_new handle=2 bytes=4898816 allocated=4898816 flags=80000 VA=100004000
SURFACE_TARGET imported=1 sid=1 handle=2 index=2 GPU_writable=1 private_PID1=1
waffle-gl-surface-target: begin sid=1 texture=7 native_cached=1 exclusive_PID1=1
'''
for fence in [1,2]:
 text+=f'''SURFACE_TARGET prepare=1 handle=2 bytes=4898816 CPU_clean=1 private_PID1=1
GENERAL_SUBMIT done fence={fence} seq={m.gl_sequence(fence-1)} control={fence:08x} checked=4096 wrong_words=0
SURFACE_TARGET complete=1 handle=2 fence={fence} CPU_invalidated=1
'''
text+='waffle-gl-surface-target: passed=1 checked=1218000 wrong=0 first=ffff0000 last=ff00ff00 CPU_direct=1 glReadPixels=0 restored=1 GL_error=0\n'
m.validate_surface_target_log(text)
bad=[]
for line in text.splitlines(True):bad.append(text.replace(line,'',1))
for a,b in [('flags=80000','flags=80002'),('bytes=4898816 CPU_clean','bytes=4096 CPU_clean'),('CPU_direct=1','CPU_direct=0'),('glReadPixels=0','glReadPixels=1'),('restored=1','restored=0'),('sid=1 texture','sid=2 texture'),('fence=2 CPU_invalidated','fence=1 CPU_invalidated'),('wrong_words=0','wrong_words=1'),('checked=1218000','checked=1200000')]:bad.append(text.replace(a,b))
lines=text.splitlines(True);lines[3],lines[4]=lines[4],lines[3];bad.append(''.join(lines))
for t in bad:
 try:m.validate_surface_target_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Broken native target proof accepted')
print(f'PASS native output checker: ordered clean/completion/invalidate pairs, exact sizes/fences/full pixels; {len(bad)} negative fixtures refused. Synthetic only.')

# Also exercise the ordinary parser's import lifetime, GEM budget and teardown
# accounting together with the private target proof, not just its subparser.
scope={'__file__':str(r/'tools/tests/waffle-surface-resource-log-host.py')}
exec((r/'tools/tests/waffle-surface-resource-log-host.py').read_text(),scope)
base=scope['text']
publication='''SURFACE_BO published index=2 VA=100004000 bytes=4898816 cached=1 pages=1196
GENERAL gem_new handle=2 bytes=4898816 allocated=4898816 flags=80000 VA=100004000
SURFACE_IMPORT created=1 sid=1 handle=2 index=2 VA=100004000 bytes=4898816 lifetime_only=0
SURFACE_IMPORT reused=1 sid=1 handle=2
SURFACE_TARGET imported=1 sid=1 handle=2 index=2 GPU_writable=1 private_PID1=1
waffle-gl-surface-target: begin sid=1 texture=7 native_cached=1 exclusive_PID1=1
SURFACE_TARGET prepare=1 handle=2 bytes=4898816 CPU_clean=1 private_PID1=1
'''
end='''SURFACE_TARGET complete=1 handle=2 fence=1 CPU_invalidated=1
waffle-gl-surface-target: passed=1 checked=1218000 wrong=0 first=ffff0000 last=ff00ff00 CPU_direct=1 glReadPixels=0 restored=1 GL_error=0
'''
retirement='''GENERAL_BO reclaimed index=2 VA=100004000 bytes=4898816 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=16384
GENERAL bo_retired handle=2 bytes=4898816 backing_retained=0
waffle-gl-surface-resource: passed=1 sid=1 textures=2 width=750 height=1624 deleted=2 GPU_memory_access=1
waffle-gl-surface: sid=1 bytes=4898816 stride=3008 width=750 height=1624 format=42475241 metadata_expected=1
waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1
'''
whole=base.replace('GENERAL_SUBMIT begin fence=1',publication+'GENERAL_SUBMIT begin fence=1')
done='GENERAL_SUBMIT done fence=1 seq=44 control=00000001 checked=4096 wrong_words=0\n'
whole=whole.replace(done,done+end)
marker='GENERAL_BO released after GPU stop and context detach count=1'
whole=whole.replace(marker,retirement+marker+' reclaimed_earlier=1 total=2').replace('completed=1 buffers=1','completed=1 buffers=2')
assert m.validate_gl_log(whole)==scope['pixels']
for needle in ['SURFACE_IMPORT reused=1 sid=1 handle=2\n', retirement.splitlines(True)[0], done]:
 try:m.validate_gl_log(whole.replace(needle,''))
 except RuntimeError:pass
 else:raise AssertionError('Combined target lifetime proof accepted missing '+needle)
print('PASS combined private output/import/GEM budget/cache handoff/teardown parser and three missing-evidence refusals; synthetic only.')
