#!/usr/bin/env python3
"""Build pinned UniXNU graphics userspace for ARM64/iOS16.5; never use USB.

Requires prepared UniXNU Mesa/translator patches and the local Rust toolchain.
Outputs are build artifacts, not evidence of a working Metal device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference', type=Path, default=ROOT.parent/'unixnu-reference')
p.add_argument('--stage', choices=['turnip', 'frontend', 'bridge', 'bundle'], required=True)
a = p.parse_args()
U = a.reference.resolve()
OUT = ROOT/'work/waffle/unixnu-build'
SDK = ROOT/'work/theos/sdks/iPhoneOS16.5.sdk'
FRONT = OUT/'frontend'
FRONT.mkdir(parents=True, exist_ok=True)


def run(cmd, log, env=None):
    cmd = [str(v) for v in cmd]
    print('Running:', cmd[0], '→', log, flush=True)
    with Path(log).open('w') as stream:
        subprocess.run(cmd, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)


def git(directory, *args, env=None):
    return subprocess.check_output(['git', '-C', str(directory), *args], env=env, text=True).strip()


assert git(U/'drivers/AdrenoMetal', 'rev-parse', 'HEAD') == '6416a76e0a287d85afbcddda21192388460e155c'
cc = ROOT/'xnu-deps/host/bin/xnu-clang'
cxx = ROOT/'xnu-deps/host/bin/xnu-clang++'
flags = ['-arch', 'arm64', '-isysroot', SDK, '-miphoneos-version-min=16.5', '-O2']
includes = ['-I', U/'drivers/Adreno740', '-I', U/'kits/AdrenoPM4',
            '-I', U/'.cache/mesa-work/include', '-I', U/'build/turnip-smoke']
env = dict(os.environ, XNU_SDK_VERSION='16.5')

if a.stage == 'turnip':
    sys.path.insert(0, str(U/'scripts'))
    from mesa_patch_identity import validate_recorded_patches
    pins = json.loads((U/'scripts/data/adreno-compiler-inputs.json').read_text())
    source = U/'.cache/mesa-work'
    assert git(source, 'rev-parse', 'HEAD') == pins['mesa']['commit']
    validate_recorded_patches(U, source, pins)
    cross = OUT/'ios16.cross'
    # The existing qualified Darwin cross configuration supplies the local
    # cctools linker and libc++ ABI flags. Only its dependency search changes.
    cross.write_text((ROOT/'xnu-deps/build/mesa/cross.ini').read_text().replace(
        "pkg-config = 'false'", "pkg-config = '/usr/bin/pkg-config'"))
    pc = OUT/'pkgconfig'
    pc.mkdir(exist_ok=True)
    version = re.search(r'#define ZLIB_VERSION "([^"]+)"',
                        (SDK/'usr/include/zlib.h').read_text())[1]
    (pc/'zlib.pc').write_text(f'''prefix={SDK}/usr
libdir=${{prefix}}/lib
includedir=${{prefix}}/include
Name: zlib
Description: iPhoneOS16.5 SDK zlib
Version: {version}
Libs: -L${{libdir}} -lz
Cflags: -I${{includedir}}
''')
    options = ['-Dgallium-drivers=', '-Dvulkan-drivers=freedreno',
        '-Dfreedreno-kmds=darwin', '-Dtu-darwin-abi-dir='+str(U/'drivers/Adreno740'),
        '-Dplatforms=macos', '-Dglx=disabled', '-Degl=disabled', '-Dgbm=disabled',
        '-Dopengl=false', '-Dgles1=disabled', '-Dgles2=disabled', '-Dllvm=disabled',
        '-Dshared-glapi=disabled', '-Dxmlconfig=disabled', '-Dshader-cache=enabled',
        '-Dtools=', '-Dbuild-tests=false', '-Dvideo-codecs=', '-Dvulkan-layers=',
        '-Dlibunwind=disabled', '-Dlmsensors=disabled', '-Dvalgrind=disabled',
        '-Dexpat=disabled', '-Dzstd=disabled', '-Dbuildtype=release', '-Db_ndebug=true']
    diff = subprocess.check_output(['git', '-C', str(source), 'diff', 'HEAD', '--binary'])
    extras = {n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in
        git(source, 'ls-files', '--others', '--exclude-standard').splitlines()}
    profile = dict(revision=pins['mesa']['commit'], options=options,
        diff_sha256=hashlib.sha256(diff).hexdigest(), extra_sources=extras,
        cross_sha256=hashlib.sha256(cross.read_bytes()).hexdigest(),
        compiler=subprocess.check_output([str(cxx), '--version'], text=True), sdk='16.5')
    identity = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    (OUT/'turnip-build-inputs.json').write_text(json.dumps(dict(source_id=identity,
        profile=profile, hardware_tested=False), indent=2)+'\n')
    options += ['-Dtu-builtin-source-id='+identity, '-Dtu-build-id='+identity[:40]]
    me = dict(env, PATH=str(U/'.cache/mesa-venv/bin')+':'+env['PATH'],
              PKG_CONFIG_LIBDIR=str(pc), PKG_CONFIG_PATH='')
    command = [U/'.cache/mesa-venv/bin/meson', 'setup', OUT/'turnip', source,
               '--cross-file', cross, '--wrap-mode=nodownload']
    if (OUT/'turnip/build.ninja').exists():command += ['--reconfigure', '--clearcache']
    run([*command, *options], OUT/'turnip-configure-final.log', me)
    run([U/'.cache/mesa-venv/bin/ninja', '-C', OUT/'turnip', '-j4'],
        OUT/'turnip-build-final.log', me)

if a.stage == 'frontend':
    source = OUT/'source/AdrenoMetal'
    shutil.copytree(U/'drivers/AdrenoMetal', source, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.git'))
    (source.parent/'GopFramebuffer').mkdir(exist_ok=True)
    shutil.copyfile(U/'drivers/GopFramebuffer/NativeGOPWire.h',
                    source.parent/'GopFramebuffer/NativeGOPWire.h')
    f = source/'NativeBridgeMetalFrontend.mm'
    text = f.read_text()
    assert text.count('MTLLanguageVersion3_1') == 1
    f.write_text(text.replace('MTLLanguageVersion3_1', 'MTLLanguageVersion3_0'))
    f = source/'bridge/FrontendChecks.h'
    text = f.read_text()
    assert '[event waitUntilSignaledValue:3 timeoutMS:10]' in text
    f.write_text(text.replace('[event waitUntilSignaledValue:3 timeoutMS:10]',
                            '[(id)event waitUntilSignaledValue:3 timeoutMS:10]'))
    compat = FRONT/'ios16-metal-compat.h'
    compat.write_text('''#import <Metal/Metal.h>
/* SDK16 MTLBinding.access uses MTLArgumentAccess, values0/1/2. */
typedef MTLArgumentAccess MTLBindingAccess;
/* UniXNU implements this selector in its own shared-event object. */
@interface NSObject (WaffleNativeSharedEventWaitDeclaration)
- (BOOL)waitUntilSignaledValue:(uint64_t)value timeoutMS:(uint64_t)milliseconds;
@end
''')
    for name in ['NativeBridgeMetalFrontend', 'NativeAdrenoMetalPlugin']:
        run([cxx, *flags, '-std=c++17', '-fobjc-arc', '-Wno-deprecated-declarations',
             *includes, '-include', compat, '-c', source/(name+'.mm'),
             '-o', FRONT/(name+'.o')], FRONT/(name+'-build.log'), env)
    run([cc, *flags, '-std=c11', '-c', U/'kits/AdrenoPM4/AdrenoPM4.c',
         '-o', FRONT/'AdrenoPM4.o'], FRONT/'pm4-build.log', env)

if a.stage == 'bridge':
    (U/'build').mkdir(exist_ok=True)
    run(['python3', U/'scripts/build-adreno-metal-bridge.py', '--target', 'ios',
         '--manifest-only'], OUT/'bridge-prepare.log')
    translator = U/'.cache/gpu-reference/metal2vulkan'
    pin = json.loads((U/'scripts/data/gpu-metal-vulkan-inputs.json').read_text())['translator']['commit']
    assert git(translator, 'rev-parse', 'HEAD') == pin
    with tempfile.TemporaryDirectory() as td:
        ge = dict(os.environ, GIT_INDEX_FILE=td+'/index')
        git(translator, 'read-tree', 'HEAD', env=ge)
        git(translator, 'add', '-A', env=ge)
        tree = git(translator, 'write-tree', env=ge)
    runtime = hashlib.sha256((pin+'\n'+tree).encode()).hexdigest()[:32]
    cargo_home = OUT/'toolchain/cargo'
    bridge = U/'build/adreno-metal-bridge'
    be = dict(env, RUSTUP_HOME=str(OUT/'toolchain/rustup'), CARGO_HOME=str(cargo_home),
              SDKROOT=str(SDK), IPHONEOS_DEPLOYMENT_TARGET='16.5',
              CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='4', NMB_RUNTIME_ID=runtime,
              CC_aarch64_apple_ios=str(cc), CXX_aarch64_apple_ios=str(cxx),
              AR_aarch64_apple_ios='llvm-ar',
              CFLAGS_aarch64_apple_ios=f'-isysroot {SDK} -miphoneos-version-min=16.5',
              CARGO_TARGET_AARCH64_APPLE_IOS_LINKER=str(cc),
              NMB_FIXTURE_AIR=str(bridge/'runtime_examples.air'),
              NMB_FC_AIR=str(bridge/'function_constant.air'),
              NMB_SCANOUT_AIR=str(bridge/'scanout_convert.air'))
    run([cargo_home/'bin/cargo', '+1.98.0', 'build', '--release', '--manifest-path',
         bridge/'Cargo.toml', '--target', 'aarch64-apple-ios', '--target-dir',
         OUT/'rust-target'], OUT/'bridge-build-final.log', be)
    (OUT/'bridge-source.json').write_text(json.dumps(dict(translator_pin=pin,
        patched_tree=tree, runtime_id=runtime, deployment='16.5',
        final_rebuild_required=False), indent=2)+'\n')

if a.stage == 'bundle':
    bundle = OUT/'NativeAdrenoMetal.bundle'
    bundle.mkdir(exist_ok=True)
    archive = OUT/'rust-target/aarch64-apple-ios/release/libadreno_metal_bridge.a'
    identity = json.loads((OUT/'bridge-source.json').read_text())
    assert not identity['final_rebuild_required']
    run([cxx, *flags, '-bundle', FRONT/'NativeAdrenoMetalPlugin.o',
         FRONT/'NativeBridgeMetalFrontend.o', FRONT/'AdrenoPM4.o', archive,
         '-Wl,-dead_strip', '-lobjc', '-framework', 'Foundation', '-framework',
         'Metal', '-framework', 'IOSurface', '-o', bundle/'NativeAdrenoMetal'],
         OUT/'bundle-link.log', env)
    shutil.copyfile(OUT/'turnip/src/freedreno/vulkan/libvulkan_freedreno.dylib',
                    bundle/'libvulkan_freedreno.dylib')
    (bundle/'Info.plist').write_bytes(plistlib.dumps(dict(
        CFBundleIdentifier='org.blu-sharky.NativeAdrenoMetal',
        CFBundleExecutable='NativeAdrenoMetal', CFBundlePackageType='BNDL',
        CFBundleVersion='1', CFBundleShortVersionString='1',
        NSPrincipalClass='NativeAdrenoMetalDevice', MinimumOSVersion='16.5')))
    artifacts = {}
    for name, expected_kind, required_symbol in [
        ('NativeAdrenoMetal', 8, '_native_bridge_metal_open'),
        ('libvulkan_freedreno.dylib', 6, '_vk_icdGetInstanceProcAddr')]:
        path = bundle/name
        data = path.read_bytes()
        magic, cpu, subtype, kind, count, size, flags_, reserved = struct.unpack_from('<8I', data)
        assert magic == 0xfeedfacf and cpu == 0x100000c and kind == expected_kind
        at = 32
        versions, dependencies = [], []
        for _ in range(count):
            command, length = struct.unpack_from('<II', data, at)
            assert length >= 8 and at+length <= 32+size
            if command == 0x32:
                platform, minimum, sdk_version = struct.unpack_from('<III', data, at+8)
                assert platform == 2 and minimum <= 0x100500
                versions.append(dict(platform=platform, minos=minimum, sdk=sdk_version))
            if command in (0xc, 0x80000018):
                offset = struct.unpack_from('<I', data, at+8)[0]
                dependencies.append(data[at+offset:data.index(0, at+offset, at+length)].decode())
            at += length
        assert versions
        symbols = subprocess.check_output(['llvm-nm', '-g', '--defined-only', str(path)], text=True)
        assert required_symbol in symbols
        artifacts[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                               build_versions=versions, dependencies=dependencies)
    provenance = dict(hardware_tested=False, installed=False, signed_for_device=False,
        target='OnePlus12 A750 / iOS16.5, userspace build only',
        components={name:git(U/name, 'rev-parse', 'HEAD') for name in
                    ['drivers/AdrenoMetal', 'drivers/Adreno740', 'drivers/GopFramebuffer', 'kits/AdrenoPM4']},
        bridge=identity, turnip=json.loads((OUT/'turnip-build-inputs.json').read_text()),
        artifacts=artifacts,
        runtime_blocker='Existing port has private PID1 cdev ABI, not NativeAdreno IOKit UserClient/memory tokens/device info expected by Turnip')
    (OUT/'userspace-build-result.json').write_text(json.dumps(provenance, indent=2)+'\n')
print('Build stage finished:', a.stage, '; hardware not tested')
