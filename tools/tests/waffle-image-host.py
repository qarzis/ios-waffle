"""Audited image payload, strict pixel readback and lossless PNG serialization."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import tempfile
import zlib

root = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, root / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


check = module('compute_check', 'tools/check-waffle-compute.py')
runner = module('image_runner', 'scripts/run_waffle_ios.py')
source = (root / 'kernel/files/bsd/sys/waffle_gpu_image.h').read_text()
body = re.search(r'waffle_image_payload\[4096\]=\{(.*?)\};', source, re.S)[1]
words = [int(v, 16) for v in re.findall(r'0x([0-9a-f]+)u', body)]
payload = struct.pack('<4096I', *words)
manifest = json.loads((root / 'tools/tests/fixtures/waffle-image-manifest.json').read_text())
provenance = json.loads((root / 'tools/tests/fixtures/waffle-image-source.json').read_text())
assert hashlib.sha256(payload).hexdigest() == provenance['payload_sha256']
assert hashlib.sha256(payload[4096:4224]).hexdigest() == provenance['shader_binary_sha256']
assert hashlib.sha256((root / 'tools/tests/fixtures/waffle-ramp256.asm').read_bytes()).hexdigest() == provenance['shader_source_sha256']
enums = json.loads((root / 'tools/tests/fixtures/waffle-compute-opcodes.json').read_text())
enum_header = '\n'.join(f'{k} = {v},' for k, v in enums.items())
report = check.audit(payload, manifest, enum_header, (root / 'kernel/files/bsd/sys/waffle_gen7_tables.h').read_text(), True)
assert report['command_dwords'] == 184 and report['protected_register_writes'] == 0
end = ['SMMU_OWNER released after child stop and context detach',
       'CLOCK_OWNER released before CX restore result=1',
       'POWER_OWNER released after clock child, CX and CFG restore result=1',
       'AOP_OWNER released after power child and channel restore result=1 transport=0']
for mode in (1, 2):
    pixels = [(0xff000000 | i) if mode == 2 else 0xdead0000+i for i in range(256)]
    start = ['AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1',
             'full GPU owner returned live to init caller; no mutex held',
             f'IMAGE begin width=16 height=16 pixels=256 dispatch={int(mode==2)}',
             f'COMPUTE begin mode={mode} dispatch={int(mode==2)} words=184 output_poison=1',
             'COMPUTE_IB ACK matched seq44 value=00000000 valid=1',
             'COMPUTE values='+'/'.join(f'{v:08x}' for v in pixels[:8])+f' control=00000001 checked=4096 wrong_words=0 mode={mode}',
             'SESSION result=1 submitted=1 completed=1 next_sequence=45 OOB=1; bounded kernel session']
    rows = [f'waffle-gmu: IMAGE pixels offset={i} values='+ '/'.join(f'{v:08x}' for v in pixels[i:i+8]) for i in range(0,256,8)]
    text = '\n'.join(start+rows+end)
    assert runner.validate_aop_owner_log(text, mode, True) == pixels
    assert runner.extract_gpu_image(text+'\n'+ '\n'.join(rows),mode) == pixels
    bad = [text.replace(rows[0], ''), text.replace(rows[-1], ''),
           text.replace(rows[0], rows[0].replace('offset=0', 'offset=1')),
           text+'\n'+rows[0].replace(f'{pixels[0]:08x}', '11111111', 1),
           text.replace('wrong_words=0', 'wrong_words=1')]
    for value in bad:
        try:
            runner.validate_aop_owner_log(value, mode, True)
        except RuntimeError:
            continue
        raise AssertionError('Incomplete or corrupt GPU image accepted')
    if mode == 2:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.png'
            runner.write_gpu_png(path, runner.extract_gpu_image(text, mode))
            data = path.read_bytes()
            assert data[:8] == b'\x89PNG\r\n\x1a\n'
            offset, compressed = 8, b''
            while offset < len(data):
                size = struct.unpack_from('>I', data, offset)[0]
                kind, body = data[offset+4:offset+8], data[offset+8:offset+8+size]
                assert struct.unpack_from('>I', data, offset+8+size)[0] == zlib.crc32(kind+body) & 0xffffffff
                if kind == b'IHDR': assert struct.unpack('>IIBBBBB', body) == (16,16,8,6,0,0,0)
                if kind == b'IDAT': compressed += body
                offset += 12+size
            actual = zlib.decompress(compressed)
            rgba = b''.join(v.to_bytes(4, 'little') for v in pixels)
            assert actual == b''.join(b'\0'+rgba[y*64:(y+1)*64] for y in range(16))

code = r'''
#include <assert.h>
#include "waffle_gpu_image.h"
int main(void){
 for(unsigned i=0;i<256;i++){
  assert(waffle_image_initial(1,3072+i)==0xdead0000u+i);
  assert(waffle_image_initial(2,3072+i)==0xdead0000u+i);
  assert(waffle_image_expected(1,3072+i)==0xdead0000u+i);
  assert(waffle_image_expected(2,3072+i)==(0xff000000u|i));
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(code)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Image payload: shader/source binding, 256 poisoned pixels, complete readback/duplicate checks and lossless actual-data PNG serialization passed (host only)')
