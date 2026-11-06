"""Actual U04 GPU writes/fences and deliberately corrupted evidence."""
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[2];m=runpy.run_path(str(root/'scripts/run_waffle_ios.py'))
s=(root/'work/waffle/runs/20261106T101950Z/kernel-final.log').read_text(errors='replace')
assert m['validate_unixnu_submit_log'](s)=={1:1,2:2};assert len(m['validate_gl_log'](s))==256
for before,after in [('checked=4 wrong=0 guards=2','checked=4 wrong=1 guards=2'),('values=57414646/4c454750/13579bdf/2468ace0','values=deadbeef/deadbeef/deadbeef/deadbeef'),('pass=2 fence=2','pass=2 fence=1'),('UNIXNU_SUBMIT fence=1','MISSING_SUBMIT fence=1'),('completed=2 waited=2 future_refused=2','completed=2 waited=1 future_refused=2')]:
 bad=s.replace(before,after)
 try:m['validate_unixnu_submit_log'](bad)
 except RuntimeError:pass
 else:raise AssertionError('Broken native GPU submit proof accepted')
conflict=s+'\nwaffle-unixnu-submit: pass=1 fence=9 checked=4 wrong=0 guards=2 values=57414646/4c454750/13579bdf/2468ace0\n'
try:m['validate_unixnu_submit_log'](conflict)
except RuntimeError:pass
else:raise AssertionError('Conflicting native GPU result accepted')
print('PASS actual U04 native fences1/2,4GPUvalues+2guards each and full256pixelGL; wrong/stalevalues, duplicatefence, missinghardware/summary and conflictingresults rejected')
