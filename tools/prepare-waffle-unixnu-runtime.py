#!/usr/bin/env python3
"""Bind the offline runtime root to a freshly built kernel. No USB operations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    manifest = json.loads((artifact/'manifest.json').read_text())
    runtime = ROOT/'work/waffle/unixnu-build/runtime-root'
    probe = json.loads((runtime/'manifest.json').read_text())
    assert sha(runtime/'root.packfs') == probe['root_sha256']
    for name, digest in probe['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    names = [
        'iokit/Kernel/WaffleNativeGPU.cpp', 'iokit/Kernel/WaffleGPUMap.cpp',
        'iokit/Kernel/WaffleGPUMemory.cpp', 'bsd/dev/waffle_gpu_drm.c',
        'bsd/dev/waffle_smmu.c', 'bsd/dev/waffle_gpu_service.c',
        'bsd/dev/waffle_adreno.c', 'bsd/sys/waffle_gpu_memory.h',
        'bsd/sys/waffle_gpu_reclaim.h', 'bsd/sys/waffle_gpu_iokit.h',
        'bsd/sys/waffle_unixnu_gpu.h', 'bsd/sys/waffle_gpu_service.h',
        'bsd/sys/waffle_smmu.h', 'bsd/sys/waffle_gpu_msm.h',
    ]
    bindings = {}
    for name in names:
        relative = 'kernel/files/'+name
        digest = sha(ROOT/relative)
        assert sha(artifact/'source'/relative) == digest, relative+' snapshot stale'
        assert sha(ROOT/'xnu-src/xnu-8796.121.2'/name) == digest, relative+' prepared source stale'
        bindings[relative] = digest
    name = 'loader/waffle.h'
    assert sha(ROOT/name) == sha(artifact/'source'/name), 'Loader snapshot stale'
    bindings[name] = sha(ROOT/name)
    assert sha(artifact/'kernel') == manifest['kernel_sha256']
    boot = artifact/'HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img'
    assert sha(boot) == manifest['boot_image_sha256']
    shutil.copy2(boot, artifact/'HakiOS-waffle-PJD110-AUTO-RAM.img')
    shutil.copytree(runtime, artifact/'gl-probe', dirs_exist_ok=True)
    manifest.update(
        experiment='U05 complete runtime/Turnip IOKit GPU fill; no Metal frontend',
        automatic_usb_loader=False, hardware_tested=False,
        gl_context=True, unixnu_runtime_probe=True, unixnu_query_test=False,
        gl_probe_root_sha256=probe['root_sha256'],
        gl_system_sha256=sha(ROOT/'work/waffle/images/system.packfs'),
        unixnu_source_sha256=bindings,
        Metal_frontend=False, CPU_fallback=False,
    )
    (artifact/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('PASS: fresh kernel/source/loader bindings, runtime root and RAM boot image; no USB')


if __name__ == '__main__':
    main()
