#!/usr/bin/env python3
"""Generate Gen7 HFI performance table from this phone's captured DT and cmd-db.
Does not request a voltage/frequency or communicate with the phone.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('waffle_fdt', ROOT / 'tools/check-waffle-dtb.py')
fdt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fdt)


def arc_vote(primary, secondary, voltage):
    index = next((i for i, v in enumerate(primary) if v >= voltage), None)
    if index is None:
        raise ValueError(f'Unsupported voltage level {voltage}')
    level = primary[index]
    dep = next((i for i, v in enumerate(secondary) if v >= level), len(secondary) - 1)
    return level << 16 | dep << 8 | index


def generate(directory):
    names = ('android-live.dtb', 'cmd-db.txt', 'kgsl.txt')
    source = {name: (directory / name).read_bytes() for name in names}
    nodes = fdt.parse_fdt(source['android-live.dtb'])
    gpu = '/soc/qcom,kgsl-3d0@3d00000'
    if struct.unpack('>I', nodes[gpu]['qcom,chipid'])[0] != 0x43051401:
        raise ValueError('Expected the captured Adreno750v2')
    arcs = {}
    for name in ('gfx.lvl', 'cx.lvl', 'mx.lvl'):
        match = re.search(rb'0x([0-9a-f]+): ' + re.escape(name.encode()) + rb'\x00* \[([^]]+)\]', source['cmd-db.txt'])
        if not match:
            raise ValueError(f'Missing cmd-db resource {name}')
        data = bytes.fromhex(match[2].decode())
        values = list(struct.unpack('<' + 'H' * (len(data) // 2), data))
        while len(values) > 1 and values[-1] == 0:
            values.pop()
        if values[0] != 0 or values != sorted(set(values)):
            raise ValueError('Malformed ARC levels')
        arcs[name] = {'address': int(match[1], 16), 'levels': values}
    text = source['kgsl.txt'].decode()
    match = re.search(r'gpu_available_frequencies\s+([\d ]+)\n', text)
    if not match:
        raise ValueError('Missing Android frequency list')
    freqs = list(map(int, match[1].split()))
    if not freqs or freqs != sorted(set(freqs), reverse=True):
        raise ValueError('Malformed frequency list')
    bins = []
    for path in nodes:
        if path.startswith(gpu + '/qcom,gpu-pwrlevel-bins/') and path.count('/') == 4:
            rows = []
            for child, props in nodes.items():
                if child.startswith(path + '/') and 'qcom,gpu-freq' in props:
                    def u32(key, default=None):
                        return struct.unpack('>I', props[key])[0] if key in props else default
                    rows.append((u32('reg'), u32('qcom,gpu-freq'), u32('qcom,level'), u32('qcom,cx-level', 0xffffffff)))
            rows.sort()
            if [r[1] for r in rows] == freqs:
                bins.append((path, rows))
    if not bins or any(rows != bins[0][1] for _, rows in bins):
        raise ValueError('No unique voltage table matches the live Android frequencies')
    gx = [[0, 0xffffffff, 0]]
    for _, freq, voltage, cx in reversed(bins[0][1]):
        cx_vote = 0xffffffff if cx == 0xffffffff else next(i for i, v in enumerate(arcs['cx.lvl']['levels']) if v >= cx)
        gx.append([arc_vote(arcs['gfx.lvl']['levels'], arcs['mx.lvl']['levels'], voltage), cx_vote, freq // 1000])
    gmu = list(struct.unpack('>4I', nodes['/soc/qcom,gmu@3d69000']['qcom,gmu-freq-table']))
    cx = [[0, 0]] + [[arc_vote(arcs['cx.lvl']['levels'], arcs['mx.lvl']['levels'], gmu[i+1]), gmu[i] // 1000] for i in (0, 2)]
    if len(gx) > 32:
        raise ValueError('Too many levels')
    # HFI>=2.6.1 TABLE(version0,typeGPU_PERF1), entries have count/stride.
    words = [0, 0, 1, len(gx), 3] + [v for row in gx for v in row] + [len(cx), 2] + [v for row in cx for v in row]
    words[0] = 2 << 20 | len(words) << 8 | 15
    if len(words) > 200:
        raise ValueError('HFI table exceeds packet bound')
    bcms = {}
    for name in ('SH0','MC0','ACV','CN0'):
        match = re.search(rb'0x([0-9a-f]+): ' + name.encode() + rb'\x00* \[([^]]+)\]', source['cmd-db.txt'])
        if not match:
            raise ValueError(f'Missing BCM {name}')
        raw = bytes.fromhex(match[2].decode())
        unit, width, vcd, _ = struct.unpack('<IHBB', raw)
        if not unit or (name != 'ACV' and not width):
            raise ValueError('Invalid BCM units')
        bcms[name] = {'address':int(match[1],16), 'unit':unit, 'width':width, 'vcd':vcd}
    ddr = list(struct.unpack('>10I', nodes[gpu]['qcom,bus-table-ddr']))
    cnoc = list(struct.unpack('>2I', nodes[gpu]['qcom,bus-table-cnoc']))
    if ddr[0] or ddr != sorted(set(ddr)) or cnoc != [0,100]:
        raise ValueError('Unexpected bus levels')
    # Gen7.9.1 profile: ACV BIT2 starting at MHZ_TO_KBPS(2736,4).
    threshold = 2736 * 1000000 * 4 // 1024
    def bw_rows(names, levels):
        rows = []
        wait = 0
        for level in levels:
            row = []
            for i,name in enumerate(names):
                bcm = bcms[name]
                commit = i == len(names)-1 or bcm['vcd'] != bcms[names[i+1]]['vcd']
                if commit:
                    wait |= 1 << i
                if name == 'ACV':
                    x, y, valid = 0, 4 if level >= threshold else 0, bool(level)
                else:
                    buswidth = 16 if name == 'SH0' else 4
                    scaled = level * bcm['width'] // buswidth
                    x = y = min(16383, max(1 if level else 0, scaled * 1000 // bcm['unit']))
                    valid = bool(x or y)
                row.append(int(commit) << 30 | int(valid) << 29 | x << 14 | y)
            rows.append(row)
        return rows, wait
    ddr_rows, ddr_wait = bw_rows(['SH0','MC0','ACV'],ddr)
    cnoc_rows, cnoc_wait = bw_rows(['CN0'],cnoc)
    # Legacy BW_VOTE_TBL fixed arrays:6CNOC commands,2levels,8DDR commands,16levels.
    bw = [0,len(ddr),1,3,cnoc_wait,ddr_wait]
    bw += [bcms['CN0']['address']] + [0]*5
    for row in cnoc_rows:
        bw += row + [0]*5
    bw += [bcms[name]['address'] for name in ('SH0','MC0','ACV')] + [0]*5
    for i in range(16):
        bw += ddr_rows[i] + [0]*5 if i < len(ddr_rows) else [0]*8
    assert len(bw) == 160
    bw[0] = 3 << 20 | len(bw) << 8 | 3
    return {'sources': {n: hashlib.sha256(b).hexdigest() for n,b in source.items()},
            'matching_bins': [p for p,_ in bins], 'arcs': arcs, 'gx': gx, 'cx': cx,
            'packet': words, 'bcms':bcms, 'ddr_levels':ddr, 'cnoc_levels':cnoc,
            'ddr_rows':ddr_rows, 'cnoc_rows':cnoc_rows, 'bw_packet':bw}



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--json', type=Path, required=True)
    p.add_argument('--header', type=Path, required=True)
    args = p.parse_args()
    data = generate(args.capture)
    args.json.write_text(json.dumps(data, indent=2) + '\n')
    words = data['packet']
    text = '/* Generated from captured PJD110 DT/Android cmd-db; no power request. */\n'
    text += '#ifndef WAFFLE_HFI_TABLES_H\n#define WAFFLE_HFI_TABLES_H\n'
    text += 'static const uint32_t waffle_hfi_perf_table[] = {\n'
    text += ''.join('    ' + ', '.join(f'0x{x:08x}u' for x in words[i:i+6]) + ',\n' for i in range(0,len(words),6))
    text += '};\nstatic const uint32_t waffle_hfi_bw_table[] = {\n'
    bw = data['bw_packet']
    text += ''.join('    ' + ', '.join(f'0x{x:08x}u' for x in bw[i:i+6]) + ',\n' for i in range(0,len(bw),6))
    text += '};\n#endif\n'
    args.header.write_text(text)
    print(f'Generated {len(data["gx"])} GPU/{len(data["cx"])} GMU levels, {len(words)} words; no votes sent')


if __name__ == '__main__':
    main()
