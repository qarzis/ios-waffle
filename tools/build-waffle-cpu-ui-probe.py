#!/usr/bin/env python3
"""Build an isolated softpipe UI root with a delayed CPU concurrency probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import assemble
import mkpackfs as pf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hud-probe', action='store_true', help='Read-only SpringBoard geometry audit and bounded synthetic volume presses')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / 'scratch'
    scratch.mkdir(exist_ok=True)
    sdk = ROOT / 'work/theos/sdks/iPhoneOS16.5.sdk'
    env = os.environ | {'PATH': str(ROOT / 'xnu-deps/host/bin') + ':' + os.environ['PATH'], 'XNU_SDK_VERSION': '16.5', 'ALLOW': 'duetexpertd mobileassetd'}
    cc = str(ROOT / 'xnu-deps/host/bin/xnu-clang')

    def run(command):
        subprocess.run(command, cwd=ROOT, env=env, check=True)

    cpu = out / 'cpu_test'
    run([cc, '-arch', 'arm64', '-isysroot', str(sdk), '-O2', '-Wall', '-Wextra',
         str(ROOT / 'userland/src/cpu_test.c'), '-o', str(cpu)])
    inject = out / 'libredwood.dylib'
    run([cc, '-arch', 'arm64', '-isysroot', str(sdk), '-O1', '-Wall', '-Wextra',
         *(['-DWAFFLE_VOLUME_HUD_PROBE=1'] if args.hud_probe else []),
         '-dynamiclib', '-install_name', '/redwood/lib/libredwood.dylib',
         '-framework', 'CoreFoundation', '-framework', 'IOKit', '-lobjc',
         str(ROOT / 'userland/src/inject.c'), '-o', str(inject)])
    base=ROOT / 'work/waffle/posterboard/fixed/kit/root-base.tar'
    tree = pf.scan_tar(str(base), str(scratch / 'base'))
    pf.add_file(tree, 'bin/cpu_test', str(cpu), mode=0o100755)
    pf.add_file(tree, 'lib/libredwood.dylib', str(inject), mode=0o100755)
    ours = pf.node_at(tree, 'etc/var.skel.redwood')
    skel = scratch / 'var.skel'
    skel.write_text(assemble.var_skel(Path(ours.source).read_text() if ours else ''))
    pf.remove(tree, 'etc/var.skel.redwood')
    pf.add_file(tree, 'etc/var.skel', str(skel))
    jobs = scratch / 'jobs'
    run([sys.executable, str(ROOT / 'userland/mkjobs.py'), '--rest', str(ROOT / 'ios165/rootfs'), str(jobs), *assemble.JOBS])
    job = {'Label': 'org.waffle.cpu-proof', 'ProgramArguments': ['/redwood/bin/cpu_test', '35'],
           'RunAtLoad': True, 'KeepAlive': False, 'StandardOutPath': '/dev/console', 'StandardErrorPath': '/dev/console'}
    (jobs / 'org.waffle.cpu-proof.plist').write_bytes(plistlib.dumps(job))
    if args.hud_probe:
        helper=out/'libwaffle-hud-probe.dylib'
        run([cc,'-arch','arm64','-isysroot',str(sdk),'-O1','-Wall','-Wextra','-fobjc-arc','-dynamiclib',
             '-framework','UIKit','-framework','Foundation','-framework','CoreFoundation','-lMobileGestalt',
             str(ROOT/'userland/src/waffle_hud_probe.m'),'-o',str(helper)])
        pf.add_file(tree,'lib/libwaffle-hud-probe.dylib',str(helper),mode=0o100755)
        sb=jobs/'com.apple.SpringBoard.plist'
        job=plistlib.loads(sb.read_bytes());environment=job.setdefault('EnvironmentVariables',{})
        libraries=environment.get('DYLD_INSERT_LIBRARIES','')
        environment['DYLD_INSERT_LIBRARIES']=':'.join(filter(None,(libraries,'/redwood/lib/libwaffle-hud-probe.dylib')))
        sb.write_bytes(plistlib.dumps(job))
    for path in sorted(jobs.iterdir()):
        pf.add_file(tree, 'LaunchDaemons/' + path.name, str(path))
    root = out / 'root.packfs'
    pf.pack(tree, str(root), zstd=15)
    assert root.stat().st_size + 16 * 1024 * 1024 < 0x03f00000
    sources = ['tools/build-waffle-cpu-ui-probe.py', 'userland/src/cpu_test.c', 'userland/src/inject.c', 'userland/mkjobs.py', 'tools/assemble.py']
    if args.hud_probe: sources.append('userland/src/waffle_hud_probe.m')
    manifest = {'RAM_only': True, 'GPU_enabled': False, 'hardware_tested': False,
                'cpu_probe_delay_seconds': 35, 'root_sha256': hashlib.sha256(root.read_bytes()).hexdigest(),
                'posterboard_base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
                'posterboard_providers': ['duetexpertd','mobileassetd'], 'hud_probe':args.hud_probe,
                'source_sha256': {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
