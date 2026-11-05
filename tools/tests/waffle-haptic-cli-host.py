#!/usr/bin/env python3
"""Negative H04 requests must stop before artifact reads or any USB action."""
from pathlib import Path
import subprocess,sys
r=Path(__file__).resolve().parents[2]
base=[sys.executable,str(r/'tools/run-waffle-auto.py'),'--artifact','/tmp/waffle-haptic-missing-artifact','--haptic-pulse']
for args in [[],['--cpu-ui-test'],['--cpu-ui-test','--cpus','2'],['--cpu-ui-test','--cpus','1','--torch-readonly'],['--cpu-ui-test','--cpus','1','--torch-pulse'],['--cpu-ui-test','--cpus','1','--torch-service'],['--cpu-ui-test','--cpus','1','--cpu-seconds','90']]:
 p=subprocess.run(base+args,cwd=r,capture_output=True,text=True)
 assert p.returncode==2 and '--haptic-pulse requires isolated' in p.stderr,(args,p.stderr)
 assert 'Traceback' not in p.stderr
print('PASS native haptic CLI: missing explicit CPU1 / read-only / torch write / long-window requests rejected before missing artifact/USB; no device contacted.')

base=[sys.executable,str(r/'tools/run-waffle-auto.py'),'--artifact','/tmp/waffle-haptic-missing-artifact','--haptic-service-test']
for args in [[],['--cpu-ui-test'],['--cpu-ui-test','--cpus','2'],['--cpu-ui-test','--cpus','1','--haptic-pulse'],['--cpu-ui-test','--cpus','1','--torch-readonly'],['--cpu-ui-test','--cpus','1','--cpu-seconds','90']]:
 p=subprocess.run(base+args,cwd=r,capture_output=True,text=True)
 assert p.returncode==2 and '--haptic-service-test requires isolated' in p.stderr,(args,p.stderr)
print('PASS H05 service CLI: CPU1/60sec isolation, one-shot/read-only/long combinations refused before artifact/USB.')
