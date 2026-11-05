#!/usr/bin/env python3
"""Exercise actual bridge admission before filesystem, USB or reboot operations."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'work/waffle/gpu/run-publish-test.py').read_text();prefix=source[:source.index("before=set(Path('work/waffle/runs').iterdir())")]
base=['--gl-context','--compute-dispatch','--dynamic-bo','--session','--ib','--writeback','--zap','--lpac-map']
def parse(flags,probe=94):
 old=sys.argv
 try:
  sys.argv=['run-publish-test.py',str(probe),'__no_device_test__',*flags];ns={};exec(compile(prefix,'bridge-admission','exec'),ns);return ns
 finally:sys.argv=old
assert parse(base)['surface_lock_audit'] is False
assert parse([*base,'--surface-lock-audit'])['surface_lock_audit'] is True
for flags,probe in [([*base,'--surface-lock-audit','--ui-workload'],94),([f for f in base if f!='--gl-context']+['--surface-lock-audit'],94),([*base,'--surface-lock-audit'],93)]:
 try:parse(flags,probe)
 except AssertionError:pass
 else:raise AssertionError('Unsafe trace mode accepted')
assert "*(['--surface-lock-audit'] if surface_lock_audit else [])" in source
print('PASS actual lock-audit bridge admission: isolated GL only, default unchanged, UI/non-GL/wrong policy rejected before filesystem/USB; forwarding present')
