#!/usr/bin/env python3
"""Extract pinned Gen7.9.1 startup tables. Offline only; no device access.

Register offsets are DWORD indices in the native GPU/GMU register map.
They are not physical addresses and require domain-aware access in the driver.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def generate(vendor):
    names = ('gen7_reg.h', 'adreno-gpulist.h', 'adreno_gen7.c')
    pins = json.loads((vendor / 'SHA256.json').read_text())
    sources = {name: (vendor / name).read_bytes() for name in names}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
    if any(hashes[name] != pins[name] for name in names):
        raise ValueError('Native source hash mismatch')
    regs = {name: int(value, 0) for name, value in re.findall(
        r'^#define\s+(GEN7_\w+)\s+(0x[0-9a-fA-F]+|[0-9]+)\s*$',
        sources['gen7_reg.h'].decode(), re.M)}
    core = sources['adreno-gpulist.h'].decode()
    startup = sources['adreno_gen7.c'].decode()

    def body(text, name):
        match = re.search(r'\b' + re.escape(name) + r'\[\]\s*=\s*\{(.*?)\n\};', text, re.S)
        if not match:
            raise ValueError(f'Missing native table {name}')
        return re.sub(r'/\*.*?\*/', '', match[1], flags=re.S)

    def resolve(expression):
        match = re.fullmatch(r'\s*(GEN7_\w+)\s*(?:\+\s*(\d+))?\s*', expression)
        if not match:
            raise ValueError(f'Unsupported register expression {expression!r}')
        return regs[match[1]] + int(match[2] or 0)

    def pairs(name):
        text = body(core, name)
        rows = re.findall(r'\{\s*(GEN7_\w+)\s*,\s*(0x[0-9a-fA-F]+)\s*\}', text)
        if not rows or re.sub(r'\{[^{}]+\}|[\s,]', '', text):
            raise ValueError(f'Unparsed pair table {name}')
        return [{'register': name, 'offset': resolve(name), 'value': int(value, 0)}
                for name, value in rows]

    def restore(name):
        return [{'register': entry.strip(), 'offset': resolve(entry)}
                for entry in body(startup, name).split(',') if entry.strip()]

    protected = []
    text = body(core, 'gen7_9_0_protected_regs')
    rows = re.findall(r'\{\s*(GEN7_CP_PROTECT_REG\s*\+\s*\d+)\s*,\s*'
                      r'(0x[0-9a-f]+)\s*,\s*(0x[0-9a-f]+)\s*,\s*([01])\s*\}', text)
    if len(rows) != 48 or re.sub(r'\{[^{}]+\}|[\s,]', '', text):
        raise ValueError('Expected 48 native protection spans and a sentinel')
    for index, (register, start, end, noaccess) in enumerate(rows):
        lo, hi, deny = int(start, 0), int(end, 0), int(noaccess)
        offset = resolve(register)
        if offset != regs['GEN7_CP_PROTECT_REG'] + index or not 0 <= lo <= hi < 1 << 18 or hi-lo >= 1 << 13:
            raise ValueError('Unrepresentable native protection span')
        protected.append({'register': register, 'offset': offset, 'start': lo,
                          'end': hi, 'noaccess': deny, 'value': lo | (hi-lo) << 18 | deny << 31})
    ifpc = restore('gen7_ifpc_pwrup_reglist') + restore('gen7_9_x_ifpc_pwrup_reglist')
    preemption = restore('gen7_pwrup_reglist')
    if len(ifpc) > 255 or len(preemption) > 255:
        raise ValueError('Restore list does not fit native u8 count')
    # Pinned gen7_start, for the captured Gen7.9.1 profile: LPDDR5,
    # MAL32, UBWC4, highest bank16, GMEM3MiB, no LPAC/preemption/DMS/LLCC.
    # HWCG's command/status handshake is intentionally a separate next step.
    setup = []
    def write(name, value, mask=0xffffffff):
        setup.append({'register': name, 'offset': resolve(name), 'value': value, 'mask': mask})
    for row in pairs('gen7_0_0_gbif_regs'):
        write(row['register'], row['value'])
    for name, value in (
        ('GEN7_UCHE_GBIF_GX_CONFIG',0x10240e0),
        ('GEN7_RBBM_PERFCTR_GPU_BUSY_MASKED',0xffffffff),
        ('GEN7_UCHE_TRAP_BASE_LO',0xfffff000),('GEN7_UCHE_TRAP_BASE_HI',0x1ffff),
        ('GEN7_UCHE_WRITE_THRU_BASE_LO',0xfffff000),('GEN7_UCHE_WRITE_THRU_BASE_HI',0x1ffff),
        ('GEN7_UCHE_GMEM_RANGE_MIN_LO',0x1000000),('GEN7_UCHE_GMEM_RANGE_MIN_HI',0),
        ('GEN7_UCHE_GMEM_RANGE_MAX_LO',0x12fffff),('GEN7_UCHE_GMEM_RANGE_MAX_HI',0),
        ('GEN7_UCHE_CACHE_WAYS',0x800000),('GEN7_UCHE_CMDQ_CONFIG',0x6690e),
        ('GEN7_GMU_CX_GMU_POWER_COUNTER_SELECT_1',4),
        ('GEN7_RB_NC_MODE_CNTL',0x816),('GEN7_TPL1_NC_MODE_CNTL',6),
        ('GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_1',0x3fe05ff4),
        ('GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_2',0x3fa0ebee),
        ('GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_3',0x3f5193ed),
        ('GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_4',0x3f0243f0),
        ('GEN7_SP_NC_MODE_CNTL',0x26),('GEN7_GRAS_NC_MODE_CNTL',0x60),
        ('GEN7_UCHE_MODE_CNTL',0x600000),
        ('GEN7_RBBM_INTERFACE_HANG_INT_CNTL',0x40cfffff),
        ('GEN7_UCHE_CLIENT_PF',0x81)):
        write(name,value)
    write('GEN7_RB_CMP_DBG_ECO_CNTL',1<<19,1<<19)
    write('GEN7_TPL1_DBG_ECO_CNTL1',0xc0700)
    write('GEN7_GPU_GMU_AO_GPU_CX_BUSY_MASK',0xff000000)
    write('GEN7_GMU_CX_GMU_POWER_COUNTER_SELECT_0',0x20,0xff)
    write('GEN7_GMU_CX_GMU_POWER_COUNTER_ENABLE',1)
    write('GEN7_CP_PROTECT_CNTL',0xb)
    for row in protected:
        write(row['register'],row['value'])
    for name,value in (('GEN7_CP_APRIV_CNTL',0x6f),('GEN7_CP_BV_APRIV_CNTL',0xf),
                       ('GEN7_CP_LPAC_APRIV_CNTL',0xf),('GEN7_CP_AQE_APRIV_CNTL',1)):
        write(name,value)
    write('GEN7_GBIF_CX_CONFIG',1<<29,7<<29)
    # The live protected pool's aperture, deliberately different from stock's
    # f0000000. No protected data is accessed by the CPU here.
    for name,value in (('GEN7_RBBM_SECVID_TSB_CNTL',0),
                       ('GEN7_RBBM_SECVID_TSB_TRUSTED_BASE_LO',0xa0000000),
                       ('GEN7_RBBM_SECVID_TSB_TRUSTED_BASE_HI',0),
                       ('GEN7_RBBM_SECVID_TSB_TRUSTED_SIZE',0x400000)):
        write(name,value)
    if len({r['offset'] for r in setup}) != len(setup):
        raise ValueError('Duplicate configuration register')
    for row in setup + ifpc + preemption:
        offset=row['offset']*4
        if not (offset < 0x40000 or 0x68000 <= offset < 0x9f000):
            raise ValueError(f'Register outside mapped GPU/GMU domains: {row}')
    for row in setup:
        row['readback_mask']=row['mask']
        if row['register']=='GEN7_RBBM_PERFCTR_GPU_BUSY_MASKED':
            # Target hardware run20261025T072503Z: 0 -> writeffffffff ->
            # read002f7fff -> write0 -> read0. Keep the exact native write;
            # compare the observed readable bits rather than reserved zeros.
            row['readback_mask']=0x002f7fff
        if row['register']=='GEN7_UCHE_GMEM_RANGE_MAX_LO':
            # Run20261025T072927Z: native012fffff reads012ff000; the upper
            # endpoint is represented by the base of its final4KiB page.
            row['readback_mask']=0xfffff000
    return {'target': 'Adreno750v2 / Gen7.9.1', 'sources': hashes,
            'offset_units': 'DWORD; native register-map domain, not physical addresses',
            'hardware_tested': False, 'runtime_integrated': False,
            'gbif': pairs('gen7_0_0_gbif_regs'),
            'gmu_ao_hwcg': pairs('gen7_2_0_ao_hwcg_regs'),
            'protected': protected, 'ifpc_restore': ifpc,
            'preemption_restore': preemption,
            'disabled_setup':setup,
            'cpu_gpu_lock_bytes': 16,
            'static_restore_bytes': 16 + 8 * (len(ifpc) + len(preemption))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, default=ROOT/'work/waffle/gpu/vendor')
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--header', type=Path)
    args = parser.parse_args()
    data = generate(args.vendor)
    args.json.write_text(json.dumps(data, indent=2) + '\n')
    if args.header:
        header='/* Generated from pinned OnePlus Gen7.9.1; DWORD register indices. */\n'
        header+='#ifndef WAFFLE_GEN7_TABLES_H\n#define WAFFLE_GEN7_TABLES_H\n'
        header+='struct waffle_gen7_write { uint32_t index, mask, value, readback_mask; };\n'
        header+='static const struct waffle_gen7_write waffle_gen7_disabled_setup[] = {\n'
        header+=''.join(f'    {{0x{r["offset"]:x}u,0x{r["mask"]:08x}u,0x{r["value"]:08x}u,0x{r["readback_mask"]:08x}u}}, /* {r["register"]} */\n' for r in data['disabled_setup'])
        header+='};\n'
        header+='static const struct waffle_gen7_write waffle_gen7_ao_hwcg[] = {\n'
        header+=''.join(f'    {{0x{r["offset"]:x}u,0xffffffffu,0x{r["value"]:08x}u,0xffffffffu}},\n' for r in data['gmu_ao_hwcg'])
        header+='};\n'
        for name in ('GEN7_RBBM_CLOCK_CNTL_GLOBAL','GEN7_RBBM_CGC_GLOBAL_LOAD_CMD',
                     'GEN7_RBBM_CGC_P2S_TRIG_CMD','GEN7_RBBM_CGC_P2S_STATUS'):
            # Literal identifiers remain tied to the same pinned register map.
            value=int(re.search(r'^#define\s+'+name+r'\s+(0x[0-9a-fA-F]+)',
                (args.vendor/'gen7_reg.h').read_text(),re.M)[1],16)
            header+=f'#define WAFFLE_{name} 0x{value:x}u\n'
        for name in ('ifpc_restore','preemption_restore'):
            header+=f'static const uint32_t waffle_gen7_{name}[] = {{\n'
            header+=''.join(f'    0x{r["offset"]:x}u, /* {r["register"]} */\n' for r in data[name])
            header+='};\n'
        header+='#endif\n'
        args.header.write_text(header)
    print(f"Extracted {len(data['protected'])} protected spans, "
          f"{len(data['ifpc_restore'])}+{len(data['preemption_restore'])} restore pairs; no device access")


if __name__ == '__main__':
    main()
