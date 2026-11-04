#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-sample-log-host.py')}
exec((root/'tools/tests/waffle-surface-sample-log-host.py').read_text(),ns)
m=ns['m'];combined=ns['combined'];pixels=ns['pixels'];samples=ns['samples'];block=ns['block'];sync=ns['sync']
proof=''
for phase,fence in [(1,4),(2,5),(3,6)]:
 proof+=sync+block.format(f=fence,s=43+fence)
 proof+=f'waffle-gl-surface-reuse: phase={phase} passed=1 checked=256 wrong=0 GL_error=0 same_texture=1\n'
 values=[0xff00ff00]*256 if phase==1 else [0xffff00ff]*256 if phase==2 else samples
 for i in range(0,256,8):proof+=f'waffle-gl-surface-reuse: phase={phase} offset={i} values='+('/'.join(f'{v:08x}' for v in values[i:i+8]))+'\n'
proof+='waffle-gl-surface-reuse: result=1 phases=3 source_restored=1 same_native_GEM=1\n'
combined=combined.replace('GENERAL_BO reclaimed index=2',proof+'GENERAL_BO reclaimed index=2').replace('completed=3 buffers=2','completed=6 buffers=2')
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[]
for line in proof.splitlines(True):
 if 'waffle-gl-surface-reuse:' in line:bad.append(combined.replace(line,''))
for before,after in [('ff00ff00','ff000000'),('ffff00ff','ff00ff00'),('source_restored=1','source_restored=0'),('same_texture=1','same_texture=0')]:bad.append(combined.replace(before,after))
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete native update/reuse proof accepted')
print(f'PASS same native texture/GEM update reuse: 3 phases/768 independent pixels plus original sample, {len(bad)} missing/stale/restoration proof refusals; synthetic only')
