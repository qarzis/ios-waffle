#!/usr/bin/env python3
"""Compare offline extraction against compiled native register tables."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('start_tables', ROOT/'tools/build-waffle-gpu-start-tables.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
vendor = ROOT/'work/waffle/gpu/vendor'
data = module.generate(vendor)
core = (vendor/'adreno-gpulist.h').read_text()
startup = (vendor/'adreno_gen7.c').read_text()

def native(text, name):
    return re.search(r'static const [^;]+\b' + name + r'\[\]\s*=\s*\{.*?\n\};', text, re.S)[0]

tables = [('gbif', 'gen7_0_0_gbif_regs', core),
          ('gmu_ao_hwcg', 'gen7_2_0_ao_hwcg_regs', core),
          ('protected', 'gen7_9_0_protected_regs', core),
          ('ifpc', 'gen7_ifpc_pwrup_reglist', startup),
          ('bicubic', 'gen7_9_x_ifpc_pwrup_reglist', startup),
          ('preemption', 'gen7_pwrup_reglist', startup)]
code = '''#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
struct kgsl_regmap_list { u32 offset, val; };
struct gen7_protected_regs { u32 reg, start, end, noaccess; };
#include "gen7_reg.h"
#define COUNT(a) (sizeof(a)/sizeof((a)[0]))
'''
code += '\n'.join(native(text, name) for _, name, text in tables)
code += '\nint main(void) {\n'
for label, name, _ in tables:
    code += f'for (unsigned i=0;i<COUNT({name});i++) {{\n'
    if label == 'protected':
        code += f'const struct gen7_protected_regs *r=&{name}[i]; if (!r->reg) break;\n'
        code += f'printf("{label} %u %u\\n",r->reg,(r->start & 0x3ffffu) | (((r->end-r->start)<<18)&0x7ffc0000u) | (r->noaccess<<31));\n'
    elif label in ('gbif','gmu_ao_hwcg'):
        code += f'printf("{label} %u %u\\n",{name}[i].offset,{name}[i].val);\n'
    else:
        code += f'printf("{label} %u\\n",{name}[i]);\n'
    code += '}\n'
code += 'return 0; }\n'
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers',
                    '-fsanitize=address,undefined','-I',str(vendor),str(path/'test.c'),'-o',str(path/'test')],check=True)
    output = subprocess.check_output([str(path/'test')],text=True)
rows = {}
for line in output.splitlines():
    name, *values = line.split()
    rows.setdefault(name, []).append(list(map(int, values)))
for name in ('gbif','gmu_ao_hwcg','protected'):
    assert rows[name] == [[r['offset'],r['value']] for r in data[name]], name
assert rows['ifpc'] + rows['bicubic'] == [[r['offset']] for r in data['ifpc_restore']]
assert rows['preemption'] == [[r['offset']] for r in data['preemption_restore']]
assert data['static_restore_bytes'] == 616
print(json.dumps({'native_table_comparison':'passed','protection_spans':len(rows['protected']),
                  'restore_pairs':len(rows['ifpc'])+len(rows['bicubic'])+len(rows['preemption']),
                  'sanitizers':'ASan+UBSan','device_access':False}))
