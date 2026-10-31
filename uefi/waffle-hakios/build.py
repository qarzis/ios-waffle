#!/usr/bin/env python3
"""Adapt HakiOS to an existing verified waffle Mu tree; no device operations."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mu-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.mu_source.resolve(), args.output.resolve()
    here = Path(__file__).resolve().parent
    required = ('Platforms/OnePlus/wafflePkg/waffle.dsc',
                'Platforms/OnePlus/wafflePkg/Applications/XnuRamLoader/loader-waffle.efi',
                'Resources/Configs/waffle.toml', 'Resources/DTBs/waffle.dtb')
    if output.exists() or source == output or source in output.parents:
        parser.error('Use a new output directory outside the input tree')
    for name in required:
        if not (source / name).is_file():
            parser.error(f'Missing prepared waffle input: {name}')
    subprocess.run(['git', 'apply', '--check', '--ignore-space-change',
                    str(here / 'integration.patch')], cwd=source, check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(output)], check=True)
    subprocess.run(['git', 'apply', '--ignore-space-change',
                    str(here / 'integration.patch')], cwd=output, check=True)
    subprocess.run([sys.executable, str(here / 'banner.py'),
                    str(output / 'Silicon/Silicium/SiliciumPkg/Include/Resources')], check=True)
    subprocess.run([sys.executable, 'build_uefi.py', '-d', 'waffle', '-r', 'DEBUG'],
                   cwd=output, check=True)
    print(output / 'Mu-waffle.img')


if __name__ == '__main__':
    main()
