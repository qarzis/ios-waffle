#!/usr/bin/env python3
"""Capture CPU-resident SMMU metadata; --describe never contacts a phone."""
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
GROUP='waffle_smmu_meta'

def android(script,timeout=15):
    return subprocess.run([ADB,'-s','1c62e9aa','exec-out',shlex.join(['su','-c',script])],
                          capture_output=True,text=True,timeout=timeout)

def states():
    p=android('\n'.join(f"printf '{k}='; cat {KGSL}/{k}" for k in KNOBS))
    if p.returncode:raise RuntimeError(p.stderr)
    result={k:v for k,v in re.findall(r'^([a-z_]+)=([01])$',p.stdout,re.M)}
    if set(result)!=set(KNOBS):raise RuntimeError('Incomplete native knob snapshot')
    return result

layout=BASE/'android-live-audit-20261026/driver-layout.json'
m=json.loads(layout.read_text())['adreno_device']['members']
fields={'dms_enabled':12720,'lpac_enabled':12719,'gpu_llc_slice_enable':13176,'gpuhtw_llc_slice_enable':13192,'pwrup_reglist':12744}
for name,offset in fields.items():assert m[name]['offset_bits']==offset*8
# adreno_device embeds kgsl_device at0; kgsl_mmu at56, inline iommu at64;
# iommu regbase at792 =>912, cb0_offset at852 =>972, pagesize at856=>976.
assert any(v['offset_bits']==56*8 for v in json.loads(layout.read_text())['kgsl_device']['members'].values())
assert json.loads(layout.read_text())['kgsl_iommu']['members']['cb0_offset']['offset_bits']==852*8
probes=[
 f'p:{GROUP}/meta msm_kgsl:gen7_hwsched_cp_init base=+912(%x0):x64 cb0=+972(%x0):x32 page=+976(%x0):u32 user_cb=+136(%x0):s32',
 f'r:{GROUP}/cp_done msm_kgsl:gen7_hwsched_cp_init ret=$retval:s32',
]
def analyze(output):
    window = output.split('MINIMAL_WINDOW_BEGIN', 1)[-1].split('MINIMAL_WINDOW_END', 1)[0] if 'MINIMAL_WINDOW_BEGIN' in output and 'MINIMAL_WINDOW_END' in output else ''
    rows = [dict(base=int(base,16), cb0=int(cb0,16), page=int(page), user_cb=int(cb))
            for base,cb0,page,cb in re.findall(r': meta:.*?base=(0x[0-9a-f]+) cb0=(0x[0-9a-f]+) page=(\d+) user_cb=(-?\d+)',window)]
    successes = len(re.findall(r': cp_done:.*ret=0\b',window))
    failures = re.findall(r': cp_done:.*ret=(-?[1-9]\d*)\b',window)
    valid = bool(rows and all(r['base'] and r['cb0']==0x20000 and r['page']==4096 and r['user_cb']==0 for r in rows))
    return {'metadata':rows, 'metadata_geometry_valid':valid, 'window_cp_successes':successes,
            'window_cp_failures':failures, 'capture_complete':'TRACE_CAPTURE_COMPLETE' in output,
            'cleanup_seen':'TRACE_CLEANUP_DONE' in output,
            'evidence_valid':bool(valid and successes and not failures and 'TRACE_CAPTURE_COMPLETE' in output and 'TRACE_CLEANUP_DONE' in output)}

