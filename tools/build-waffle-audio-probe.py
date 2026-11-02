#!/usr/bin/env python3
"""Build a static PID1 and private firmware-only RAM root for adsp=3."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mkpackfs as pf
import importlib.util


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('audio_check', ROOT/'tools/check-waffle-audio.py')
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    audit = check.audit(args.dtb, args.firmware, ROOT/'kernel/files/bsd/dev/macan_adsp.c')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(ROOT/'xnu-deps/host/bin')+':'+os.environ['PATH'], XNU_SDK_VERSION='16.5')
    cc = [str(ROOT/'xnu-deps/host/bin/xnu-clang'), '-arch','arm64','-Os','-static','-nostdlib',
          '-ffreestanding','-fno-stack-protector','-fno-builtin','-Wall','-Wextra',
          '-isysroot',str(ROOT/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),'-I',str(ROOT/'userland/libmini')]
    for name in ('mini.c','start.S'):
        subprocess.run(cc+['-c',str(ROOT/'userland/libmini'/name),'-o',str(out/(name+'.o'))],env=env,check=True)
    binary = out/'waffle-audio-probe'
    subprocess.run(cc+['-Wl,-e,_start','-Wl,-pagezero_size,0x100000000',
        str(ROOT/'userland/src/waffle_audio_probe.c'),str(out/'mini.c.o'),str(out/'start.S.o'),'-o',str(binary)],env=env,check=True)
    tree = pf.Node(b'',0o40755,0)
    pf.node_at(tree,'dev',create=True)
    pf.add_file(tree,'sbin/launchd',str(binary),mode=0o100755)
    for name, image in audit['images'].items():
        pf.add_file(tree,'fw/'+name+'.mdt',str(args.firmware/(name+'.mdt')))
        for segment in image['segments']:
            if segment['file_size']:
                filename=f"{name}.b{segment['index']:02d}"
                pf.add_file(tree,'fw/'+filename,str(args.firmware/filename))
    pf.pack(tree,str(out/'root.packfs'),block=4096,page=16384)
    pf.pack(pf.Node(b'',0o40755,0),str(out/'system.packfs'),block=4096,page=16384)
    sources=['userland/src/waffle_audio_probe.c','userland/libmini/mini.c','userland/libmini/mini.h',
        'userland/libmini/start.S','kernel/files/bsd/dev/macan_adsp.c','kernel/files/bsd/dev/macan_input.c','kernel/files/bsd/sys/waffle_adsp_power.h','kernel/files/bsd/sys/waffle_adsp_rpmh.h','loader/waffle.h',
        'tools/build-waffle-audio-probe.py','tools/check-waffle-audio.py','tools/run-waffle-auto.py','scripts/run_waffle_ios.py']
    manifest={'mode':'adsp=3 firmware-only','hardware_DSP_startup':False,
        'root_sha256':hashlib.sha256((out/'root.packfs').read_bytes()).hexdigest(),
        'system_sha256':hashlib.sha256((out/'system.packfs').read_bytes()).hexdigest(),
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},'preflight':audit}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Audio firmware root bytes:',(out/'root.packfs').stat().st_size)


if __name__=='__main__':
    main()
