#!/usr/bin/env python3
"""Inspect actual framework lock traps; do not assume locks are exclusive."""
from pathlib import Path
import argparse,json,re

def analyze(text):
    if 'waffle-surface-lock: audit_enabled=1 max_records=128' not in text:
        raise ValueError('Native surface lock audit was not enabled')
    rows={}
    for fields in re.findall(r'waffle-surface-lock: seq=(\d+) pid=(\d+) sid=(\d+) unlock=([01]) options=([0-9a-f]+) seed=(\d+)(?: result=([0-9a-f]+))?',text):
        seq,pid,sid,unlock=int(fields[0]),int(fields[1]),int(fields[2]),int(fields[3])
        row={'seq':seq,'pid':pid,'sid':sid,'unlock':bool(unlock),'options':int(fields[4],16),'seed':int(fields[5]),'result':int(fields[6],16) if fields[6] else 0}
        if not 1<=seq<=128 or not 0<sid<=0xffffffff or row['seed']>0xffffffff:raise ValueError('Invalid native lock record')
        if seq in rows and rows[seq]!=row:raise ValueError('Conflicting native lock record')
        rows[seq]=row
    if sorted(rows)!=list(range(1,len(rows)+1)):raise ValueError('Missing native lock records')
    failed=[];active={};counts={'writer_locks':0,'writer_unlocks':0,'reader_locks':0,'reader_unlocks':0};unmatched=[]
    for seq,row in sorted(rows.items()):
        if row['result']:
            failed.append(seq);continue
        role='reader' if row['options']&1 else 'writer';key=(row['pid'],row['sid'],role)
        counts[role+('_unlocks' if row['unlock'] else '_locks')]+=1
        if not row['unlock']:active[key]=active.get(key,0)+1
        elif active.get(key,0):active[key]-=1
        else:unmatched.append(seq)
    return {'record_count':len(rows),'bounded_log_full':len(rows)==128,**counts,
            'failed_sequences':failed,'unmatched_unlock_sequences':unmatched,'open_brackets':[{'pid':k[0],'sid':k[1],'role':k[2],'depth':v} for k,v in active.items() if v],
            'records':[rows[k] for k in sorted(rows)],'claim':'Observed trap traffic only; no CPU/GPU exclusion or lease qualification'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);args=p.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace')),indent=2))
