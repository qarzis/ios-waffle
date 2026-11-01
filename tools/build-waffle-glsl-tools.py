"""Link external offline GLSL/IR3 compiler with stock configured Mesa objects."""
from pathlib import Path
import argparse,hashlib,json,os,shlex,subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compute-export',action='store_true');p.add_argument('--build',type=Path,default=root/'work/waffle/gpu/compute-build');p.add_argument('--output',type=Path,default=root/'work/waffle/gpu/forensic-audit/compute-tools');a=p.parse_args()
build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
ninja=root/'xnu-deps/build/mesa/venv/bin/ninja';env=dict(os.environ,PATH=str(ninja.parent)+':'+os.environ['PATH'])
subprocess.run([str(ninja),'-C',str(build),'src/compiler/glsl/glsl_compiler','src/gallium/drivers/freedreno/libfreedreno.a.p/ir3_ir3_descriptor.c.o'],check=True,env=env)
commands=json.loads((build/'compile_commands.json').read_text())
def compile_args(suffix):
 c=next(c for c in commands if c['file'].endswith(suffix));args=shlex.split(c['command']);result=[];skip=False
 for s in args:
  if skip:skip=False;continue
  if s in ('-o','-c','-MF','-MQ','-MT'):skip=True;continue
  if s not in ('-MD','-MMD','-MP'):result.append(s)
 return result
args=compile_args('/compiler/glsl/main.cpp')
for s in compile_args('/computerator/a6xx.cc')[1:]:
 if s.startswith(('-I','-D')) and s not in args:args.append(s)
args += ['-I'+str(root/'xnu-deps/build/mesa/mesa-26.3.0-rc1/src/gallium/drivers/freedreno')]
source=root/'tools/waffle-glsl-compile.cc';
if a.compute_export:args+=['-DWAFFLE_GLSL_LIBRARY=1']
obj=out/'waffle-glsl-compile.o';args+=['-c',str(source),'-o',str(obj)]
subprocess.run(args,cwd=build,check=True)
def link_command(target):return shlex.split(subprocess.check_output([str(ninja),'-C',str(build),'-t','commands',target],text=True).splitlines()[-1])
link=link_command('src/compiler/glsl/glsl_compiler');link=[s for s in link if not s.endswith('.o')];binary=out/'waffle-glsl-compile';link[link.index('-o')+1]=str(binary);link.insert(1,str(obj))
end=link.index('-Wl,--end-group');extra=[s for s in link_command('src/freedreno/computerator/computerator') if s.endswith('.a') and s not in link];extra.append('src/gallium/drivers/freedreno/libfreedreno.a.p/ir3_ir3_descriptor.c.o')
if a.compute_export:
 export_source=root/'tools/waffle-compute-export.cc';export_obj=out/'waffle-glsl-export.o'
 export_args=args[:-4]+['-DWAFFLE_GLSL_EXPORT=1','-c',str(export_source),'-o',str(export_obj)]
 export_args=[x for x in export_args if x!='-DWAFFLE_GLSL_LIBRARY=1']
 subprocess.run(export_args,cwd=build,check=True)
 link.insert(1,str(export_obj));link[link.index('-o')+1]=str(out/'waffle-glsl-export');binary=out/'waffle-glsl-export'
 extra += ['src/freedreno/computerator/computerator.p/a6xx.cc.o','src/freedreno/computerator/computerator.p/ir3_asm.cc.o']
 for symbol in ('_fd_bo_new','_fd_bo_set_name','fd_bo_map','fd_bo_upload','fd_bo_mark_for_dump','fd_bo_del','fd_bo_size','fd_submit_new_ringbuffer'):link.append('-Wl,--wrap='+symbol)
 end=link.index('-Wl,--end-group')
link[end:end]=extra
subprocess.run(link,cwd=build,check=True)
(out/('glsl-export-build.json' if a.compute_export else 'glsl-compiler-build.json')).write_text(json.dumps({'compile_argv':args,'link_argv':link,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'device_opened':False},indent=2)+'\n')
print(binary)
