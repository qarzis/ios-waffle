#!/usr/bin/env python3
"""Bounded native LLCC-off control via KGSL's reversible power-cycle knobs."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import shlex
import subprocess

root=Path(__file__).resolve().parents[1]
base=root/'work/waffle/gpu'
layout=base/'android-live-audit-20261026/driver-layout.json'
m=json.loads(layout.read_text())['adreno_device']['members']
assert m['gpu_llc_slice_enable']['offset_bits']==13176*8
assert m['gpuhtw_llc_slice_enable']['offset_bits']==13192*8
probes=[
 'p:waffle_llcc_off/start msm_kgsl:gen7_start gpu_enable=+13176(%x0):u8 htw_enable=+13192(%x0):u8',
 'r:waffle_llcc_off/cp_done msm_kgsl:gen7_hwsched_cp_init ret=$retval:s32',
 'p:waffle_llcc_off/reg_write msm_kgsl:kgsl_regmap_write offset=%x2:u32 value=%x1:x32',
]
script=r'''set -eu
trace_root=/sys/kernel/tracing
instance=$trace_root/instances/waffle_llcc_off
kgsl=/sys/class/kgsl/kgsl-3d0
test ! -e "$instance"
test ! -e "$trace_root/events/waffle_llcc_off"
gpu_initial=$(cat "$kgsl/gpu_llc_slice_enable")
htw_initial=$(cat "$kgsl/gpuhtw_llc_slice_enable")
case "$gpu_initial/$htw_initial" in 0/0|0/1|1/0|1/1) ;; *) exit 2;; esac
cleanup() {
 echo 0 > "$instance/tracing_on" 2>/dev/null || true
 printf '%s\n' "$gpu_initial" > "$kgsl/gpu_llc_slice_enable" || true
 printf '%s\n' "$htw_initial" > "$kgsl/gpuhtw_llc_slice_enable" || true
 echo RESTORED_GPU=$(cat "$kgsl/gpu_llc_slice_enable")
 echo RESTORED_HTW=$(cat "$kgsl/gpuhtw_llc_slice_enable")
 if test -d "$instance"; then
  for event in start cp_done reg_write; do
   if test -e "$instance/events/waffle_llcc_off/$event/enable"; then
    echo 0 > "$instance/events/waffle_llcc_off/$event/enable" || true
   fi
  done
  rmdir "$instance" || true
 fi
 for event in start cp_done reg_write; do
  printf '%s\n' "-:waffle_llcc_off/$event" >> "$trace_root/kprobe_events" || true
 done
 echo TRACE_CLEANUP_DONE
}
trap cleanup EXIT
echo INITIAL_GPU=$gpu_initial
echo INITIAL_HTW=$htw_initial
mkdir "$instance"
echo 128 > "$instance/buffer_size_kb"
REGISTRATION
printf '%s\n' 'offset == 15361 || offset == 15362' > "$instance/events/waffle_llcc_off/reg_write/filter"
for event in start cp_done reg_write; do echo 1 > "$instance/events/waffle_llcc_off/$event/enable"; done
echo 1 > "$instance/tracing_on"
echo 0 > "$kgsl/gpu_llc_slice_enable"
echo 0 > "$kgsl/gpuhtw_llc_slice_enable"
test "$(cat "$kgsl/gpu_llc_slice_enable")" = 0
test "$(cat "$kgsl/gpuhtw_llc_slice_enable")" = 0
echo OFF_WINDOW_BEGIN > "$instance/trace_marker"
input keyevent KEYCODE_WAKEUP
input keyevent KEYCODE_HOME
sleep 5
echo OFF_WINDOW_END > "$instance/trace_marker"
echo 0 > "$instance/tracing_on"
cat "$instance/trace"
'''.replace('REGISTRATION','\n'.join("printf '%s\\n' "+shlex.quote(p)+' >> "$trace_root/kprobe_events"' for p in probes))
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'android-live-audit-20261029';out.mkdir(exist_ok=True)
p=subprocess.run(['/home/qarzis/platform-tools/adb','-s','1c62e9aa','exec-out',shlex.join(['su','-c',script])],capture_output=True,text=True,timeout=45)
path=out/f'llcc-off-{stamp}.trace';path.write_text(p.stdout);path.with_suffix('.stderr').write_text(p.stderr)
window=p.stdout.split('OFF_WINDOW_BEGIN',1)[-1].split('OFF_WINDOW_END',1)[0] if 'OFF_WINDOW_BEGIN' in p.stdout and 'OFF_WINDOW_END' in p.stdout else ''
initial=re.findall(r'INITIAL_(GPU|HTW)=([01])',p.stdout)
restored=re.findall(r'RESTORED_(GPU|HTW)=([01])',p.stdout)
report={'returncode':p.returncode,'cleanup_seen':'TRACE_CLEANUP_DONE' in p.stdout,
        'initial':dict(initial),'restored':dict(restored),'restoration_matches':len(initial)==2 and dict(initial)==dict(restored),
        'off_window_starts':len(re.findall(r': start:.*gpu_enable=0 htw_enable=0',window)),
        'off_window_cp_successes':len(re.findall(r': cp_done:.*ret=0\b',window)),
        'off_window_scid_writes':len(re.findall(r': reg_write:',window)),
        'trace_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'probes':probes}
path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'trace':str(path.relative_to(root)),**report},indent=2))
if p.stderr:print(p.stderr)
raise SystemExit(0 if p.returncode==0 and report['cleanup_seen'] and report['restoration_matches'] else 1)
