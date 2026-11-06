"""Replay actual U03 log and reject broken relocation/lifetime evidence."""
from pathlib import Path
import runpy,re
root=Path(__file__).resolve().parents[2];m=runpy.run_path(str(root/'scripts/run_waffle_ios.py'))
s=(root/'work/waffle/runs/20261106T101034Z/kernel-final.log').read_text(errors='replace')
assert len(m['validate_gl_log'](s))==256
for run in ['20261106T095030Z','20261106T100106Z']:
 assert len(m['validate_gl_log']((root/f'work/waffle/runs/{run}/kernel-final.log').read_text(errors='replace')))==256
pattern=r'UNIXNU_BO relocate passed=1 old=([0-9a-f]+) new=([0-9a-f]+) poisoned=0'
match=re.search(pattern,s);assert match
bad=[s.replace('UNIXNU_BO relocate passed=1','UNIXNU_BO relocate passed=0'),
 s.replace('new=10f000000 poisoned=0','new=10f000000 poisoned=1'),
 re.sub(pattern,lambda x:x[0].replace('old='+x[1],'old=100000000'),s),
 s.replace('new=10f000000 poisoned=0','new=ffffffffffffc000 poisoned=0'),
 s.replace('new=10f000000 poisoned=0','new=10f001000 poisoned=0'),
 re.sub(r'^.*UNIXNU_BO relocate.*\n','',s,flags=re.M),
 s.replace('waffle-unixnu-map: relocated=2 chosen_VA=10f000000 remap_refused=2','missing-map-proof')]
for value in bad:
 try:m['validate_gl_log'](value)
 except RuntimeError:pass
 else:raise AssertionError('Broken relocation/lifetime evidence accepted')
print('PASS actual U03 full GL validation; U01/U02 regressions; relocation failure/poison/source/range/alignment/missing events/missing proof rejected. Original U03 runner failure preserved, no hardware replay.')