def main():
    if sys.argv[1:] == ['--describe']:
        print(json.dumps({'probes':probes, 'reads':'CPU metadata only; no SMMU MMIO reads', 'hardware_contacted':False},indent=2))
        return
    if len(sys.argv)==3 and sys.argv[1]=='--analyze':
        result=analyze(Path(sys.argv[2]).read_text())
        print(json.dumps(result,indent=2))
        raise SystemExit(0 if result['evidence_valid'] else 1)
    contexts_mode=sys.argv[1:]==['--contexts']
    routing_mode=sys.argv[1:] in (['--routing'],['--contexts'])
    register_mode=sys.argv[1:] in (['--registers'],['--routing'],['--contexts'])
    if sys.argv[1:] and not register_mode:
        raise SystemExit('Use no arguments for metadata, --registers after validated metadata, --describe or --analyze TRACE offline')
    capture_probes=list(probes)
    if register_mode:
        reports=sorted((BASE/'android-live-audit-20261030').glob('smmu-meta-native-*.json'))
        validated=[json.loads(p.read_text()) for p in reports if not p.name.endswith('.initial.json')]
        if not any(r.get('passed') and r.get('metadata_geometry_valid') for r in validated):
            raise SystemExit('Need successful metadata-only capture first')
        offsets={'sctlr':0,'actlr':4,'tcr2':0x10,'ttbr0':0x20,'ttbr1':0x28,'tcr':0x30,'contextidr':0x34,'mair0':0x38,'mair1':0x3c}
        fields=' '.join(f'{name}=+{0x20000+off}(+912(%x0)):'+('x64' if name.startswith('ttbr') else 'x32') for name,off in offsets.items())
        if routing_mode:
            routing={'cbar0':0x1000,'cba2r0':0x1800}
            routing.update({f'smr{i}':0x800+i*4 for i in range(6)})
            routing.update({f's2cr{i}':0xc00+i*4 for i in range(6)})
            fields+=' '+' '.join(f'{name}=+{off}(+912(%x0)):x32' for name,off in routing.items())
            offsets.update(routing)
        if contexts_mode:
            # CB2/CB3 standard register windows fit the BTF/DT-validated
            # 4KB-bank, 0x40000-byte NS register mapping. No table-memory reads.
            extra={}
            for bank in (2,3):
                for name,off in {'sctlr':0,'actlr':4,'tcr2':0x10,'ttbr0':0x20,'ttbr1':0x28,'tcr':0x30,'contextidr':0x34,'mair0':0x38,'mair1':0x3c}.items():
                    extra[f'c{bank}_{name}']=0x20000+bank*4096+off
                extra[f'cbar{bank}']=0x1000+bank*4
                extra[f'cba2r{bank}']=0x1800+bank*4
            assert all(off+8<=0x40000 for off in extra.values())
            fields+=' '+' '.join(f'{name}=+{off}(+912(%x0)):'+('x64' if 'ttbr' in name else 'x32') for name,off in extra.items())
            offsets.update(extra)
        capture_probes.append(f'p:{GROUP}/cb msm_kgsl:gen7_hwsched_cp_init '+fields)
    events=' '.join(p.split('/',1)[1].split()[0] for p in capture_probes)
    initial=states()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=BASE/'android-live-audit-20261030';out.mkdir(exist_ok=True)
    path=out/f"smmu-{'contexts' if contexts_mode else 'routing' if routing_mode else 'registers' if register_mode else 'meta'}-native-{stamp}.trace"
    restore='\n'.join(f"printf '%s\\n' {initial[k]} > {KGSL}/{k} || true" for k in reversed(KNOBS))
    script=r'''set -eu
    trace_root=/sys/kernel/tracing
    instance=$trace_root/instances/waffle_smmu_meta
    test ! -e "$instance"
    test ! -e "$trace_root/events/waffle_smmu_meta"
    cleanup() {
     capture_status=$?
     trap - EXIT
     echo 0 > "$instance/tracing_on" 2>/dev/null || true
     RESTORE
     if test -d "$instance"; then
      for event in EVENTS; do
       if test -e "$instance/events/waffle_smmu_meta/$event/enable"; then
        echo 0 > "$instance/events/waffle_smmu_meta/$event/enable" || true
       fi
      done
      rmdir "$instance" || true
     fi
     for event in EVENTS; do
      printf '%s\n' "-:waffle_smmu_meta/$event" >> "$trace_root/kprobe_events" || true
     done
     echo TRACE_CLEANUP_DONE
     exit "$capture_status"
    }
    trap cleanup EXIT
    mkdir "$instance"
    echo 512 > "$instance/buffer_size_kb"
    REGISTRATION
    for event in EVENTS; do echo 1 > "$instance/events/waffle_smmu_meta/$event/enable"; done
    echo 1 > "$instance/tracing_on"
    APPLY
    VERIFY
    echo MINIMAL_WINDOW_BEGIN > "$instance/trace_marker"
    input keyevent KEYCODE_WAKEUP
    input keyevent KEYCODE_HOME
    sleep 5
    echo MINIMAL_WINDOW_END > "$instance/trace_marker"
    echo 0 > "$instance/tracing_on"
    cat "$instance/trace"
    echo TRACE_CAPTURE_COMPLETE
    '''.replace('RESTORE',restore).replace('REGISTRATION','\n'.join("printf '%s\\n' "+shlex.quote(p)+' >> "$trace_root/kprobe_events"' for p in capture_probes)).replace('EVENTS',events).replace('APPLY','\n'.join(f'echo 0 > {KGSL}/{k}' for k in KNOBS)).replace('VERIFY','\n'.join(f'test "$(cat {KGSL}/{k})" = 0' for k in KNOBS))
    report={'register_mode':register_mode,'initial':initial,'probes':capture_probes,'layout_sha256':hashlib.sha256(layout.read_bytes()).hexdigest(),'source_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
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
    path.write_text(output);path.with_suffix('.stderr').write_text(error)
    window=output.split('MINIMAL_WINDOW_BEGIN',1)[-1].split('MINIMAL_WINDOW_END',1)[0] if 'MINIMAL_WINDOW_BEGIN' in output and 'MINIMAL_WINDOW_END' in output else ''
    report['cleanup_seen']='TRACE_CLEANUP_DONE' in output
    report['window_cp_successes']=len(re.findall(r': cp_done:.*ret=0\b',window))
    report.update(analyze(output))
    if register_mode:
        rows=[]
        for line in window.splitlines():
            if ': cb:' not in line: continue
            row={name:int(value,16) for name,value in re.findall(r'\b('+ '|'.join(offsets) +r')=(0x[0-9a-f]+)',line)}
            rows.append(row)
        report['context_registers']=rows
        report['evidence_valid']=report['evidence_valid'] and bool(rows) and all(set(row)==set(offsets) for row in rows)
    report['passed']=bool(report.get('returncode')==0 and report.get('host_restore_exit')==0 and report['restoration_matches'] and report['evidence_valid'])
    report['trace_sha256']=hashlib.sha256(output.encode()).hexdigest()
    path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'trace':str(path.relative_to(ROOT)),**report},indent=2))
    if error:print(error)
    raise SystemExit(0 if report['passed'] else 1)

if __name__ == "__main__":
    main()
