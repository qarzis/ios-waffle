#!/usr/bin/env python3
"""Capture native clock/regulator requests and CP timing; offline analysis available.

Voltage arguments for these ARC supplies are abstract levels, not physical uV.
Absence of an outgoing ARC command does not mean the consumer made no vote:
the native regulator framework aggregates votes shared with other consumers.
"""
from pathlib import Path
import datetime
import hashlib
import json
import re
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/waffle/gpu'
ADB='/home/qarzis/platform-tools/adb'
KNOBS=('dms','lpac','preemption','gpu_llc_slice_enable','gpuhtw_llc_slice_enable','ifpc')
KGSL='/sys/class/kgsl/kgsl-3d0'
GROUP='waffle_power_audit'

def android(script,timeout=15):
    return subprocess.run([ADB,'-s','1c62e9aa','exec-out',shlex.join(['su','-c',script])],
                          capture_output=True,text=True,timeout=timeout)

def states():
    p=android('\n'.join(f"printf '{k}='; cat {KGSL}/{k}" for k in KNOBS))
    if p.returncode:raise RuntimeError(p.stderr)
    result={k:v for k,v in re.findall(r'^([a-z_]+)=([01])$',p.stdout,re.M)}
    if set(result)!=set(KNOBS):raise RuntimeError('Incomplete native knob snapshot')
    return result

btf=(BASE/'android-live-audit-20261026/vmlinux-btf.txt').read_text()
for struct_name, member, bit_offset in [('regulator','dev',0),('regulator','supply_name',640),('device','kobj',0),('kobject','name',0)]:
    block=re.search(r"STRUCT '"+struct_name+r"' .*?(?=\n\[)",btf,re.S)[0]
    assert re.search(r"'"+member+r"'.*bits_offset="+str(bit_offset)+r"\b",block)
probes=[
 f'p:{GROUP}/rate msm_kgsl:kgsl_clk_set_rate name=+0(%x2):string hz=%x3:u64',
 f'r:{GROUP}/rate_done msm_kgsl:kgsl_clk_set_rate ret=$retval:s32',
 f'p:{GROUP}/rpmh qcom_rpmh:rpmh_write state=%x1:u32 n=%x3:u32 addr=+0(%x2):x32 data=+4(%x2):x32 wait=+8(%x2):u32',
 f'r:{GROUP}/rpmh_done qcom_rpmh:rpmh_write ret=$retval:s32',
 f'p:{GROUP}/async qcom_rpmh:rpmh_write_async state=%x1:u32 n=%x3:u32 addr=+0(%x2):x32 data=+4(%x2):x32 wait=+8(%x2):u32',
 f'r:{GROUP}/async_done qcom_rpmh:rpmh_write_async ret=$retval:s32',
 f'p:{GROUP}/voltage regulator_set_voltage consumer=+0(+0(+0(%x0))):string supply=+0(+80(%x0)):string min=%x1:s32 max=%x2:s32',
 f'r:{GROUP}/voltage_done regulator_set_voltage ret=$retval:s32',
 f'p:{GROUP}/cp msm_kgsl:gen7_hwsched_cp_init',
 f'r:{GROUP}/cp_done msm_kgsl:gen7_hwsched_cp_init ret=$retval:s32',
]

