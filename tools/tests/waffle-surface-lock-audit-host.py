#!/usr/bin/env python3
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[2];analyze=runpy.run_path(str(root/'tools/analyze-waffle-surface-locks.py'))['analyze']
banner='waffle-surface-lock: audit_enabled=1 max_records=128\n'
def row(n,unlock,options,seed):return f'waffle-surface-lock: seq={n} pid=1 sid=7 unlock={unlock} options={options:x} seed={seed}\n'
text=banner+row(1,0,0,4)+row(2,1,0,5)+row(3,0,1,5)+row(4,1,1,5)
r=analyze(text);assert r['record_count']==4 and r['writer_locks']==r['writer_unlocks']==r['reader_locks']==r['reader_unlocks']==1
assert not r['unmatched_unlock_sequences'] and not r['open_brackets'] and analyze(text+'\n'+text)==r
r=analyze(banner+row(1,1,0,5));assert r['unmatched_unlock_sequences']==[1] # Evidence of a possible framework fast path, never silently treated as paired.
r=analyze(banner+row(1,0,0,4));assert r['open_brackets']==[{'pid':1,'sid':7,'role':'writer','depth':1}]
assert analyze(banner)['record_count']==0
failed=row(1,0,0,4).rstrip()+' result=e00002bc\n'
r=analyze(banner+failed+row(2,0,0,4)+row(3,1,0,5))
assert r['failed_sequences']==[1] and r['writer_locks']==r['writer_unlocks']==1 and not r['open_brackets']

for bad in [text.replace(banner,''),text.replace(row(2,1,0,5),''),text+row(1,1,0,5),banner+row(129,0,0,4)]:
 try:analyze(bad)
 except ValueError:pass
 else:raise AssertionError('Invalid lock audit accepted')
print('PASS lock trace analyzer: exact replay, reader/writer brackets, unmatched/absent traps remain diagnostic evidence; missing/conflicting/over-bound records refused; synthetic only')
