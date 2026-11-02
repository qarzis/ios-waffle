#!/usr/bin/env python3
"""Inspect USB; explicitly collect small Sahara crash segments only in900e mode.

No programmer, Firehose, flash operations or Android reboot is sent. Upstream
qdl ramdump resets the target AFTER collecting, so Android may restart then.
This path is not yet hardware validated on this PJD110.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import time
from waffle_ramlogs import create_manifest

ROOT = Path(__file__).resolve().parents[1]
QDL = ROOT / 'work/waffle/gpu/qdl-source/build/qdl'
PROVENANCE = ROOT / 'work/waffle/gpu/qdl-provenance.json'
SERIAL = '1c62e9aa'
# Exact stems actually offered by this PJD110; no whole DDR dump.
LEGACY_SEGMENTS = ['OCIMEM', 'CODERAM', 'MSGRAM', 'ocimem', 'coderam', 'msgram']
DIAGNOSTIC_SEGMENTS = ['md_TZ_DIAG', 'md_HYP_DIAG', 'md_MDMP_LOG', 'md_XBL_LOG',
                       'md_UEFI_LOG', 'md_RST_STAT', 'md_SHRDIMEM', 'md_PMIC_PON',
                       'md_SMEMINFO', 'md_DATARAM', 'md_CODERAM']
SEGMENTS = ','.join(LEGACY_SEGMENTS + DIAGNOSTIC_SEGMENTS +
                    [f'md_MSGRAM{i}' for i in range(16)])


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def devices(base=Path('/sys/bus/usb/devices')):
    return [dict(path=str(p), vid=read(p / 'idVendor').lower(),
                 pid=read(p / 'idProduct').lower(), serial=read(p / 'serial'),
                 product=read(p / 'product'))
            for p in sorted(base.iterdir()) if (p / 'idVendor').is_file()]


def eligible(entries):
    qualcomm = [d for d in entries if d['vid'] == '05c6']
    if len(qualcomm) != 1:
        return None
    device = qualcomm[0]
    if device['pid'] != '900e' or SERIAL not in (device['serial'] + ' ' + device['product']).lower():
        return None
    return device


def command(device, output, qdl=QDL):
    args = [str(qdl), 'ramdump', '--backend', 'usb', '--debug', '-o', str(output)]
    # qdl's USB backend selects the _SN: token from iProduct, not iSerial.
    # Qualcomm exposes a DIFFERENT random-looking iSerial in900e mode.
    match = re.search(r'_SN:([^ _]+)', device['product'])
    if not match or match.group(1).lower() != SERIAL:
        raise ValueError('qdl requires matching PJD110 _SN: token in iProduct')
    args += ['--serial', match.group(1)]
    return args + [SEGMENTS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true', help='Read offered crash segments, then qdl sends reset')
    parser.add_argument('--wait-seconds', type=int, choices=range(181), default=30,
                        help='Bounded wait for delayed900e re-enumeration after a crash')
    parser.add_argument('--ramlog-run', type=Path, help='Experimental: read five owned RAM-log pages from latest run')
    parser.add_argument('--ramlog-kernel', type=Path, help='Kernel must match staged payload and artifact manifest')
    args = parser.parse_args()
    if bool(args.ramlog_run) != bool(args.ramlog_kernel):
        parser.error('Both RAM-log run and kernel are required')
    visible = devices()
    device = eligible(visible)
    deadline = time.monotonic() + args.wait_seconds
    while args.collect and device is None and time.monotonic() < deadline:
        time.sleep(0.25)
        visible = devices()
        device = eligible(visible)
    print(json.dumps({'eligible_pjd110_900e': device, 'usb_devices': visible}, indent=2))
    if not args.collect:
        return 0
    if device is None:
        parser.error('Expected exactly one Qualcomm device: this PJD110 in05c6:900e. No device commands sent.')
    path = Path(device['path'])
    bus, number = read(path / 'busnum'), read(path / 'devnum')
    if not bus.isdigit() or not number.isdigit():
        parser.error('Cannot resolve the crash USB node; no device commands sent.')
    node = Path(f'/dev/bus/usb/{int(bus):03d}/{int(number):03d}')
    if not os.access(node, os.R_OK | os.W_OK):
        parser.error(f'Linux denies access to {node}. Grant this user a temporary ACL; no device commands sent.')
    expected = json.loads(PROVENANCE.read_text())['binary_sha256']
    if hashlib.sha256(QDL.read_bytes()).hexdigest() != expected:
        parser.error('Pinned qdl binary does not match provenance; no device commands sent.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'work/waffle/gpu/crashdumps' / stamp
    output.mkdir(parents=True, exist_ok=False)
    capture_command = command(device, output)
    ramlog_report = None
    if args.ramlog_run:
        runs = ROOT / 'work/waffle/runs'
        latest = max(p for p in runs.iterdir() if p.is_dir())
        if args.ramlog_run.resolve() != latest.resolve():
            parser.error('RAM-log capture requires the latest run; no device commands sent')
        ramlog_binary = ROOT / 'work/waffle/gpu/ramlog-client/waffle-sahara-ramlogs'
        ramlog_provenance = json.loads(ramlog_binary.with_name('provenance.json').read_text())
        if hashlib.sha256(ramlog_binary.read_bytes()).hexdigest() != ramlog_provenance['sha256'][str(ramlog_binary.relative_to(ROOT))]:
            parser.error('RAM-log client differs from provenance; no device commands sent')
        try:
            ramlog_report = create_manifest(args.ramlog_run, args.ramlog_kernel, output / 'ramlogs.manifest', 59)
        except (OSError, ValueError) as error:
            parser.error(f'{error}; no device commands sent')
        capture_command = [str(ramlog_binary), str(output / 'ramlogs.manifest'), str(output / 'pages')]
    report = {'device': device, 'command': capture_command, 'flash_operations': False,
              'qdl_resets_after_dump': True, 'hardware_validated_on_pjd110': False}
    if ramlog_report:
        report['ramlog_manifest'] = ramlog_report
        report['experimental_ramlogs'] = True
    try:
        with (output / 'transport.log').open('w') as log:
            result = subprocess.run(report['command'], stdout=log, stderr=subprocess.STDOUT, timeout=60)
        report['exit_code'] = result.returncode
    except subprocess.TimeoutExpired:
        report['timeout'] = True
    finally:
        report['segments'] = {str(p.relative_to(output)): {'bytes': p.stat().st_size,
                                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                              for p in (output.rglob('*.bin') if ramlog_report else output.iterdir()) if p.is_file() and p.name != 'transport.log'}
        (output / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
    if ramlog_report:
        expected_names = {'pages/waffle_hfi0.bin'} | {f'pages/waffle_gmu{i}.bin' for i in range(4)}
        report['read_complete'] = (set(report['segments']) == expected_names and
                                   all(p['bytes'] == 16384 for p in report['segments'].values()))
        # Keep the protocol endpoint and reset evidence, not just process status.
        lines = (output / 'transport.log').read_text(errors='replace').splitlines()
        for line in reversed(lines):
            try:
                client = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(client, dict) and 'reset_sent' in client and 'pages' in client:
                report['client_result'] = client
                break
        (output / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'output': str(output), **report}, indent=2))
        return 0 if report.get('exit_code') == 0 and report['read_complete'] else 1
    print(json.dumps({'output': str(output), **report}, indent=2))
    return 0 if report.get('exit_code') == 0 and report['segments'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
