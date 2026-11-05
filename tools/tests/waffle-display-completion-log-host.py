#!/usr/bin/env python3
from pathlib import Path
import runpy,tempfile
r=Path(__file__).resolve().parents[2];check=runpy.run_path(str(r/'tools/analyze-waffle-display-completion.py'))['analyze']
banner='waffle-display-completion: records=3 no_extra_writes=1 guard_frames=2 cntfrq=1000000\n'
def row(i,stage,ticks,frame,flush):return f'waffle-display-completion: row={i} seq=1 stage={stage} ticks={ticks} valid=1 frame0={frame} frame1={frame} flush={flush:x} scheduler=1 auto_status=0 write_line=0 read_line=5 address0=d6270000 address1=d6270000\n'
text=banner+row(0,2,100,0xffffffff,0)+row(1,3,102,0xffffffff,3)+row(2,1,19000,1,0)
a=check(text);assert a['sequences'][0]['observations'][-1]['mdp_delta']==2 and not a['one_frame_retirement_qualified'];assert check(text+text)==a
for bad in [text.replace('guard_frames=2','guard_frames=1'),text.replace('records=3','records=129'),text.replace(row(1,3,102,0xffffffff,3),''),text+row(1,3,103,0xffffffff,3),text.replace('ticks=19000','ticks=10')]:
 try:check(bad)
 except ValueError:pass
 else:raise AssertionError('Invalid completion trace accepted')
print('PASS display completion analyzer: exact replay, wrap, no false release qualification, five invalid proof refusals; synthetic only.')

ns=runpy.run_path(str(r/'tools/analyze-waffle-display-completion.py'))
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'kernel-1.log').write_text(banner+row(0,2,100,0xffffffff,0))
 (p/'kernel-2.log').write_text(text);(p/'kernel-final.log').write_text('later ring tail without early trace')
 result=ns['analyze_run'](p);assert result['record_count']==3 and result['source_log']=='kernel-2.log'
 (p/'kernel-2.log').unlink()
 try:ns['analyze_run'](p)
 except ValueError:pass
 else:raise AssertionError('Incomplete historical trace accepted')
print('PASS saved-run collection: complete earlier snapshot survives final log rollover; partial history refused.')
def irq(i,top,ctl,tear):return f'waffle-display-irq: row={i} top_status={top:x} top_enable=0 ctl_status={ctl:x} ctl_enable=0 tear_status={tear:x} tear_enable=0 active=2\n'
sticky=text+''.join(irq(i,0x300,1,1) for i in range(3))
a=check(sticky);assert a['irq_record_count']==3 and all(not v for v in a['sampled_irq_rising_edges'].values())
fresh=text+irq(0,0,0,0)+irq(1,0x300,1,1)+irq(2,0x300,1,1)
a=check(fresh);assert all(v==[1] for v in a['sampled_irq_rising_edges'].values()) and not a['one_frame_retirement_qualified']
for bad in [fresh.replace(irq(1,0x300,1,1),''),fresh+irq(1,0,0,0)]:
 try:check(bad)
 except ValueError:pass
 else:raise AssertionError('Incomplete/conflicting IRQ pair accepted')
print('PASS IRQ observations: sticky high is no fresh edge; sampled low/high still not a release fence; missing/conflicting pairs refused.')
