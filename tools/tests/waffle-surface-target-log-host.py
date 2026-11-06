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
