"""Actual packet auditor rejects escaped memory/protected registers and bad packets."""
from pathlib import Path
import importlib.util
import json
import re
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compute_check', root / 'tools/check-waffle-compute.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
text = (root / 'kernel/files/bsd/sys/waffle_gpu_compute.h').read_text()
array = re.search(r'waffle_compute_payload\[4096\]=\{(.*?)\};', text, re.S)[1]
words = [int(v, 16) for v in re.findall(r'0x([0-9a-f]+)u', array)]
assert len(words) == 4096
payload = struct.pack('<4096I', *words)
manifest = json.loads((root / 'tools/tests/fixtures/waffle-compute-manifest.json').read_text())
enums = json.loads((root / 'tools/tests/fixtures/waffle-compute-opcodes.json').read_text())
enum_header = '\n'.join(f'{name} = {value},' for name, value in enums.items())
protect = (root / 'kernel/files/bsd/sys/waffle_gen7_tables.h').read_text()
result = module.audit(payload, manifest, enum_header, protect)
assert result['command_dwords'] == 184 and result['exec_word_offset'] == 164
assert len(result['register_writes']) == 73 and result['protected_register_writes'] == 0


def changed(word, value):
    copy = list(words)
    copy[word] = value
    return struct.pack('<4096I', *copy)


bad = [payload[:-4], changed(256, 0), changed(256, words[256] ^ 0x8000),
       changed(256 + 5, 0x84f),  # Protected CP_PROTECT_CNTL inside first NC register bunch.
       changed(256 + 126, words[256 + 126] + 4),  # Indirect shader address.
       changed(4352 // 4 + 4, 0),  # Output descriptor target.
       changed(64, 0), changed(2048, 1)]  # CPU must not prefill expected result or control.
for data in bad:
    try:
        module.audit(data, manifest, enum_header, protect)
    except (AssertionError, KeyError, IndexError, struct.error):
        continue
    raise AssertionError('Invalid/unsafe shader payload accepted')

code = r'''
#include <assert.h>
#include "waffle_gpu_compute.h"
int main(void){
 unsigned different=0;
 for(unsigned i=0;i<4096;i++){
  if(waffle_compute_initial(1,i)!=waffle_compute_initial(2,i)){assert(i>=WAFFLE_COMPUTE_EXEC_WORD && i<WAFFLE_COMPUTE_EXEC_WORD+5);different++;}
  if(i>=64 && i<72){assert(waffle_compute_initial(1,i)==0xdead0000u+i-64);assert(waffle_compute_initial(2,i)==0xdead0000u+i-64);assert(waffle_compute_expected(2,i)==i-64);}
 }
 assert(different==4);
 assert(waffle_compute_initial(1,WAFFLE_COMPUTE_EXEC_WORD)==0x70100004);
 for(unsigned i=1;i<5;i++)assert(!waffle_compute_initial(1,WAFFLE_COMPUTE_EXEC_WORD+i));
 assert(waffle_compute_initial(2,2048)==0 && waffle_compute_expected(2,2048)==1);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(code)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Compute payload: packet parity/bounds, protected-register and escaped-address rejection, poisoned output and one-packet prepare/dispatch difference passed')
