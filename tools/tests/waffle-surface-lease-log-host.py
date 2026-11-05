#!/usr/bin/env python3
from pathlib import Path
import runpy
r=Path(__file__).resolve().parents[2];check=runpy.run_path(str(r/'scripts/run_waffle_ios.py'))['validate_surface_lease_log']
text='''SURFACE_LEASE_TEST op=1 handle=27 active=1 waiting=0 manual_no_GPU=1
waffle-surface-lock: seq=1 pid=1 sid=1 unlock=0 options=2 seed=7 result=e00002cc
SURFACE_LEASE_TEST op=3 handle=27 active=1 waiting=1 manual_no_GPU=1
SURFACE_LEASE_TEST op=2 handle=27 active=0 waiting=0 manual_no_GPU=1
waffle-gl-surface-lease: passed=1 sid=1 CPU_writer_refused_GPU_lease=1 AvoidSync_refused=1 reader_allowed=1 kernel_waiter_seen=1 writer_resumed=1 manual_no_GPU=1
'''
check(text);check(text+text)
for bad in [text.replace('passed=1','passed=0'),text.replace('waiting=1','waiting=0'),text.replace('result=e00002cc','result=0'),text.replace('op=2 handle=27','op=2 handle=28'),text.replace('SURFACE_LEASE_TEST op=3','GENERAL_SUBMIT begin fence=1\nSURFACE_LEASE_TEST op=3'),text.replace('AvoidSync_refused=1','AvoidSync_refused=0')]:
 try:check(bad)
 except RuntimeError:pass
 else:raise AssertionError('Invalid lease contention proof accepted')
print('PASS lease log: acquisition, kernel waiter, actual AvoidSync refusal, no manual GPU, release and resumed writer; six corrupt proofs refused, synthetic only.')
