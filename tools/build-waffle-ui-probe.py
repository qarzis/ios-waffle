#!/usr/bin/env python3
"""Build an isolated RAM UI root selecting the GPU only for backboardd.

Uses the previous UI kit and stock launch jobs; changes no original images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import mkpackfs as pf
import assemble

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--stop-seconds',type=int,choices=(30,60,240,600),default=30)
 parser.add_argument('--hook-library',type=Path,help='Use a source-bound hook previously qualified by the fullsize pixel probe')
 parser.add_argument('--base-kit',type=Path,default=ROOT/'work/waffle/posterboard/client-gl-kit')
 parser.add_argument('--posterboard-providers',action='store_true',help='Restore the qualified duetexpertd/mobileassetd provider configuration')
 parser.add_argument('--service-audit',action='store_true',help='Read-only actual Focus/ringer/Poster service interface discovery')
 parser.add_argument('--poster-inventory',action='store_true',help='Read-only actual wallpaper collection and logical-screen inventory')
 parser.add_argument('--ios16-wallpaper',action='store_true',help='Test scoped availability of bundled iOS16 artwork for375x812@2x')
 parser.add_argument('--cpu-proof',action='store_true',help='Run the delayed CPU concurrency probe alongside the GPU UI')
 parser.add_argument('--mesa-library',type=Path,help='Use an explicitly bound candidate Mesa library')
 parser.add_argument('--reclaim-on-oom',action='store_true',help='Opt in to one bounded BO-cache purge/retry in candidate Mesa')
 args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
 if args.poster_inventory and not args.service_audit:parser.error('--poster-inventory requires --service-audit')
 if args.ios16_wallpaper and not args.service_audit:parser.error('--ios16-wallpaper requires --service-audit')
 sdk=ROOT/'work/theos/sdks/iPhoneOS16.5.sdk'
 cc=str(ROOT/'xnu-deps/host/bin/xnu-clang')
 mesa=args.mesa_library.resolve() if args.mesa_library else ROOT/'xnu-deps/build/mesa/out-26.3.0-rc1/libOSMesa.8.dylib'
 hook=args.hook_library.resolve() if args.hook_library else ROOT/'work/waffle/gpu/e45-gl-contexts/libredwood-gl.dylib'
 assert hook.is_file() and mesa.is_file()
 hook_manifest=None
 if args.hook_library:
  hook_manifest=json.loads((hook.parent/'manifest.json').read_text())
  assert hook_manifest['hook_sha256']==hashlib.sha256(hook.read_bytes()).hexdigest()
  for name,digest in hook_manifest['source_sha256'].items():
   assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
 env=dict(os.environ,PATH=str(ROOT/'xnu-deps/host/bin')+':'+os.environ['PATH'],XNU_SDK_VERSION='16.5')
 if args.posterboard_providers:env['ALLOW']='duetexpertd mobileassetd'
 def run(command,**kwargs):subprocess.run(command,env=env,cwd=ROOT,check=True,**kwargs)
 flags=[cc,'-arch','arm64','-Os','-static','-nostdlib','-ffreestanding','-fno-stack-protector','-fno-builtin','-Wall','-Wextra','-isysroot',str(ROOT/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),'-I',str(ROOT/'userland/libmini')]
 for src,name in [('userland/libmini/mini.c','mini.o'),('userland/libmini/start.S','start.o')]:run(flags+['-c',str(ROOT/src),'-o',str(out/name)])
 init=out/'waffle-ui-init'
 run(flags+['-Wl,-e,_start','-Wl,-pagezero_size,0x100000000',str(ROOT/'userland/src/waffle_ui_init.c'),str(out/'mini.o'),str(out/'start.o'),'-o',str(init)])
 inject=out/'libredwood.dylib'
 run([cc,'-arch','arm64','-isysroot',str(sdk),'-O1','-Wall','-Wextra','-DWAFFLE_UI_GPU_PROBE',f'-DWAFFLE_UI_GPU_STOP_SECONDS={args.stop_seconds}','-dynamiclib','-install_name','/redwood/lib/libredwood.dylib','-framework','CoreFoundation','-framework','IOKit','-lobjc',str(ROOT/'userland/src/inject.c'),'-o',str(inject)])
 scratch=out/'scratch';scratch.mkdir(exist_ok=True)
 tree=pf.scan_tar(str(args.base_kit/'root-base.tar'),str(scratch/'base'))
 normal=pf.node_at(tree,'sbin/init');assert normal and normal.source
 pf.add_file(tree,'sbin/init.real',normal.source,mode=0o100755)
 pf.add_file(tree,'sbin/init',str(init),mode=0o100755)
 for name,path in [('libredwood.dylib',inject),('libredwood-gl.dylib',hook),('libOSMesa.8.dylib',mesa)]:
  pf.add_file(tree,'lib/'+name,str(path),mode=0o100755)
 ours=pf.node_at(tree,'etc/var.skel.redwood')
 skel=scratch/'var.skel';skel.write_text(assemble.var_skel(Path(ours.source).read_text() if ours else ''))
 pf.remove(tree,'etc/var.skel.redwood');pf.add_file(tree,'etc/var.skel',str(skel))
 jobs=scratch/'jobs'
 run([sys.executable,str(ROOT/'userland/mkjobs.py'),'--rest',str(ROOT/'ios165/rootfs'),str(jobs),*assemble.JOBS])
 bb=jobs/'com.apple.backboardd.plist';job=plistlib.loads(bb.read_bytes())
 assert job.get('UserName')=='mobile'
 job['KeepAlive']=False;job['RunAtLoad']=True
 job['StandardOutPath']=job['StandardErrorPath']='/dev/console'
 job.setdefault('EnvironmentVariables',{}).update(WAFFLE_GPU_UI='1',MESA_SHADER_CACHE_DISABLE='true',GALLIUM_THREAD='0',DYLD_SHARED_CACHE_DIR='/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld')
 if args.reclaim_on_oom:job['EnvironmentVariables']['WAFFLE_GPU_RECLAIM_ON_OOM']='1'
 bb.write_bytes(plistlib.dumps(job,fmt=plistlib.FMT_BINARY))
 if args.cpu_proof:
  cpu=out/'cpu_test'
  run([cc,'-arch','arm64','-isysroot',str(sdk),'-O2','-Wall','-Wextra',str(ROOT/'userland/src/cpu_test.c'),'-o',str(cpu)])
  pf.add_file(tree,'bin/cpu_test',str(cpu),mode=0o100755)
  cpu_job=dict(Label='org.waffle.cpu-proof',ProgramArguments=['/redwood/bin/cpu_test','35'],RunAtLoad=True,KeepAlive=False,StandardOutPath='/dev/console',StandardErrorPath='/dev/console')
  (jobs/'org.waffle.cpu-proof.plist').write_bytes(plistlib.dumps(cpu_job))
 if args.service_audit:
  helper=out/'libwaffle-service-audit.dylib'
  run([cc,'-arch','arm64','-isysroot',str(sdk),'-O1','-Wall','-Wextra','-fobjc-arc','-dynamiclib','-framework','Foundation',*(['-framework','UIKit'] if args.ios16_wallpaper else []),str(ROOT/'userland/src/waffle_service_audit.m'),*([str(ROOT/'userland/src/waffle_poster_inventory.m')] if args.poster_inventory else []),*([str(ROOT/'userland/src/inject_waffle_wallpaper.m')] if args.ios16_wallpaper else []),'-o',str(helper)])
  pf.add_file(tree,'lib/libwaffle-service-audit.dylib',str(helper),mode=0o100755)
  injection=pf.node_at(tree,'etc/inject.conf');assert injection and injection.source
  config=scratch/'inject.conf';lines=[]
  for i,line in enumerate(Path(injection.source).read_text().splitlines()):
   if not line.strip():continue
   library,programs=line.split(None,1);assert library.startswith('/redwood/lib/')
   assert pf.node_at(tree,'lib/'+Path(library).name)
   alias=f'{i}.dylib';pf.add_symlink(tree,'lib/'+alias,Path(library).name)
   lines.append('/redwood/lib/'+alias+' '+programs)
  lines.append('/redwood/lib/libwaffle-service-audit.dylib SpringBoard'+(' PosterBoard CollectionsPoster' if args.ios16_wallpaper else ''))
  config.write_text('\n'.join(lines)+'\n');assert len(config.read_bytes().rstrip())+1<=512
  pf.add_file(tree,'etc/inject.conf',str(config))
 for path in sorted(jobs.iterdir()):pf.add_file(tree,'LaunchDaemons/'+path.name,str(path))
 for name in ('extensions.plist','extensions.plist.sig'):
  path=ROOT/'ios165/rootfs/System/Library/xpc'/name
  if path.is_file():pf.add_file(tree,'xpc/'+name,str(path))
 firmware={}
 for path in sorted((ROOT/'work/waffle/gpu/e45-gl-contexts/fw').iterdir()):
  pf.add_file(tree,'fw/'+path.name,str(path));firmware[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 assert len(firmware)==4
 root=out/'root.packfs';pf.pack(tree,str(root),zstd=15,raw=pf.sources_under(tree,'fw'))
 assert root.stat().st_size+16*1024*1024<0x03f00000,'UI payload exceeds RAM loader limit'
 sources=['userland/src/inject.c','userland/src/waffle_ui_init.c','tools/build-waffle-ui-probe.py','userland/mkjobs.py','tools/assemble.py']
 if args.cpu_proof:sources.append('userland/src/cpu_test.c')
 if args.service_audit:sources.append('userland/src/waffle_service_audit.m')
 if args.poster_inventory:sources.append('userland/src/waffle_poster_inventory.m')
 if args.ios16_wallpaper:sources.append('userland/src/inject_waffle_wallpaper.m')
 manifest=dict(experiment='E46 first actual backboardd GPU workload; no UI success claim',hardware_tested=False,RAM_only=True,normal_image_mutated=False,GPU_process='backboardd',GPU_process_uid=501,device_mode='0600',process_stop_seconds=30,job_KeepAlive=False,other_processes_softpipe=True,root_sha256=hashlib.sha256(root.read_bytes()).hexdigest(),root_bytes=root.stat().st_size,inject_sha256=hashlib.sha256(inject.read_bytes()).hexdigest(),hook_sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),mesa_sha256=hashlib.sha256(mesa.read_bytes()).hexdigest(),firmware=firmware,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources})
 manifest['process_stop_seconds']=args.stop_seconds
 manifest['posterboard_providers']=args.posterboard_providers
 manifest['service_audit']=args.service_audit
 manifest['poster_inventory']=args.poster_inventory
 manifest['ios16_wallpaper']=args.ios16_wallpaper
 manifest['cpu_proof']=args.cpu_proof
 manifest['reclaim_on_oom']=args.reclaim_on_oom
 if hook_manifest:
  manifest['hook_policy']={name:hook_manifest.get(name) for name in ('batch_readback','profile_readback','hook_sha256','source_sha256')}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(manifest,indent=2))

if __name__=="__main__":main()
