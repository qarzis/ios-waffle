#!/usr/bin/env python3
"""Analyze bounded read-only commit observations, never infer a release fence."""
from pathlib import Path
import re,json,argparse,hashlib

def analyze(text):
 banners=re.findall(r'waffle-display-completion: records=(\d+) no_extra_writes=([01]) guard_frames=2 cntfrq=(\d+)',text)
 if not banners or len(set(banners))!=1:raise ValueError('Missing/conflicting completion audit banner')
 count,readonly,hz=map(int,banners[0])
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
 irq_rows={}
 irq_keys=('row','top_status','top_enable','ctl_status','ctl_enable','tear_status','tear_enable','active')
 for fields in re.findall(r'waffle-display-irq: row=(\d+) top_status=([0-9a-f]+) top_enable=([0-9a-f]+) ctl_status=([0-9a-f]+) ctl_enable=([0-9a-f]+) tear_status=([0-9a-f]+) tear_enable=([0-9a-f]+) active=([0-9a-f]+)',text):
  row={k:int(v,10 if k=='row' else 16) for k,v in zip(irq_keys,fields)}
  if row['row'] in irq_rows and irq_rows[row['row']]!=row:raise ValueError('Conflicting IRQ sample replay')
  irq_rows[row['row']]=row
 if 'waffle-display-irq:' in text and sorted(irq_rows)!=list(range(count)):raise ValueError('Missing paired IRQ samples')
 valid_irq=[irq_rows[r['row']] for r in ordered if r['valid'] and r['frame0']==r['frame1'] and r['row'] in irq_rows]
 irq_values={k:sorted({r[k] for r in valid_irq}) for k in irq_keys[1:]}
 rising={name:[] for name in ('pp0_done','pp1_done','ctl0_done','tear_autorefresh_done')}
 bits={'pp0_done':('top_status',1<<8),'pp1_done':('top_status',1<<9),'ctl0_done':('ctl_status',1),'tear_autorefresh_done':('tear_status',1)}
 for before,after in zip(valid_irq,valid_irq[1:]):
  for name,(field,mask) in bits.items():
   if not before[field]&mask and after[field]&mask:rising[name].append(after['row'])
 probe_headers=re.findall(r'waffle-display-irq-probe: enabled=1 writes=(\d+) clear_offset=1018 clear_mask=100 guard_frames=2 mode_change=0 irq_enable_writes=0',text)
 probe={'enabled':bool(probe_headers),'writes':0,'fresh_events':0,'actions':[]}
 if probe_headers:
  if len(set(probe_headers))!=1 or not 0<=int(probe_headers[0])<=8:raise ValueError('Invalid masked IRQ probe bound')
  probe['writes']=int(probe_headers[0])
  if bool(readonly)!=(not bool(probe['writes'])):raise ValueError('IRQ write accounting disagrees with read-only banner')
  actions={}
  for fields in re.findall(r'waffle-display-irq-probe: row=(\d+) seq=(\d+) action=([1-4]) wrote=([01]) status_after=([0-9a-f]+) mux=([0-9a-f]+) version=([0-9a-f]+)',text):
   keys=('row','seq','action','wrote','status_after','mux','version');v={k:int(x,16 if i>=4 else 10) for i,(k,x) in enumerate(zip(keys,fields))}
   if v['row'] not in rows or v['seq']!=rows[v['row']]['seq'] or rows[v['row']]['stage']!=1:raise ValueError('IRQ probe action lacks matching wait sample')
   if v['row'] in actions and actions[v['row']]!=v:raise ValueError('Conflicting IRQ probe action')
   actions[v['row']]=v
  armed={};written=set();done=set()
  for index,v in sorted(actions.items()):
   sample=rows[index];irq=irq_rows.get(index)
   if not irq or not sample['valid'] or sample['frame0']!=sample['frame1']:raise ValueError('IRQ probe sample not stable')
   baseline=next((row for row in ordered if row['seq']==v['seq'] and row['stage']==2),None)
   delta=(sample['frame0']-baseline['frame0'])&0xffffffff if baseline else 0
   commit=next((row for row in ordered if row['seq']==v['seq'] and row['stage']==3 and row['row']<index),None)
   if v['wrote'] and v['action'] not in (1,4):raise ValueError('Impossible IRQ write action')
   if v['wrote']:
    if not commit or sample['address0'] not in (0xd5100000,0xd6270000) or sample['address0']!=sample['address1'] or sample['address0']!=commit['address0'] or v['seq'] in written or delta!=1 or sample['flush'] or not sample['auto_status'] or irq['top_enable'] or not irq['top_status']&0x100 or irq['active']!=2 or v['mux'] not in (0,0xf0000) or v['version']!=0xa0000000:
     raise ValueError('IRQ probe wrote without a new masked PP0 transfer')
    written.add(v['seq'])
   if v['action']==1:
    if not v['wrote'] or v['status_after']&0x100:raise ValueError('PP0 clear baseline not established')
    armed[v['seq']]=index
   elif v['action']==2:
    if v['wrote'] or v['seq'] not in armed or v['seq'] in done or not irq['top_status']&0x100 or irq['top_enable'] or not 1<=delta<0x80000000:
     raise ValueError('Fresh PP0 event lacks an earlier clear')
    done.add(v['seq'])
  if sum(v['wrote'] for v in actions.values())!=probe['writes']:raise ValueError('Masked IRQ write total mismatch')
  probe['actions']=[actions[k] for k in sorted(actions)];probe['fresh_events']=len(done)
 elif not readonly or 'waffle-display-irq-probe:' in text:raise ValueError('Unbound or unaccounted IRQ write probe')
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
         'no_extra_MMIO_writes':bool(readonly),'irq_probe':probe,
         'irq_record_count':len(irq_rows),'irq_values':irq_values,'sampled_irq_rising_edges':rising,
         'sequences':sequences,'one_frame_retirement_qualified':False,'claim':('Bounded masked PP0 clear/reassertion observations under unchanged guard; no release fence or FPS qualification' if probe['enabled'] else 'Read-only sparse observations around unchanged two-frame guard; no IRQ edge/fence or FPS proof'),'records':ordered}
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
