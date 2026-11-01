"""Parse inner runner flags without allowing filesystem or phone calls."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'work/waffle/gpu/run-publish-test.py').read_text()
prefix=source[:source.index("before=set(Path('work/waffle/runs').iterdir())")]
chain=['--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-dispatch','--gl-context']
previous=sys.argv
try:
 for flags in [chain,chain+['--ui-workload'],chain+['--ui-workload','--ui-long-test']]:
  sys.argv=['runner','94','artifact',*flags];ns={};exec(prefix,ns)
  assert ns['image']==13 and ns['probe']==94
 for flags in [chain+['--unknown'],chain+['--ui-long-test'],chain+['--ui-workload','--ui-workload']]:
  sys.argv=['runner','94','artifact',*flags]
  try:exec(prefix,{})
  except AssertionError:pass
  else:raise AssertionError('Invalid UI runner flags accepted')
finally:sys.argv=previous
print('Pure inner-runner CLI:defaultGL/shortUI/longUI chains accepted; unknown, incomplete longUI and duplicate flags refused beforefilesystem/USB work.')
