#!/usr/bin/env python3
"""Build an isolated PosterBoard layer diagnostic from the last working UI kit."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-kit',type=Path,default=ROOT/'work/waffle/posterboard/client-gl-kit')
    parser.add_argument('--output',type=Path,default=ROOT/'work/waffle/posterboard/layers-diagnostic')
    parser.add_argument('--enable-duetexpertd',action='store_true',
        help='Include the stock FaceSuggestions provider as an on-demand job')
    parser.add_argument('--enable-mobileassetd',action='store_true',
        help='Include the stock MobileAsset provider required by duetexpertd')
    parser.add_argument('--no-diagnostics',action='store_true',
        help='Build the normal UI library without observers or the sampling job')
    args=parser.parse_args()
    if args.enable_mobileassetd and not args.enable_duetexpertd:
        parser.error('--enable-mobileassetd requires --enable-duetexpertd')
    allowed=(['duetexpertd'] if args.enable_duetexpertd else []) + (['mobileassetd'] if args.enable_mobileassetd else [])
    base=args.base_kit.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    theos=Path(os.environ.get('THEOS',Path.home()/'theos'))
    if not (theos/'sdks').is_dir():theos=ROOT/'work/theos'
    sdk=theos/'sdks/iPhoneOS16.5.sdk'
    if not sdk.is_dir():raise SystemExit('Missing iOS16.5 SDK')
    subprocess.run(['bash','-c',r'''
set -e
source tools/xnu-env.sh
compile=(xnu-clang -arch arm64 -isysroot "$2" -O1 -Wall -Wextra)
diagnostics=()
if [ "$3" = 1 ]; then diagnostics=(-DWAFFLE_POSTER_DIAGNOSTICS=1); fi
"${compile[@]}" "${diagnostics[@]}" -dynamiclib -install_name /redwood/lib/libredwood-sb.dylib \
 -framework CoreFoundation -framework IOKit -lobjc -framework Foundation \
 -framework UIKit -framework QuartzCore -framework CoreGraphics \
 -o "$1/libredwood-sb.dylib" userland/src/inject_sb.c userland/src/inject_island.m \
 userland/src/inject_poster.m userland/src/inject_settings.m
if [ "$3" = 1 ]; then "${compile[@]}" -o "$1/poster_diag" userland/src/poster_diag.c; fi
''','poster-build',str(out),str(sdk),'0' if args.no_diagnostics else '1'],cwd=ROOT,check=True)
    job=plistlib.dumps({'Label':'com.redwood.poster.layers',
        'ProgramArguments':['/redwood/bin/poster_diag','--layers'],
        'RunAtLoad':True,'StandardOutPath':'/dev/console','StandardErrorPath':'/dev/console'})
    changes={'lib/libredwood-sb.dylib':((out/'libredwood-sb.dylib').read_bytes(),0o755)}
    if not args.no_diagnostics:
        changes.update({'bin/poster_diag':((out/'poster_diag').read_bytes(),0o755),
            'LaunchDaemons/com.redwood.poster.layers.plist':(job,0o644)})
    kit=out/'kit';kit.mkdir(exist_ok=True)
    with tarfile.open(base/'root-base.tar') as src,tarfile.open(kit/'root-base.tar','w',format=tarfile.PAX_FORMAT) as dst:
        for member in src:
            if str(Path(member.name)) in changes:continue
            if args.no_diagnostics and str(Path(member.name)) in (
                    'bin/poster_diag','LaunchDaemons/com.redwood.poster.layers.plist'):continue
            dst.addfile(member,src.extractfile(member) if member.isfile() else None)
        for name,(data,mode) in changes.items():
            info=tarfile.TarInfo('./'+name);info.size=len(data);info.mode=mode;info.mtime=int(time.time())
            dst.addfile(info,io.BytesIO(data))
    overlay=kit/'system-overlay.tar'
    if not overlay.exists():overlay.symlink_to(base/'system-overlay.tar')
    images=out/'images'
    subprocess.run([sys.executable,str(ROOT/'tools/assemble.py'),'--kit',str(kit),
        '--out',str(images),'--only','root'],cwd=ROOT,env=os.environ|{
            'OSLOG':'com.apple.PosterBoard com.apple.duetexpertd com.apple.mobileassetd',
            'ALLOW':' '.join(allowed)},check=True)
    with tarfile.open(kit/'root-base.tar') as archive:
        injection=archive.extractfile('./etc/inject.conf').read()
    manifest={'base_kit':str(base),'test':'Normal UI; no diagnostic observers' if args.no_diagnostics else 'Three read-only scene/layer snapshots at30/90/180seconds',
        'diagnostics':not args.no_diagnostics,
        'on_demand_allow':allowed,
        'changes':{name:hashlib.sha256(data).hexdigest() for name,(data,_) in changes.items()},
        'root_sha256':hashlib.sha256((images/'root.packfs').read_bytes()).hexdigest(),
        'inject_conf_sha256':hashlib.sha256(injection).hexdigest(),'hardware_tested':False}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PosterBoard diagnostic:',images/'root.packfs')

if __name__=='__main__':main()
