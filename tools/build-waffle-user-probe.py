"""Build a freestanding Darwin PID1 and separate RAM-only probe root."""
from pathlib import Path
import argparse,hashlib,json,os,stat,struct,subprocess,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools'));import mkpackfs as pf
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mapped',action='store_true')
parser.add_argument('--mesa-transport',action='store_true')
parser.add_argument('--msm',action='store_true')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();assert not args.mesa_transport or args.msm;assert not args.mapped or args.mesa_transport;out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(root/'xnu-deps/host/bin')+':'+os.environ['PATH'],XNU_SDK_VERSION='16.5')
cc=[str(root/'xnu-deps/host/bin/xnu-clang'),'-arch','arm64','-Os','-static','-nostdlib','-ffreestanding','-fno-stack-protector','-fno-builtin','-Wall','-Wextra','-isysroot',str(root/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),'-I',str(root/'userland/libmini'),'-I',str(root/'kernel/files/bsd/sys')]
for src,name in [('userland/libmini/mini.c','mini.o'),('userland/libmini/start.S','start.o')]:
 subprocess.run(cc+['-c',str(root/src),'-o',str(out/name)],env=env,check=True)
binary=out/'waffle-gpu-user-probe'
extra=['-DWAFFLE_MSM_PROBE',str(root/'tools/mesa/drm-shim/drm_shim.c')] if args.mesa_transport else []
if args.mapped:extra+=['-DWAFFLE_MSM_MAP_PROBE']
subprocess.run(cc+extra+['-Wl,-e,_start','-Wl,-pagezero_size,0x100000000','-o',str(binary),str(root/('userland/src/waffle_msm_probe.c' if args.msm else 'userland/src/waffle_gpu_probe.c')),str(out/'mini.o'),str(out/'start.o')],env=env,check=True)
# Verify executable has no dynamic loader/dependencies and expected ARM64 entry.
b=binary.read_bytes();magic,cpu,subtype,kind,ncmds,cmdsize,flags,reserved=struct.unpack_from('<8I',b)
assert magic==0xfeedfacf and cpu==0x100000c and kind==2
cursor=32;commands=[]
for _ in range(ncmds):
 cmd,size=struct.unpack_from('<II',b,cursor);assert size>=8 and cursor+size<=32+cmdsize;commands.append(cmd);cursor+=size
assert cursor==32+cmdsize and 0xe not in commands and 0xc not in commands and (0x5 in commands or 0x80000028 in commands)
fw_path=root/'work/waffle/gpu/probe-firmware-system.packfs';image=fw_path.read_bytes();s=pf.SUPER.unpack_from(image)
assert s[0]==pf.MAGIC and s[7]==len(image)
nodes=[pf.DNODE.unpack_from(image,s[3]+i*pf.DNODE.size) for i in range(s[2])]
def node_name(i):
 n=nodes[i];assert n[7]+n[8]<=s[5];return image[s[4]+n[7]:s[4]+n[7]+n[8]].decode()
def node_path(i):return (node_path(nodes[i][6])+'/' if i and nodes[i][6] else '')+node_name(i)
tree=pf.Node(b'',0o40755,0);fwdir=out/'firmware';fwdir.mkdir(exist_ok=True);firmware={}
for i,n in enumerate(nodes):
 path=node_path(i)
 if stat.S_ISDIR(n[0]):pf.node_at(tree,path,create=True);continue
 assert stat.S_ISREG(n[0]) and n[9]==0 and n[5]+n[4]<=len(image)
 assert path.startswith('fw/') and '/' not in path[3:]
 target=fwdir/path[3:];target.write_bytes(image[n[5]:n[5]+n[4]]);pf.add_file(tree,path,str(target))
 firmware[path]=hashlib.sha256(target.read_bytes()).hexdigest()
assert len(firmware)==4
pf.node_at(tree,'sbin',create=True);pf.add_file(tree,'sbin/launchd',str(binary),mode=0o100755)
ram=out/'user-probe.packfs';pf.pack(tree,str(ram),block=4096,page=16384)
manifest={'experiment':'E32 actual Mesa DRM shim transport' if args.mesa_transport else 'E31 MSM diagnostic' if args.msm else 'E27 standalone Darwin user GPU boundary','mesa_drm_shim':args.mesa_transport,'mapped_bo':args.mapped,'static_arm64_pid1':True,'dynamic_loader':False,'flash_operations':False,'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in [('userland/src/waffle_msm_probe.c' if args.msm else 'userland/src/waffle_gpu_probe.c'),'kernel/files/bsd/sys/waffle_gpu_msm.h','kernel/files/bsd/sys/waffle_gpu_data.h','kernel/files/bsd/sys/waffle_gpu_glsl.h','userland/libmini/mini.c','userland/libmini/mini.h','userland/libmini/start.S','kernel/files/bsd/sys/waffle_gpu_user.h','tools/build-waffle-user-probe.py','tools/mesa/drm-shim/drm_shim.c']},'program_sha256':hashlib.sha256(b).hexdigest(),'packfs_sha256':hashlib.sha256(ram.read_bytes()).hexdigest(),'firmware':firmware,'load_commands':commands,'user_execution_tested':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'program':str(binary),'ram_root':str(ram),'static_arm64':True,'firmware_files':len(firmware)}))
