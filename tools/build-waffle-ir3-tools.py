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
args = parser.parse_args()
build, output = args.build.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
source = root / 'tools/waffle-ir3-assemble.c'
commands = json.loads((build / 'compile_commands.json').read_text())
command = next(c for c in commands if c['file'].endswith('/ir3/ir3_assembler.c'))
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
obj = output / 'waffle-ir3-assemble.o'
compile_args += ['-c', str(source), '-o', str(obj)]
subprocess.run(compile_args, cwd=build, check=True)
ninja = root / 'xnu-deps/build/mesa/venv/bin/ninja'
lines = subprocess.check_output([str(ninja), '-C', str(build), '-t', 'commands',
    'src/freedreno/computerator/computerator'], text=True).splitlines()
link_args = shlex.split(lines[-1])
assert link_args[0] == 'c++' and '-o' in link_args
link_args = [word for word in link_args if not word.endswith('.o')]
binary = output / 'waffle-ir3-assemble'
link_args[link_args.index('-o') + 1] = str(binary)
link_args.insert(1, str(obj))
subprocess.run(link_args, cwd=build, check=True)
(output / 'offline-assembler-build.json').write_text(json.dumps({
    'mesa_build': str(build), 'compile_argv': compile_args, 'link_argv': link_args,
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    'device_execution': False,
}, indent=2) + '\n')
print(binary)
