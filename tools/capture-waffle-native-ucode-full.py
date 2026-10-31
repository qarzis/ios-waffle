#!/usr/bin/env python3
"""Read complete native SQE/AQE CPU buffers during bounded Android CP startup.

Uses BTF-checked pointers and file-derived lengths. No MMIO reads or writes.
Optional GPU knobs are restored by both the device EXIT trap and the host.
"""
from pathlib import Path
import datetime
import hashlib
import json
import re
import shlex
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work/waffle/gpu'
ADB = '/home/qarzis/platform-tools/adb'
GROUP = 'waffle_full_ucode'
KGSL = '/sys/class/kgsl/kgsl-3d0'
KNOBS = ('dms', 'lpac', 'preemption', 'gpu_llc_slice_enable', 'gpuhtw_llc_slice_enable', 'ifpc')

def android(script, timeout=20):
    return subprocess.run([ADB, '-s', '1c62e9aa', 'exec-out', shlex.join(['su', '-c', script])], capture_output=True, text=True, timeout=timeout)

def states():
    p = android('\n'.join(f"printf '{k}='; cat {KGSL}/{k}" for k in KNOBS))
    p.check_returncode()
    values = dict(re.findall(r'^([a-z_]+)=([01])$', p.stdout, re.M))
    if set(values) != set(KNOBS):
        raise RuntimeError('Incomplete optional-knob snapshot')
    return values

