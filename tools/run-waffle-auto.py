#!/usr/bin/env python3
"""RAM boot the automatic waffle loader and run a bounded GPU diagnostic.

Never flashes. Optional standard Sahara collection uses the existing pinned
collector, which resets after collecting offered crash segments.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--prepare-gpu', action='store_true', help='Run existing probe93; no RAW')
    parser.add_argument('--access-matrix', action='store_true', help='Add existing E03 checks to probe93')
    parser.add_argument('--measure-clocks', action='store_true', help='Measure clocks on prepare-only probe93')
    parser.add_argument('--lpac-cp-init',action='store_true',help='E08 only: CP_INIT94 with validated LPAC mapping; may enter900e')
    parser.add_argument('--compute',choices=('prepare','dispatch'),help='E21 bounded shader state/control or dispatch; requires --dynamic-bo')
    parser.add_argument('--dynamic-bo',action='store_true',help='E20: post-bootstrap test BO; requires --session')
    parser.add_argument('--session',action='store_true',help='E12 bounded owned session: requires --ib and entire verified chain')
    parser.add_argument('--ib',action='store_true',help='E11: GPU indirect command-buffer fetch; requires --writeback')
    parser.add_argument('--writeback',action='store_true',help='E10: dedicated GPU memory write after verified ZAP; requires --zap')
    parser.add_argument('--zap',action='store_true',help='E09: PAS13 authenticated load and native secure switch after CP_INIT')
    parser.add_argument('--lpac-map',action='store_true',help='Validate LPAC mappings on probe93, or controlled94 with --lpac-cp-init')
    parser.add_argument('--fastboot', default=str(ROOT.parent / 'platform-tools/fastboot'))
    parser.add_argument('--adb', default=str(ROOT.parent / 'platform-tools/adb'))
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    image = artifact / 'HakiOS-waffle-PJD110-AUTO-RAM.img'
    if args.access_matrix and not args.prepare_gpu:
        parser.error('--access-matrix requires --prepare-gpu')
    if args.measure_clocks and not args.prepare_gpu:
        parser.error('--measure-clocks requires --prepare-gpu')
    if args.lpac_cp_init and (not args.lpac_map or args.prepare_gpu):
        parser.error('--lpac-cp-init requires --lpac-map and excludes --prepare-gpu')
    if args.lpac_map and not (args.prepare_gpu or args.lpac_cp_init):
        parser.error('--lpac-map requires --prepare-gpu or controlled --lpac-cp-init')
    if args.zap and not args.lpac_cp_init:
        parser.error('--zap requires controlled --lpac-cp-init --lpac-map')
    if args.writeback and not args.zap:
        parser.error('--writeback requires --zap')
    if args.ib and not args.writeback:
        parser.error('--ib requires --writeback')
    if args.compute and not args.dynamic_bo:
        parser.error('--compute requires --dynamic-bo')
    if args.dynamic_bo and not args.session:
        parser.error('--dynamic-bo requires --session')
    if args.session and not args.ib:
        parser.error('--session requires --ib')
    manifest = json.loads((artifact / 'manifest.json').read_text())
    if not manifest.get('automatic_usb_loader'):
        parser.error('Artifact does not declare automatic loader entry')
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest['boot_image_sha256']:
        parser.error('Boot image does not match manifest')
    for name in ('adb', 'fastboot'):
        if not Path(getattr(args, name)).is_file():
            parser.error(f'Missing {name}')
    if args.prepare_gpu or args.lpac_cp_init:
        # The existing session runner pins these transport paths.
        if Path(args.adb).resolve() != (ROOT.parent / 'platform-tools/adb').resolve() or \
                Path(args.fastboot).resolve() != (ROOT.parent / 'platform-tools/fastboot').resolve():
            parser.error('Prepare runner requires the standard workspace platform-tools')
        if hashlib.sha256((artifact / 'kernel').read_bytes()).hexdigest() != manifest['kernel_sha256']:
            parser.error('Kernel does not match manifest')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'work/waffle/auto-runs' / stamp
    output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': stamp, 'flash_operations': False, 'gpu_raw': args.lpac_cp_init,
              'prepare_gpu': args.prepare_gpu, 'access_matrix': args.access_matrix,
              'measure_clocks': args.measure_clocks, 'lpac_map':args.lpac_map, 'lpac_cp_init':args.lpac_cp_init, 'zap':args.zap, 'writeback':args.writeback, 'ib':args.ib, 'session':args.session, 'dynamic_bo':args.dynamic_bo, 'compute':args.compute,
              'physical_boot_selection': False, 'android_confirmed': False}

    def command(items, timeout=10):
        result = subprocess.run(items, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        with (output / 'host.log').open('a') as log:
            log.write(' '.join(map(str, items)) + '\n' + result.stdout + result.stderr + '\n')
        return result

    def wait_for(check, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if check():
                return True
            time.sleep(1)
        return False

    def android_ready():
        p = command([args.adb, '-s', '1c62e9aa', 'shell', 'getprop', 'sys.boot_completed'])
        return p.returncode == 0 and p.stdout.strip() == '1'

    def fastboot_has(serial):
        p = command([args.fastboot, 'devices'])
        return any(line.split()[:1] == [serial] for line in p.stdout.splitlines())

    collector = None
    recovery_log = None
    try:
        if android_ready():
            p = command([args.adb, '-s', '1c62e9aa', 'reboot', 'bootloader'])
            if p.returncode:
                raise RuntimeError('Android refused reboot to bootloader')
        if not wait_for(lambda: fastboot_has('1c62e9aa'), 60):
            raise RuntimeError('Expected PJD110 Android fastboot; no RAM boot sent')
        p = command([args.fastboot, '-s', '1c62e9aa', 'boot', str(image)], timeout=30)
        if p.returncode:
            raise RuntimeError('RAM boot rejected')
        if not wait_for(lambda: fastboot_has('xnuloader'), 60):
            raise RuntimeError('Automatic loader did not enumerate')
        p = command([args.fastboot, '-s', 'xnuloader', 'getvar', 'platform'])
        if p.returncode or 'platform: waffle' not in p.stdout + p.stderr:
            raise RuntimeError('Automatic loader platform mismatch')
        report['automatic_loader_verified'] = True
        if args.prepare_gpu or args.lpac_cp_init:
            recovery_log = (output / 'recovery.log').open('w')
            collector = subprocess.Popen([sys.executable, 'tools/capture-waffle-crash.py',
                '--collect', '--wait-seconds', '60'], cwd=ROOT,
                stdout=recovery_log, stderr=subprocess.STDOUT)
            items = [sys.executable, 'work/waffle/gpu/run-publish-test.py', '94' if args.lpac_cp_init else '93', str(artifact)]
            if args.access_matrix:
                items.append('--access-matrix')
            if args.measure_clocks:
                items.append('--measure-clocks')
            if args.lpac_map:
                items.append('--lpac-map')
            if args.zap:
                items.append('--zap')
            if args.writeback:
                items.append('--writeback')
            if args.ib:
                items.append('--ib')
            if args.session:
                items.append('--session')
            if args.dynamic_bo:
                items.append('--dynamic-bo')
            if args.compute:
                items.append('--compute-'+args.compute)
            result = command(items, timeout=240)
            report['runner_exit'] = result.returncode
            if result.returncode:
                raise RuntimeError('GPU test failed; preserve original result and inspect recovery log')
        else:
            p = command([args.fastboot, '-s', 'xnuloader', 'reboot'])
            if p.returncode:
                raise RuntimeError('Loader refused Android reboot')
        if not wait_for(android_ready, 90):
            raise RuntimeError('Android recovery not confirmed; stop before another experiment')
        report['android_confirmed'] = True
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        report['success'] = False
        # Try normal loader reboot without hiding the failed experiment.
        try:
            if fastboot_has('xnuloader'):
                command([args.fastboot, '-s', 'xnuloader', 'reboot'])
            report['android_confirmed'] = wait_for(android_ready, 60)
        except Exception as recovery_error:
            report['recovery_error'] = str(recovery_error)
    finally:
        if collector:
            if collector.poll() is None and report['android_confirmed']:
                collector.terminate()
            try:
                collector.wait(timeout=65)
            except subprocess.TimeoutExpired:
                collector.terminate()
                report['collector_timeout'] = True
        if recovery_log:
            recovery_log.close()
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(output), **report}, indent=2))
    return 0 if report.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