def analyze(output):
    if 'MINIMAL_WINDOW_BEGIN' not in output or 'MINIMAL_WINDOW_END' not in output:
        return {'evidence_valid':False,'reason':'Incomplete capture window'}
    window=output.split('MINIMAL_WINDOW_BEGIN',1)[1].split('MINIMAL_WINDOW_END',1)[0]
    pending={}
    completed=[]
    cp_clocks=[]
    unmatched=[]
    for line in window.splitlines():
        m=re.search(r'-(\d+)\s+\[\d+\].*?\s(\d+\.\d+): (rate|rate_done|voltage|voltage_done|cp|cp_done): (.*)',line)
        if not m:continue
        pid,stamp,event,detail=m.groups()
        stamp=float(stamp)
        kind=event.removesuffix('_done')
        key=(pid,kind)
        if event.endswith('_done'):
            stack=pending.get(key,[])
            if not stack:
                unmatched.append(line);continue
            entry=stack.pop()
            ret=re.search(r'\bret=(-?\d+)\b',detail)
            entry.update(return_time=stamp,ret=int(ret[1]) if ret else None)
            completed.append(entry)
        else:
            entry={'pid':pid,'kind':kind,'time':stamp,'detail':detail}
            if kind=='rate':
                rate=re.search(r'name="([^"]+)" hz=(\d+)',detail)
                if rate:entry.update(name=rate[1],hz=int(rate[2]))
            if kind=='voltage':
                voltage=re.search(r'consumer="([^"]+)" supply="([^"]+)" min=(-?\d+) max=(-?\d+)',detail)
                if voltage:entry.update(consumer=voltage[1],supply=voltage[2],minimum=int(voltage[3]),maximum=int(voltage[4]))
            if kind=='cp':
                previous=[c for c in completed if c['pid']==pid and c['kind']=='rate' and c.get('name')=='gmu_clk' and c['ret']==0]
                cp_clocks.append({'pid':pid,'time':stamp,'last_gmu_rate_Hz':previous[-1].get('hz') if previous else None})
            pending.setdefault(key,[]).append(entry)
    rates=[c for c in completed if c['kind']=='rate']
    gpu_voltages=[c for c in completed if c['kind']=='voltage' and c.get('consumer')=='3d90000.clock-controller']
    failures=[c for c in completed if c.get('ret')!=0]
    unfinished=sum(len(stack) for stack in pending.values())
    expected_rates=all(any(c.get('name')==name and c.get('hz')==hz and c['ret']==0 for c in rates) for name,hz in (('gmu_clk',625000000),('gmu_clk',260000000),('hub_clk',200000000)))
    expected_votes=all(any(c.get('supply','').endswith(suffix) and c.get('minimum')==level and c['ret']==0 for c in gpu_voltages) for suffix,level in (('-vdd_cx',128),('-vdd_mx',192)))
    cp_successes=sum(c['kind']=='cp' and c['ret']==0 for c in completed)
    valid=bool(expected_rates and expected_votes and cp_successes and not failures and not unfinished and not unmatched)
    return {'evidence_valid':valid,'completed_clock_requests':rates,'completed_gpu_voltage_requests':gpu_voltages,'cp_entry_clocks':cp_clocks,'paired_cp_successes':cp_successes,'call_failures':failures,'unfinished_calls':unfinished,'unmatched_returns':unmatched}

