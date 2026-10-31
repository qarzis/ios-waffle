#!/usr/bin/env python3
"""Capture native cold CP startup with the port's optional features disabled."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/waffle/gpu'
ADB='/home/qarzis/platform-tools/adb'
KNOBS=('dms','lpac','preemption','gpu_llc_slice_enable','gpuhtw_llc_slice_enable','ifpc')
KGSL='/sys/class/kgsl/kgsl-3d0'
GROUP='waffle_minimal_audit'

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
probes=[
 f'p:{GROUP}/start msm_kgsl:gen7_start '+ ' '.join(f'{name}=+{offset}(%x0):u8' for name,offset in fields.items() if name!='pwrup_reglist'),
 f'p:{GROUP}/ucode msm_kgsl:gen7_start sqe_va=+24(+6472(%x0)):x64 aqe_va=+24(+6504(%x0)):x64 sqe_size=+6456(%x0):u64 aqe_size=+6488(%x0):u64 sqe=+0(+8(+6472(%x0))):x32[16] aqe=+0(+8(+6504(%x0))):x32[16]',
 f'p:{GROUP}/regions msm_kgsl:gen7_hwsched_cp_init offset0=+5392(%x0):u32 size0=+5396(%x0):u32 offset1=+5424(%x0):u32 size1=+5428(%x0):u32 offset2=+5456(%x0):u32 size2=+5460(%x0):u32 offset3=+5488(%x0):u32 size3=+5492(%x0):u32',
 f'p:{GROUP}/precp msm_kgsl:gen7_hwsched_cp_init r3c03=+61452(+5384(%x0)):x32 r3c04=+61456(+5384(%x0)):x32 r3c05=+61460(+5384(%x0)):x32 r3c06=+61464(+5384(%x0)):x32 r11=+68(+5384(%x0)):x32 r8e28=+145568(+5384(%x0)):x32 r1f841=+90372(+5416(%x0)):x32 r3c00=+61440(+5384(%x0)):x32 r808=+8224(+5384(%x0)):x32 r830=+8384(+5384(%x0)):x32 r831=+8388(+5384(%x0)):x32 rb70=+11712(+5384(%x0)):x32 rb71=+11716(+5384(%x0)):x32 rf800=+253952(+5384(%x0)):x32 rf801=+253956(+5384(%x0)):x32 rf802=+253960(+5384(%x0)):x32 rf803=+253964(+5384(%x0)):x32 rf400=+249856(+5384(%x0)):x32 r800=+8192(+5384(%x0)):x32 r801=+8196(+5384(%x0)):x32 r802=+8200(+5384(%x0)):x32 r803=+8204(+5384(%x0)):x32 r804=+8208(+5384(%x0)):x32 r805=+8212(+5384(%x0)):x32 r806=+8216(+5384(%x0)):x32 r807=+8220(+5384(%x0)):x32',
 f'p:{GROUP}/contexts msm_kgsl:kgsl_iommu_start user_cb=+80(%x0):s32 secure_cb=+344(%x0):s32 lpac_cb=+608(%x0):s32',
 f'r:{GROUP}/cp_done msm_kgsl:gen7_hwsched_cp_init ret=$retval:s32',
 f'p:{GROUP}/hfi msm_kgsl:gen7_hfi_cmdq_write bytes=%x2:u32 id=+0(%x1):u8 '+
 ' '.join(f'w{i}=+{4*i}(%x1):x32' for i in range(11))+
 ' pwrup0=+0(+8(+12744(%x0))):x32[63] pwrup1=+252(+8(+12744(%x0))):x32[63] pwrup2=+504(+8(+12744(%x0))):x32[28]',
 f'p:{GROUP}/write msm_kgsl:kgsl_regmap_write offset=%x2:u32 value=%x1:x32',
]
initial=states()
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=BASE/'android-live-audit-20261029';out.mkdir(exist_ok=True)
path=out/f'ring-state-native-{stamp}.trace'
restore='\n'.join(f"printf '%s\\n' {initial[k]} > {KGSL}/{k} || true" for k in reversed(KNOBS))
script=r'''set -eu
trace_root=/sys/kernel/tracing
instance=$trace_root/instances/waffle_minimal_audit
test ! -e "$instance"
test ! -e "$trace_root/events/waffle_minimal_audit"
cleanup() {
 echo 0 > "$instance/tracing_on" 2>/dev/null || true
 RESTORE
 if test -d "$instance"; then
  for event in start cp_done hfi write ucode regions precp contexts; do
   if test -e "$instance/events/waffle_minimal_audit/$event/enable"; then
    echo 0 > "$instance/events/waffle_minimal_audit/$event/enable" || true
   fi
  done
  rmdir "$instance" || true
 fi
 for event in start cp_done hfi write ucode regions precp contexts; do
  printf '%s\n' "-:waffle_minimal_audit/$event" >> "$trace_root/kprobe_events" || true
 done
 echo TRACE_CLEANUP_DONE
}
trap cleanup EXIT
mkdir "$instance"
echo 512 > "$instance/buffer_size_kb"
REGISTRATION
printf '%s\n' 'id == 11 || id == 14 || id == 10 || id == 131 || id == 122 || id == 13' > "$instance/events/waffle_minimal_audit/hfi/filter"
for event in start cp_done hfi write ucode regions precp contexts; do echo 1 > "$instance/events/waffle_minimal_audit/$event/enable"; done
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
'''.replace('RESTORE',restore).replace('REGISTRATION','\n'.join("printf '%s\\n' "+shlex.quote(p)+' >> "$trace_root/kprobe_events"' for p in probes)).replace('APPLY','\n'.join(f'echo 0 > {KGSL}/{k}' for k in KNOBS)).replace('VERIFY','\n'.join(f'test "$(cat {KGSL}/{k})" = 0' for k in KNOBS))
report={'initial':initial,'probes':probes,'layout_sha256':hashlib.sha256(layout.read_bytes()).hexdigest(),'source_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
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
report['window_native_raw_count']=len(re.findall(r': hfi:.*bytes=44 id=131\b',window))
report['trace_sha256']=hashlib.sha256(output.encode()).hexdigest()
path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'trace':str(path.relative_to(ROOT)),**report},indent=2))
if error:print(error)
raise SystemExit(0 if report.get('returncode')==0 and report['cleanup_seen'] and report['restoration_matches'] else 1)
