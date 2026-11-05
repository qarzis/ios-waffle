#!/usr/bin/env python3
"""Analyze bounded read-only commit observations, never infer a release fence."""
from pathlib import Path
import re,json,argparse,hashlib

def analyze(text):
 banners=re.findall(r'waffle-display-completion: records=(\d+) no_extra_writes=1 guard_frames=2 cntfrq=(\d+)',text)
 if not banners or len(set(banners))!=1:raise ValueError('Missing/conflicting completion audit banner')
 count,hz=map(int,banners[0])
 if not 1<=count<=128 or hz<=0:raise ValueError('Invalid bounded audit/clock')
 pattern=r'waffle-display-completion: row=(\d+) seq=(\d+) stage=(\d+) ticks=(\d+) valid=([01]) frame0=(\d+) frame1=(\d+) flush=([0-9a-f]+) scheduler=([0-9a-f]+) auto_status=([0-9a-f]+) write_line=(\d+) read_line=(\d+) address0=([0-9a-f]+) address1=([0-9a-f]+)'
 rows={};keys=('row','seq','stage','ticks','valid','frame0','frame1','flush','scheduler','auto_status','write_line','read_line','address0','address1')
 for fields in re.findall(pattern,text):
  v={k:int(f,16 if k in ('flush','scheduler','auto_status','address0','address1') else 10) for k,f in zip(keys,fields)}
  if not 1<=v['seq']<=9 or v['stage'] not in (1,2,3):raise ValueError('Invalid sample identity')
  if v['row'] in rows and rows[v['row']]!=v:raise ValueError('Conflicting sample replay')
  rows[v['row']]=v
 if sorted(rows)!=list(range(count)):raise ValueError('Missing completion observations')
 ordered=[rows[i] for i in range(count)]
 if any(b['ticks']<a['ticks'] for a,b in zip(ordered,ordered[1:])):raise ValueError('Non-monotonic observations')
 sequences=[]
 for seq in sorted({r['seq'] for r in ordered}):
  group=[r for r in ordered if r['seq']==seq];base=next((r for r in group if r['stage']==2 and r['valid'] and r['frame0']==r['frame1']),None)
  post=next((r for r in group if r['stage']==3),None)
  states=[]
  if base:
   for r in group:
    if not r['valid'] or r['frame0']!=r['frame1']:continue
    delta=(r['frame0']-base['frame0'])&0xffffffff
    if delta>=0x80000000:continue
    states.append({'stage':r['stage'],'mdp_delta':delta,'elapsed_us':round((r['ticks']-base['ticks'])*1e6/hz,2),'flush':r['flush'],'scheduler':r['scheduler'],'auto_status':r['auto_status']})
  sequences.append({'sequence':seq,'baseline_observed':base is not None,'post_flush_observed':post is not None,'observations':states})
 return {'record_count':count,'clock_hz':hz,'invalid_records':sum(not r['valid'] for r in ordered),'crossed_frame_records':sum(r['frame0']!=r['frame1'] for r in ordered if r['valid']),
         'scheduler_values':sorted({r['scheduler'] for r in ordered if r['valid']}),'auto_status_values':sorted({r['auto_status'] for r in ordered if r['valid']}),
         'sequences':sequences,'one_frame_retirement_qualified':False,'claim':'Read-only sparse observations around unchanged two-frame guard; no IRQ edge/fence or FPS proof','records':ordered}
def analyze_run(directory):
    """Use one complete immutable snapshot; never stitch conflicting epochs."""
    directory=Path(directory)
    logs=sorted((p for p in directory.glob('kernel-*.log') if p.stem.removeprefix('kernel-').isdigit()),
                key=lambda p:int(p.stem.removeprefix('kernel-')))
    logs.append(directory/'kernel-final.log')
    for path in logs:
        if not path.is_file():continue
        raw=path.read_bytes()
        if b'waffle-display-completion: records=' not in raw:continue
        try:report=analyze(raw.decode(errors='replace'))
        except ValueError:continue
        report['source_log']=path.name;report['source_log_sha256']=hashlib.sha256(raw).hexdigest()
        return report
    raise ValueError('No complete completion trace in saved run snapshots')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);a=p.parse_args();print(json.dumps(analyze_run(a.log) if a.log.is_dir() else analyze(a.log.read_text(errors='replace')),indent=2))