def main():
    layout_path = BASE / 'android-live-audit-20261026/driver-layout.json'
    members = json.loads(layout_path.read_text())['adreno_device']['members']
    # Offsets used by the previously validated native-ucode capture.
    assert any(v['offset_bits'] == 6448 * 8 for v in members.values())
    layout = json.loads(layout_path.read_text())
    assert layout['adreno_firmware']['bytes'] == 32
    assert layout['adreno_firmware']['members']['memdesc']['offset_bits'] == 24 * 8
    assert layout['kgsl_memdesc']['members']['hostptr']['offset_bits'] == 8 * 8
    probes = []
    specs = {}
    expected = {}
    for name, pointer, length in (('sqe', 6472, 6456), ('aqe', 6504, 6488)):
        payload = (BASE / f'android-capture2/gen70900_{name}.fw').read_bytes()[4:]
        assert len(payload) % 4 == 0
        expected[name] = payload
        words = len(payload) // 4
        for start in range(0, words, 4 * 63):
            event = f'{name}_{start}'
            fields = []
            chunks = []
            for index, off in enumerate(range(start, min(words, start + 4 * 63), 63)):
                count = min(63, words - off)
                fields.append(f'd{index}=+{off*4}(+8(+{pointer}(%x0))):x32[{count}]')
                chunks.append((f'd{index}', off * 4, count))
            assert sum(n * 4 for _, _, n in chunks) <= 1008
            assert sum(n * 11 for _, _, n in chunks) + 256 < 4096
            probes.append(f'p:{GROUP}/{event} msm_kgsl:gen7_start n=+{length}(%x0):u64 ' + ' '.join(fields))
            specs[event] = (name, words, chunks)
    probes.append(f'r:{GROUP}/cp_done msm_kgsl:gen7_hwsched_cp_init ret=$retval:s32')
    events = list(specs) + ['cp_done']
    initial = states()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = BASE / 'android-live-audit-20261030'
    out.mkdir(exist_ok=True)
    path = out / f'ucode-full-native-{stamp}.trace'
    restore = '\n'.join(f'echo {initial[k]} > {KGSL}/{k}' for k in reversed(KNOBS))
    script = '''set -eu
root=/sys/kernel/tracing
instance=$root/instances/waffle_full_ucode
test ! -e "$instance"
test ! -e "$root/events/waffle_full_ucode"
cleanup() {
 echo 0 > "$instance/tracing_on" 2>/dev/null || true
 RESTORE
 for event in EVENTS; do
  test ! -e "$instance/events/waffle_full_ucode/$event/enable" || echo 0 > "$instance/events/waffle_full_ucode/$event/enable"
 done
 rmdir "$instance" || true
 for event in EVENTS; do echo "-:waffle_full_ucode/$event" >> "$root/kprobe_events" || true; done
 echo TRACE_CLEANUP_DONE
}
trap cleanup EXIT
mkdir "$instance"
echo 4096 > "$instance/buffer_size_kb"
REGISTER
for event in EVENTS; do echo 1 > "$instance/events/waffle_full_ucode/$event/enable"; done
echo 1 > "$instance/tracing_on"
APPLY
VERIFY
echo FULL_WINDOW_BEGIN > "$instance/trace_marker"
input keyevent KEYCODE_WAKEUP
input keyevent KEYCODE_HOME
sleep 5
echo FULL_WINDOW_END > "$instance/trace_marker"
echo 0 > "$instance/tracing_on"
cat "$instance/trace"
'''.replace('RESTORE', restore).replace('EVENTS', ' '.join(events)).replace('REGISTER', '\n'.join("printf '%s\\n' " + shlex.quote(p) + ' >> "$root/kprobe_events"' for p in probes)).replace('APPLY', '\n'.join(f'echo 0 > {KGSL}/{k}' for k in KNOBS)).replace('VERIFY', '\n'.join(f'test "$(cat {KGSL}/{k})" = 0' for k in KNOBS))
    report = {'initial': initial, 'probes': probes, 'layout_sha256': hashlib.sha256(layout_path.read_bytes()).hexdigest(), 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path.with_suffix('.initial.json').write_text(json.dumps(report, indent=2) + '\n')
    output = ''
    error = ''
    try:
        p = android(script, 60)
        output, error = p.stdout, p.stderr
        report['returncode'] = p.returncode
    except subprocess.TimeoutExpired as exc:
        output, error = exc.stdout or b'', exc.stderr or b''
        if isinstance(output, bytes): output = output.decode(errors='replace')
        if isinstance(error, bytes): error = error.decode(errors='replace')
        report['timeout'] = True
    finally:
        recovery = android(restore, 30)
        report['host_restore_exit'] = recovery.returncode
        report['restored'] = states()
        report['restoration_matches'] = report['restored'] == initial
        path.write_text(output)
        path.with_suffix('.stderr').write_text(error)
    window = output.split('FULL_WINDOW_BEGIN', 1)[-1].split('FULL_WINDOW_END', 1)[0] if 'FULL_WINDOW_BEGIN' in output and 'FULL_WINDOW_END' in output else ''
    pending = {}
    completed = []
    errors = []
    for line in window.splitlines():
        match = re.search(r': ((?:sqe|aqe)_\d+):.*\bn=(\d+) ', line)
        if not match: continue
        event, count = match.groups()
        name, words, chunks = specs[event]
        if int(count) != words:
            errors.append(f'{event}: descriptor length mismatch')
            continue
        pid = re.search(r'-(\d+)\s+\[', line)
        if not pid:
            errors.append(f'{event}: task PID missing')
            continue
        key = (pid[1], name)
        pieces = pending.setdefault(key, {})
        for field, off, size in chunks:
            data = re.search(r'\b' + field + r'=\{([^}]+)\}', line)
            values = re.findall(r'0x[0-9a-fA-F]+', data[1]) if data else []
            if len(values) != size:
                errors.append(f'{event}/{field}: unreadable or truncated array')
                continue
            if off in pieces:
                errors.append(f'{event}/{field}: duplicate chunk before complete capture')
            pieces[off] = struct.pack('<' + 'I' * size, *(int(v, 16) for v in values))
        if sum(map(len, pieces.values())) == len(expected[name]):
            payload = b''.join(pieces[off] for off in sorted(pieces))
            completed.append({'kind': name, 'pid': pid[1], 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(), 'matches_port_payload': payload == expected[name]})
            pending[key] = {}
    report.update(trace=str(path.relative_to(ROOT)), trace_sha256=hashlib.sha256(output.encode()).hexdigest(), cleanup_seen='TRACE_CLEANUP_DONE' in output, window_cp_successes=len(re.findall(r': cp_done:.*ret=0\b', window)), completed=completed, parse_errors=errors, incomplete_chunks=sum(len(v) for v in pending.values()))
    report['passed'] = bool(report.get('returncode') == 0 and report['cleanup_seen'] and report['restoration_matches'] and not errors and report['window_cp_successes'] and all(any(c['kind'] == name and c['matches_port_payload'] for c in completed) for name in expected) and all(c['matches_port_payload'] for c in completed))
    path.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'probes'}, indent=2))
    if error: print(error)
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
