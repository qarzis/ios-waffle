#!/usr/bin/env python3
"""Summarize existing EAGL timing samples without inventing a panel FPS.

Console prints frames1..40 and every20th thereafter, so these are deliberately
sampled timings, not an unbiased frame count or throughput measurement.
"""
import argparse,hashlib,json,re,statistics
from pathlib import Path

def summarize(rows):
    if not rows:return None
    def metrics(key):
        values=sorted(r[key] for r in rows)
        return dict(median=statistics.median(values),p95=values[min(len(values)-1,(len(values)*95+99)//100-1)],maximum=max(values))
    return dict(samples=len(rows),frame_us=metrics('frame_us'),copy_out_us=metrics('copy_out_us'),
        wait_us=metrics('wait_us'),hand_on_us=metrics('hand_on_us'),
        copy_share_of_sampled_frame_time=sum(r['copy_out_us'] for r in rows)/max(1,sum(r['frame_us'] for r in rows)))

def analyze(run,last_snapshot):
    pattern=re.compile(r'redwood-gl: frame (\d+): (\d+) GL calls, (\d+) draws, (\d+) triangles, (\d+) clears;.*?; (\d+) us \((\d+) handing on, (\d+) waiting, (\d+) copying out\), (\d+) before it for the IOSurfaces')
    rows=[];seen=set();proof={}
    for path in sorted(run.glob('kernel-[0-9]*.log'),key=lambda p:int(p.stem.split('-')[1])):
        if int(path.stem.split('-')[1])>last_snapshot:continue
        text=path.read_text(errors='replace')
        added=False
        for m in pattern.finditer(text):
            key=m.group(0)
            if key in seen:continue
            seen.add(key);values=list(map(int,m.groups()))
            row=dict(zip(['frame','GL_calls','draws','triangles','clears','frame_us','hand_on_us','wait_us','copy_out_us','texture_attach_before_frame_us'],values))
            row['first_snapshot']=path.name;rows.append(row);added=True
        if added:proof[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(run=str(run),last_snapshot=last_snapshot,panel_FPS_measured=False,
        limitations=['Printed frames are sampled, not every frame.','No PID/context tag in historical EAGL timing lines: per-process attribution is not guaranteed.',
          'Duplicate identical console reports are counted once.','Scene changes and first600-frame GL error-check behavior prevent uncontrolled before/after FPS claims.',
          'Frame timing includes GL and CPU readback work; it is not display refresh cadence.'],
        all_printed_samples=summarize(rows),after_frame_40=summarize([r for r in rows if r['frame']>40]),
        after_frame_600=summarize([r for r in rows if r['frame']>600]),
        rows=rows,source_sha256=proof)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('--last-snapshot',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=analyze(args.run,args.last_snapshot);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['panel_FPS_measured','all_printed_samples','after_frame_40','after_frame_600']},indent=2))
