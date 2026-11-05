#!/usr/bin/env python3
from pathlib import Path
import runpy
r=Path(__file__).resolve().parents[2];check=runpy.run_path(str(r/'scripts/run_waffle_ios.py'))['validate_guarded_display_log']
text='''waffle-display-present: armed=1 working_bytes=18247680 front=d5100000 back=d6270000
waffle-display-present: committed=1 completed=1 target=d6270000 copied=1 rollback=0 rollback_ok=0 us=80 accepted=1 pending=1
waffle-display-present: committed=1 completed=2 target=d5100000 copied=1 rollback=0 rollback_ok=0 us=80 accepted=1 pending=1
waffle-display-source: compose_us=4 copy_us=2 submit_wait_us=3 reads=5 changes=1 pixel_changes=0
waffle-display-present: quiesced=1 restored=1 completed=8 active=d5100000
'''
assert check(text)==8
for bad in [text.replace('restored=1','restored=0'),text.replace('accepted=1','accepted=0'),text.replace('rollback=0','rollback=1'),text.replace('reads=5','reads=0'),text.replace('target=d5100000','target=d6270000'),text.replace('working_bytes=18247680','working_bytes=0')]:
 try:check(bad)
 except RuntimeError:pass
 else:raise AssertionError('Invalid guarded presenter accepted')
print('PASS guarded display proof: both targets, copied commits, source reads and restored teardown mandatory; six failures refused, synthetic only.')
