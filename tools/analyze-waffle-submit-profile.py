#!/usr/bin/env python3
"""Sampled GENERAL submit phase costs with unchanged full-buffer validation."""
from pathlib import Path
import argparse,importlib.util,json,re,statistics
ROOT=Path(__file__).resolve().parents[1]
FIELDS=('snapshot','stage','preverify','exchange','fence_wait','postverify','finish')
def samples(text,fences):
    pattern=r'GENERAL_PROFILE fence=(\d+) '+r' '.join(name+r'_us=(\d+)' for name in FIELDS)
    result={}
    for match in re.findall(pattern,text):
        fence=int(match[0]);values=tuple(map(int,match[1:]))
        if fence in result and result[fence]!=values:raise RuntimeError('Conflicting phase sample')
        if not sum(values):raise RuntimeError('Empty phase timing')
        result[fence]=values
    expected={i for i in range(1,fences+1) if i<=16 or i%128==0}
    if set(result)!=expected:raise RuntimeError('Missing/unexpected sampled submit phases')
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    collector=module('collector',ROOT/'tools/collect-waffle-ui-evidence.py');runner=module('runner',ROOT/'scripts/run_waffle_ios.py')
    paths=sorted((x for x in args.run.glob('kernel-*.log') if re.fullmatch(r'kernel-\d+\.log',x.name)),key=lambda x:int(x.stem.split('-')[1]))
    if not paths and (args.run/'kernel-final.log').is_file():paths=[args.run/'kernel-final.log']
    text,sources=collector.collect(paths);runner.validate_gl_log(text);fences=runner.gl_completed_fences(text);values=samples(text,fences)
    rows=[dict(fence=fence,**dict(zip((name+'_us' for name in FIELDS),value))) for fence,value in sorted(values.items())]
    totals={}
    for label,selected in [('all_samples',rows),('after_first_16',rows[16:])]:
        if not selected:continue
        sums={name:sum(row[name+'_us'] for row in selected) for name in FIELDS};total=sum(sums.values())
        guarded=sums['stage']+sums['preverify']+sums['postverify']
        totals[label]={'samples':len(selected),'phase_median_us':{name:statistics.median(row[name+'_us'] for row in selected) for name in FIELDS},
                       'phase_sum_us':sums,'full_buffer_operations_share':guarded/total if total else None}
    report={'run':str(args.run),'GPU_fences':fences,'strict_GL_proof_passed':True,'sample_policy':'first16 then every128',
            'samples':rows,'summary':totals,'raw_snapshots':sources,
            'limitations':'Sparse phase samples, not panel FPS. Timed exchange includes its diagnostic output; profile-line output excluded. All4096 words remain initialized and verified before/after each job.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('samples','raw_snapshots')},indent=2))
if __name__=='__main__':main()
