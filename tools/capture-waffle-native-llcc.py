#!/usr/bin/env python3
"""Read native LLCC enable flags through a private bounded Android trace."""
from pathlib import Path
import datetime
import hashlib
import json
import shlex
import subprocess

root=Path(__file__).resolve().parents[1]
base=root/'work/waffle/gpu'
layout=base/'android-live-audit-20261026/driver-layout.json'
members=json.loads(layout.read_text())['adreno_device']['members']
fields={'gpu_llc_slice_enable':13176,'gpuhtw_llc_slice_enable':13192}
for name,offset in fields.items():
    assert members[name]['offset_bits']==offset*8
probe='p:waffle_llcc_audit/start msm_kgsl:gen7_start '+ ' '.join(
    f'{name}=+{offset}(%x0):u8' for name,offset in fields.items())
script=r'''set -eu
trace_root=/sys/kernel/tracing
instance=$trace_root/instances/waffle_llcc_audit
test ! -e "$instance"
test ! -e "$trace_root/events/waffle_llcc_audit"
cleanup() {
 if test -d "$instance"; then
  echo 0 > "$instance/tracing_on" || true
  if test -e "$instance/events/waffle_llcc_audit/start/enable"; then
   echo 0 > "$instance/events/waffle_llcc_audit/start/enable" || true
  fi
  rmdir "$instance" || true
 fi
 printf '%s\n' '-:waffle_llcc_audit/start' >> "$trace_root/kprobe_events" || true
 echo TRACE_CLEANUP_DONE
}
trap cleanup EXIT
mkdir "$instance"
echo 64 > "$instance/buffer_size_kb"
printf '%s\n' PROBE >> "$trace_root/kprobe_events"
echo 1 > "$instance/events/waffle_llcc_audit/start/enable"
echo 1 > "$instance/tracing_on"
input keyevent KEYCODE_WAKEUP
input keyevent KEYCODE_HOME
sleep 5
echo 0 > "$instance/tracing_on"
cat "$instance/trace"
'''.replace('PROBE',shlex.quote(probe))
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'android-live-audit-20261029';out.mkdir(exist_ok=True)
p=subprocess.run(['/home/qarzis/platform-tools/adb','-s','1c62e9aa','exec-out',
                  shlex.join(['su','-c',script])],capture_output=True,text=True,timeout=35)
path=out/f'llcc-native-{stamp}.trace';path.write_text(p.stdout)
path.with_suffix('.stderr').write_text(p.stderr)
report={'returncode':p.returncode,'cleanup_seen':'TRACE_CLEANUP_DONE' in p.stdout,
        'gpu_knob_changes':False,'layout_sha256':hashlib.sha256(layout.read_bytes()).hexdigest(),
        'trace_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'probe':probe}
path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'trace':str(path.relative_to(root)),**report},indent=2))
for line in p.stdout.splitlines():
    if ': start:' in line:print(line)
if p.stderr:print(p.stderr)
raise SystemExit(0 if p.returncode==0 and report['cleanup_seen'] else 1)
