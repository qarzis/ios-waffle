#!/usr/bin/env python3
"""Validate captured UI proof across rolling-console snapshots.

Keep first-observed order, original lines, and source locations. Never repair
missing events or replace the original hardware-runner result. This is a
separate evidence report; raw captures remain authoritative.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re

MARKERS=('waffle-ui-', 'waffle-gl-', 'waffle-gpu:', 'waffle-iommu:',
         'waffle-gmu:', 'waffle-aop:', 'waffle-power:', 'waffle-clock:',
         'an OpenGL ES', 'redwood-gl: frame ', 'MiniIOMobileFramebuffer: swap ',
         'A SHADER DOES NOT COMPILE', 'REBOOT REQUIRED')

def collect(paths):
    seen=set();records=[];sources={}
    for path in paths:
        data=path.read_bytes();sources[path.name]=hashlib.sha256(data).hexdigest()
        for number,line in enumerate(data.decode(errors='replace').splitlines(),1):
            if line not in seen and any(marker in line for marker in MARKERS):
                seen.add(line);records.append(f'{path.name}:{number}: {line}\n')
    return ''.join(records),sources

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=('ui','gl'),default='ui')
    args=p.parse_args()
    paths=sorted((x for x in args.run.glob('kernel-*.log')
                  if re.fullmatch(r'kernel-\d+\.log',x.name)),
                 key=lambda x:int(x.stem.split('-')[1]))
    if not paths:raise SystemExit('No numbered raw snapshots')
    journal,sources=collect(paths)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    evidence=args.output.with_suffix('.log');evidence.write_text(journal)
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    report={'run':str(args.run),'raw_snapshots':sources,
            'evidence':str(evidence),'evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
            'original_runner_result_unchanged':True,'order':'first observation, no sorting of GPU events',
            'pixel_reference_or_optical_proof':False}
    try:
        report['proof']=(runner.validate_ui_workload_log(journal) if args.kind=='ui'
                         else {'correct_reference_pixels':len(runner.validate_gl_log(journal))})
        report['strict_component_proof_passed']=True
    except RuntimeError as error:
        report['strict_component_proof_passed']=False;report['error']=str(error)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='raw_snapshots'},indent=2))
    return 0 if report['strict_component_proof_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
