"""Audit recorded Mesa A7xx packets and export a bounded diagnostic payload."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

root = Path(__file__).resolve().parents[1]


def audit(payload, manifest, enum_header, protect_header):
    assert len(payload) == 16384 and manifest['generation'] == 7
    assert manifest['chip_id'] == '0x43051401' and not manifest['gpu_executed']
    base = int(manifest['gpu_base'], 16)
    assert base == 0x1ff8000478000 and manifest['command_offset'] == 1024
    count = manifest['command_dwords']
    assert 0 < count <= 768
    words = struct.unpack_from('<' + str(count) + 'I', payload, 1024)
    names = {int(value): name for name, value in re.findall(r'^\s*(CP_\w+) = (\d+),', enum_header, re.M)}
    records = {bo['name']: bo for bo in manifest['bo_records']}
    assert set(records) == {'control', 'CL', 'output', 'tex_desc'}
    ranges = [(1024, 1024 + count * 4)]
    for bo in records.values():
        lo, size = bo['offset'], bo['bytes']
        assert size and 0 <= lo < lo + size <= 16384 and int(bo['iova'], 16) == base + lo
        assert all(lo + size <= a or lo >= b for a, b in ranges)
        ranges.append((lo, lo + size))
    assert records['control']['offset'] == 8192 and records['control']['bytes'] == 4096
    assert records['CL']['offset'] == 4096 and records['CL']['bytes'] == 128
    assert records['output']['offset'] == 256 and records['output']['bytes'] == 32
    assert records['tex_desc']['offset'] == 4352 and records['tex_desc']['bytes'] == 64
    spans = []
    for value in re.findall(r'\{0x[0-9a-f]+u,0xffffffffu,0x([0-9a-f]+)u,0xffffffffu\}, /\* GEN7_CP_PROTECT_REG', protect_header):
        v = int(value, 16)
        start = v & 0x3ffff
        spans.append((start, start + ((v >> 18) & 0x1fff)))
    assert len(spans) == 48
    allowed = {'CP_THREAD_CONTROL', 'CP_NON_CONTEXT_REG_BUNCH', 'CP_CONTEXT_REG_BUNCH',
               'CP_LOAD_STATE6_FRAG', 'CP_SET_MARKER', 'CP_EXEC_CS', 'CP_WAIT_FOR_IDLE',
               'CP_EVENT_WRITE7', 'CP_WAIT_REG_MEM'}
    packets, registers, exec_offset, loads = [], [], None, []
    cursor = 0
    parity = lambda n: 1 ^ (n.bit_count() & 1)
    while cursor < count:
        h = words[cursor]
        assert h >> 28 == 7
        n, opcode = h & 0x3fff, (h >> 16) & 0x7f
        assert ((h >> 15) & 1) == parity(n) and ((h >> 23) & 1) == parity(opcode)
        assert cursor + 1 + n <= count
        name = names[opcode]
        assert name in allowed
        data = words[cursor + 1:cursor + 1 + n]
        if name in ('CP_CONTEXT_REG_BUNCH', 'CP_NON_CONTEXT_REG_BUNCH'):
            if name == 'CP_NON_CONTEXT_REG_BUNCH':
                assert data[:2] == (1, 0)
                data = data[2:]
            assert len(data) % 2 == 0
            for reg, value in zip(data[::2], data[1::2]):
                assert not any(lo <= reg <= hi for lo, hi in spans), f'Protected register {reg:x}'
                registers.append((reg, value))
        elif name == 'CP_LOAD_STATE6_FRAG':
            assert n == 3
            address = data[1] | (data[2] << 32)
            assert address in (base + 4096, base + 4352)
            loads.append(address)
        elif name == 'CP_EXEC_CS':
            assert exec_offset is None and data == (0, 1, 1, 1)
            exec_offset = cursor
        elif name == 'CP_EVENT_WRITE7':
            assert data == (0x08000016, (base + 8192) & 0xffffffff, (base + 8192) >> 32, 1) or data == (0x32,)
        elif name == 'CP_WAIT_REG_MEM':
            assert data == (0x13, (base + 8192) & 0xffffffff, (base + 8192) >> 32, 1, 0xffffffff, 16)
        elif name == 'CP_WAIT_FOR_IDLE':
            assert n == 0
        elif name == 'CP_THREAD_CONTROL':
            assert n == 1
        elif name == 'CP_SET_MARKER':
            assert n == 1
        packets.append({'word_offset': cursor, 'opcode': name, 'payload_words': n})
        cursor += n + 1
    assert cursor == count and exec_offset is not None and loads == [base + 4096, base + 4352]
    descriptor = struct.unpack_from('<16I', payload, 4352)
    assert descriptor[1] == 8 and (descriptor[4] | (descriptor[5] << 32)) == base + 256
    assert struct.unpack_from('<8I', payload, 256) == tuple(0xdead0000 + i for i in range(8))
    assert payload[8192:12288] == bytes(4096)
    return {'packets': packets, 'register_writes': [{'index': hex(r), 'value': hex(v)} for r, v in registers],
            'protected_spans_checked': len(spans), 'protected_register_writes': 0,
            'exec_word_offset': exec_offset, 'command_dwords': count,
            'payload_sha256': hashlib.sha256(payload).hexdigest(), 'gpu_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--build', type=Path, default=root / 'work/waffle/gpu/compute-build')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--header', type=Path)
    args = parser.parse_args()
    data = args.payload.read_bytes()
    enums = args.build / 'src/freedreno/registers/adreno/adreno_pm4.xml.h'
    report = audit(data, json.loads(args.manifest.read_text()), enums.read_text(),
                   (root / 'kernel/files/bsd/sys/waffle_gen7_tables.h').read_text())
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if args.header:
        words = struct.unpack('<4096I', data)
        lines = ['#ifndef WAFFLE_GPU_COMPUTE_H', '#define WAFFLE_GPU_COMPUTE_H', '#include <stdint.h>',
                 f'#define WAFFLE_COMPUTE_WORDS {report["command_dwords"]}u',
                 f'#define WAFFLE_COMPUTE_EXEC_WORD {report["exec_word_offset"] + 256}u',
                 'static const uint32_t waffle_compute_payload[4096]={']
        for i in range(0, 4096, 8):
            lines.append('    ' + ','.join(f'0x{x:08x}u' for x in words[i:i+8]) + ',')
        lines += ['};', 'static inline uint32_t waffle_compute_initial(unsigned mode,unsigned word)', '{',
                  '    if(mode==1 && word>=WAFFLE_COMPUTE_EXEC_WORD && word<WAFFLE_COMPUTE_EXEC_WORD+5)',
                  '        return word==WAFFLE_COMPUTE_EXEC_WORD?0x70100004u:0;',
                  '    return waffle_compute_payload[word];', '}',
                  'static inline uint32_t waffle_compute_expected(unsigned mode,unsigned word)', '{',
                  '    if(mode==2 && word>=64 && word<72)return word-64;',
                  '    if(word==2048)return 1;', '    return waffle_compute_initial(mode,word);', '}', '#endif', '']
        args.header.write_text('\n'.join(lines))
    print(json.dumps({'packet_audit': 'passed', 'register_writes': len(report['register_writes']),
                      'protected_conflicts': 0, 'gpu_executed': False}))


if __name__ == '__main__':
    main()
