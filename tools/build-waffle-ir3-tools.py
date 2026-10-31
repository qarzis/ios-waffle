"""Link an offline FD750 assembler against a configured native Mesa build."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, default=root / 'work/waffle/gpu/compute-build')
parser.add_argument('--output', type=Path, default=root / 'work/waffle/gpu/forensic-audit/compute-tools')
parser.add_argument('--compute-export', action='store_true')
args = parser.parse_args()
build, output = args.build.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
source = root / ('tools/waffle-compute-export.cc' if args.compute_export else 'tools/waffle-ir3-assemble.c')
commands = json.loads((build / 'compile_commands.json').read_text())
suffix='/computerator/a6xx.cc' if args.compute_export else '/ir3/ir3_assembler.c'
command = next(c for c in commands if c['file'].endswith(suffix))
original = shlex.split(command['command'])
compile_args = []
skip = False
for word in original:
    if skip:
        skip = False
        continue
    if word in ('-o', '-c', '-MF', '-MQ', '-MT'):
        skip = True
        continue
    if word not in ('-MD', '-MMD', '-MP'):
        compile_args.append(word)
name='waffle-compute-export' if args.compute_export else 'waffle-ir3-assemble'
obj = output / (name+'.o')
compile_args += ['-c', str(source), '-o', str(obj)]
subprocess.run(compile_args, cwd=build, check=True)
ninja = root / 'xnu-deps/build/mesa/venv/bin/ninja'
lines = subprocess.check_output([str(ninja), '-C', str(build), '-t', 'commands',
    'src/freedreno/computerator/computerator'], text=True).splitlines()
link_args = shlex.split(lines[-1])
assert link_args[0] == 'c++' and '-o' in link_args
keep=('computerator.p/a6xx.cc.o','computerator.p/ir3_asm.cc.o') if args.compute_export else ()
link_args = [word for word in link_args if not word.endswith('.o') or word.endswith(keep)]
binary = output / name
link_args[link_args.index('-o') + 1] = str(binary)
link_args.insert(1, str(obj))
if args.compute_export:
    for symbol in ('_fd_bo_new','_fd_bo_set_name','fd_bo_map','fd_bo_upload','fd_bo_mark_for_dump',
                   'fd_bo_del','fd_bo_size','fd_submit_new_ringbuffer'):
        link_args.append('-Wl,--wrap='+symbol)
subprocess.run(link_args, cwd=build, check=True)
(output / (name+'-build.json' if args.compute_export else 'offline-assembler-build.json')).write_text(json.dumps({
    'mesa_build': str(build), 'compile_argv': compile_args, 'link_argv': link_args,
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    'device_execution': False,
}, indent=2) + '\n')
print(binary)