def main():
    if sys.argv[1:]==['--describe']:
        print(json.dumps({'probes':probes,'reads':'CPU clock names and first tcs_cmd only; no MMIO','hardware_contacted':False},indent=2));return
    if len(sys.argv)==3 and sys.argv[1]=='--analyze':
        result=analyze(Path(sys.argv[2]).read_text());print(json.dumps(result,indent=2));raise SystemExit(0 if result['evidence_valid'] else 1)
    if sys.argv[1:]:raise SystemExit('Use --describe/--analyze TRACE offline or no arguments to capture')
    capture_probes=probes
    events=' '.join(p.split('/',1)[1].split()[0] for p in probes)
    initial=states()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=BASE/'android-live-audit-20261030';out.mkdir(exist_ok=True)
    path=out/f'power-native-{stamp}.trace'
    restore='\n'.join(f"printf '%s\\n' {initial[k]} > {KGSL}/{k} || true" for k in reversed(KNOBS))
    script=r'''set -eu
    trace_root=/sys/kernel/tracing
    instance=$trace_root/instances/waffle_power_audit
    test ! -e "$instance"
    test ! -e "$trace_root/events/waffle_power_audit"
    cleanup() {
     capture_status=$?
     trap - EXIT
     echo 0 > "$instance/tracing_on" 2>/dev/null || true
     RESTORE
     if test -d "$instance"; then
      for event in EVENTS; do
       if test -e "$instance/events/waffle_power_audit/$event/enable"; then
        echo 0 > "$instance/events/waffle_power_audit/$event/enable" || true
       fi
      done
      rmdir "$instance" || true
     fi
     for event in EVENTS; do
      printf '%s\n' "-:waffle_power_audit/$event" >> "$trace_root/kprobe_events" || true
     done
     echo TRACE_CLEANUP_DONE
     exit "$capture_status"
    }
    trap cleanup EXIT
    mkdir "$instance"
    echo 512 > "$instance/buffer_size_kb"
    REGISTRATION
    for event in EVENTS; do echo 1 > "$instance/events/waffle_power_audit/$event/enable"; done
    echo 1 > "$instance/tracing_on"
    echo MINIMAL_WINDOW_BEGIN > "$instance/trace_marker"
    APPLY
    VERIFY
    input keyevent KEYCODE_WAKEUP
    input keyevent KEYCODE_HOME
    sleep 5
    echo MINIMAL_WINDOW_END > "$instance/trace_marker"
    echo 0 > "$instance/tracing_on"
    cat "$instance/trace"
    echo TRACE_CAPTURE_COMPLETE
    '''.replace('RESTORE',restore).replace('REGISTRATION','\n'.join("printf '%s\\n' "+shlex.quote(p)+' >> "$trace_root/kprobe_events"' for p in capture_probes)).replace('EVENTS',events).replace('APPLY','\n'.join(f'echo 0 > {KGSL}/{k}' for k in KNOBS)).replace('VERIFY','\n'.join(f'test "$(cat {KGSL}/{k})" = 0' for k in KNOBS))
    report={'initial':initial,'probes':capture_probes,'source_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path.with_suffix('.initial.json').write_text(json.dumps(report,indent=2)+'\n')
    try:
        p=android(script,45)
        output,error=p.stdout,p.stderr
        report['returncode']=p.returncode
    except subprocess.TimeoutExpired as e:
        output=e.stdout or b'';error=e.stderr or b''
        if isinstance(output,bytes):output=output.decode(errors='replace')
        if isinstance(error,bytes):error=error.decode(errors='replace')
        report['timeout']=True
    finally:
        # A second connection restores known original values even if the trace shell
        # was interrupted. Normal completion uses its EXIT trap first.
        recovery=android(restore,30)
        report['host_restore_exit']=recovery.returncode
        report['restored']=states()
        report['restoration_matches']=report['restored']==initial
        cleanup=android('test ! -d /sys/kernel/tracing/instances/waffle_power_audit && test ! -d /sys/kernel/tracing/events/waffle_power_audit')
        report['host_cleanup_exit']=cleanup.returncode
    path.write_text(output);path.with_suffix('.stderr').write_text(error)
    window=output.split('MINIMAL_WINDOW_BEGIN',1)[-1].split('MINIMAL_WINDOW_END',1)[0] if 'MINIMAL_WINDOW_BEGIN' in output and 'MINIMAL_WINDOW_END' in output else ''
    report['cleanup_seen']='TRACE_CLEANUP_DONE' in output
    report['window_cp_successes']=len(re.findall(r': cp_done:.*ret=0\b',window))
    report['clock_requests']=[line for line in window.splitlines() if ': rate:' in line or ': rate_done:' in line]
    report['arc_requests']=[line for line in window.splitlines() if (': rpmh:' in line or ': async:' in line) and re.search(r'addr=0x300[01]0\b',line)]
    report['gpu_voltage_requests']=[line for line in window.splitlines() if ': voltage:' in line and '3d90000.clock-controller' in line]
    report.update(analyze(output))
    report['passed']=bool(report.get('returncode')==0 and report.get('host_restore_exit')==0 and report.get('host_cleanup_exit')==0 and report['restoration_matches'] and report['cleanup_seen'] and 'TRACE_CAPTURE_COMPLETE' in output and report['evidence_valid'])
    report['trace_sha256']=hashlib.sha256(output.encode()).hexdigest()
    path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'trace':str(path.relative_to(ROOT)),**report},indent=2))
    if error:print(error)
    raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
