#!/usr/bin/env python3
"""Build the real metal2vulkan/Turnip buffer probe RAM root; no USB."""
from pathlib import Path
import argparse,subprocess,os,sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));import mkpackfs as pf
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
u=ROOT.parent/'unixnu-reference';sdk=ROOT/'work/theos/sdks/iPhoneOS16.5.sdk';cc=ROOT/'xnu-deps/host/bin/xnu-clang';cxx=ROOT/'xnu-deps/host/bin/xnu-clang++';bundle=ROOT/'work/waffle/unixnu-build/NativeAdrenoMetal.bundle'
result=json.loads((ROOT/'work/waffle/unixnu-build/userspace-build-result.json').read_text())
for name,record in result['artifacts'].items():assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==record['sha256'],name
env=dict(os.environ,PATH=str(ROOT/'xnu-deps/host/bin')+':'+os.environ['PATH'],XNU_SDK_VERSION='16.5')
flags=[str(cc),'-arch','arm64','-Os','-static','-nostdlib','-ffreestanding','-fno-stack-protector','-fno-builtin','-isysroot',str(ROOT/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),'-I',str(ROOT/'userland/libmini')]
for source,name in [('userland/libmini/mini.c','mini.o'),('userland/libmini/start.S','start.o')]:subprocess.run(flags+['-c',str(ROOT/source),'-o',str(out/name)],env=env,check=True)
init=out/'init';subprocess.run(flags+['-Wl,-e,_start','-Wl,-pagezero_size,0x100000000','-o',str(init),str(ROOT/'userland/src/waffle_unixnu_runtime_init.c'),str(out/'mini.o'),str(out/'start.o')],env=env,check=True)
program=out/'waffle-unixnu-runtime-probe';subprocess.run([str(cxx),'-arch','arm64','-isysroot',str(sdk),'-miphoneos-version-min=16.5','-O2','-std=c++17','-I',str(u/'drivers/AdrenoMetal/bridge'),str(ROOT/'userland/src/waffle_unixnu_runtime_probe.cpp'),'-o',str(program)],env=env,check=True)
tree=pf.Node(b'',0o40755,0);image=(ROOT/'work/waffle/gpu/probe-firmware-system.packfs').read_bytes();sup=pf.SUPER.unpack_from(image);nodes=[pf.DNODE.unpack_from(image,sup[3]+i*pf.DNODE.size) for i in range(sup[2])]
def name(i):n=nodes[i];return image[sup[4]+n[7]:sup[4]+n[7]+n[8]].decode()
def path(i):return (path(nodes[i][6])+'/' if i and nodes[i][6] else '')+name(i)
fw=out/'fw';fw.mkdir(exist_ok=True);firmware={}
for i,n in enumerate(nodes):
 f=path(i)
 if f.startswith('fw/') and n[4]:
  assert not n[9];target=fw/f[3:];target.write_bytes(image[n[5]:n[5]+n[4]]);pf.add_file(tree,f,str(target));firmware[f]=hashlib.sha256(target.read_bytes()).hexdigest()
assert len(firmware)==4
pf.add_file(tree,'sbin/init',str(init),mode=0o100755);pf.add_file(tree,'bin/waffle-unixnu-runtime-probe',str(program),mode=0o100755)
for f in bundle.iterdir():
 if f.is_file():pf.add_file(tree,'lib/NativeAdrenoMetal.bundle/'+f.name,str(f),mode=0o100755 if f.name!='Info.plist' else 0o100644)
ram=out/'root.packfs';pf.pack(tree,str(ram),block=4096,page=16384)
files=['userland/src/waffle_unixnu_runtime_probe.cpp','userland/src/waffle_unixnu_runtime_init.c','tools/build-waffle-unixnu-runtime-probe.py','tools/build-waffle-unixnu-userspace.py']
manifest=dict(unixnu_runtime_probe=True,unixnu_query_test=False,hardware_tested=False,Metal_frontend=False,CPU_fallback=False,root_sha256=hashlib.sha256(ram.read_bytes()).hexdigest(),source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},program_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),bundle_artifacts=result['artifacts'],firmware=firmware)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(root=str(ram),hardware_tested=False)))
