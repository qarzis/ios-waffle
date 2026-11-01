#!/usr/bin/env python3
"""Validate E64 full-frame timings; these are offscreen latency, not panel FPS."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,re,statistics

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def frames(text):
    if ('waffle-gl-bench: begin frames=240 width=750 height=1624 inverted=0 CPU_reference_outside_timing=1 panel_FPS=0' not in text or
        'waffle-gl-bench: result=1 frames=240 checked=292320000 wrong=0 inverted=0 panel_FPS=0' not in text or
        not re.search(r'waffle-gl-hook: attachImage=1 surface=\d+ inverted=0',text) or
        'waffle-gl-bench: result=0' in text):
        raise RuntimeError('Complete noninverted actual-hook benchmark missing')
    observed={}
    for row in re.findall(r'waffle-gl-bench: frame=(\d+) render_and_readback_us=(\d+) checked=(\d+) wrong=(\d+) blue=(\d+)',text):
        index,elapsed,checked,wrong,blue=map(int,row)
        value=(elapsed,checked,wrong,blue)
        if index in observed and observed[index]!=value:raise RuntimeError('Conflicting benchmark frame')
        if elapsed<1 or checked!=1218000 or wrong or blue!=int(index%2==0):
            raise RuntimeError('Wrong benchmark timing/reference/alternation')
        observed[index]=value
    if set(observed)!=set(range(240)):raise RuntimeError('Missing benchmark frames')
    return [observed[index][0] for index in range(240)]

def summary(values):
    ordered=sorted(values)
    return {'frames':len(values),'median_us':statistics.median(values),
            'mean_us':statistics.mean(values),'p95_us':ordered[math.ceil(.95*len(values))-1],
            'minimum_us':ordered[0],'maximum_us':ordered[-1]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    collector=module('collector',ROOT/'tools/collect-waffle-ui-evidence.py')
    runner=module('runner',ROOT/'scripts/run_waffle_ios.py')
    paths=sorted((x for x in args.run.glob('kernel-*.log') if re.fullmatch(r'kernel-\d+\.log',x.name)),key=lambda x:int(x.stem.split('-')[1]))
    if not paths and (args.run/'kernel-final.log').is_file():paths=[args.run/'kernel-final.log']
    text,sources=collector.collect(paths);values=frames(text)
    checked=runner.extract_gl_pixels(text);fences=runner.gl_completed_fences(text)
    if len(checked)!=256 or fences<240 or 'GENERAL close passed=1' not in text:
        raise RuntimeError('Actual GPU drawing/final reference/cleanup missing')
    proof_error=None
    try:runner.validate_gl_log(text)
    except RuntimeError as error:proof_error=str(error)
    report={'run':str(args.run),'actual_hook_inverted':False,'total_reference_pixels':292320000,
            'final_reference_pixels':256,'GPU_fences':fences,'all_completion_tokens_verified':True,
            'strict_GL_proof_passed':proof_error is None,'strict_GL_proof_error':proof_error,
            'all_frames':summary(values),'after_40_warmup_frames':summary(values[40:]),
            'render_and_readback_us':values,'profile_modes_observed':sorted(set(re.findall(r'waffle-gl-readback: pid=1 mode=(\w+)',text))),
            'panel_FPS_measured':False,'CPU_reference_outside_timing':True,
            'limitation':'Fixed offscreen triangle/alternating clear; no claim of UI or panel FPS. Profile output inside hook is equal across policies.',
            'raw_snapshots':sources,'evidence_sha256':hashlib.sha256(text.encode()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('raw_snapshots','render_and_readback_us')},indent=2))

if __name__=='__main__':main()
