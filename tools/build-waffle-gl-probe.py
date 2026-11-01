"""Create controlled dynamic OSMesa probe root for the existing full iOS system RAM image."""
from pathlib import Path
import argparse,subprocess,os,sys,json,hashlib,struct
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'));import mkpackfs as pf
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--present',action='store_true',help='Read GPU pixels into IOSurface and use existing display swap');args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
cc=str(root/'xnu-deps/host/bin/xnu-clang');sdk=root/'work/theos/sdks/iPhoneOS16.5.sdk';lib=root/'xnu-deps/build/mesa/out-26.3.0-rc1/libOSMesa.8.dylib'
env=dict(os.environ,PATH=str(root/'xnu-deps/host/bin')+':'+os.environ['PATH'],XNU_SDK_VERSION='16.5')
# Static init is invoked by the original system image's stage0 after mounting md1.
flags=[cc,'-arch','arm64','-Os','-static','-nostdlib','-ffreestanding','-fno-stack-protector','-fno-builtin','-Wall','-Wextra','-isysroot',str(root/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),'-I',str(root/'userland/libmini')]
for src,name in [('userland/libmini/mini.c','mini.o'),('userland/libmini/start.S','start.o')]:subprocess.run(flags+['-c',str(root/src),'-o',str(out/name)],env=env,check=True)
init=out/'waffle-gl-init';subprocess.run(flags+['-Wl,-e,_start','-Wl,-pagezero_size,0x100000000','-o',str(init),str(root/'userland/src/waffle_gl_init.c'),str(out/'mini.o'),str(out/'start.o')],env=env,check=True)
program=out/'waffle-gl-probe';subprocess.run([cc,'-arch','arm64','-isysroot',str(sdk),'-Os','-Wall','-Wextra','-I',str(root/'xnu-deps/build/mesa/mesa-26.3.0-rc1/include'),str(root/'userland/src/waffle_gl_probe.c'),str(lib),*(['-DWAFFLE_GL_PRESENT','-framework','CoreFoundation','-framework','IOSurface','-framework','IOKit'] if args.present else []),'-o',str(program)],env=env,check=True)
# ELF/host libraries must never enter the Darwin probe.
def load_commands(path):
 b=path.read_bytes();magic,cpu,subtype,kind,ncmds,cmdsize,flags,reserved=struct.unpack_from('<8I',b);assert magic==0xfeedfacf and cpu==0x100000c
 result=[];at=32
 for i in range(ncmds):
  cmd,size=struct.unpack_from('<II',b,at);assert size>=8 and at+size<=32+cmdsize
  if cmd in (0xc,0xd,0x18,0x80000018,0x8000001f,0xe):
   offset=struct.unpack_from('<I',b,at+8)[0];result.append({'cmd':cmd,'path':b[at+offset:b.index(b'\0',at+offset,at+size)].decode()})
  at+=size
 return result
commands=load_commands(program);assert any(v['cmd']==0xe and v['path']=='/usr/lib/dyld' for v in commands);assert any(v['path']=='/redwood/lib/libOSMesa.8.dylib' for v in commands)
tree=pf.Node(b'',0o40755,0);image=(root/'work/waffle/gpu/probe-firmware-system.packfs').read_bytes();s=pf.SUPER.unpack_from(image);nodes=[pf.DNODE.unpack_from(image,s[3]+i*pf.DNODE.size) for i in range(s[2])]
def name(i):n=nodes[i];return image[s[4]+n[7]:s[4]+n[7]+n[8]].decode()
def path(i):return (path(nodes[i][6])+'/' if i and nodes[i][6] else '')+name(i)
firmware={};fwdir=out/'fw';fwdir.mkdir(exist_ok=True)
for i,n in enumerate(nodes):
 f=path(i)
 if not f.startswith('fw/') or not n[4]:continue
 assert not n[9];target=fwdir/f[3:];target.write_bytes(image[n[5]:n[5]+n[4]]);pf.add_file(tree,f,str(target));firmware[f]=hashlib.sha256(target.read_bytes()).hexdigest()
assert len(firmware)==4
for directory in ('sbin','bin','lib'):pf.node_at(tree,directory,create=True)
pf.add_file(tree,'sbin/init',str(init),mode=0o100755);pf.add_file(tree,'bin/waffle-gl-probe',str(program),mode=0o100755);pf.add_file(tree,'lib/libOSMesa.8.dylib',str(lib),mode=0o100755)
ram=out/'root.packfs';pf.pack(tree,str(ram),block=4096,page=16384)
files=['userland/src/waffle_gl_init.c','userland/src/waffle_gl_probe.c','tools/build-waffle-gl-probe.py','tools/mesa/drm-shim/drm_shim.c','tools/mesa/drm-shim/waffle_msm_transport.h','kernel/files/bsd/sys/waffle_gpu_msm.h']
manifest={'experiment':'E40 actual Mesa IOSurface presentation' if args.present else 'E36 controlled real Darwin OSMesa GL triangle','presentation_probe':args.present,'gpu_hardware_tested':False,'dynamic_arm64_program':True,'program_load_commands':commands,'mesa_load_commands':load_commands(lib),'program_sha256':hashlib.sha256(program.read_bytes()).hexdigest(),'mesa_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),'root_sha256':hashlib.sha256(ram.read_bytes()).hexdigest(),'firmware':firmware,'source_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},'system_image':'work/waffle/images/system.packfs','system_mutated':False,'user_checks':256,'expected_filled_pixels':128,'fallback_renderer_refused':True}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'root':str(ram),'program':str(program),'mesa_bytes':lib.stat().st_size,'hardware_tested':False}))
