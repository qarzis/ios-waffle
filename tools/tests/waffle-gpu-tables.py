#!/usr/bin/env python3
"""Cross-check captured hardware tables and reject inconsistent capture data."""
import importlib.util
from pathlib import Path
import tempfile
import re

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tables', ROOT / 'tools/build-waffle-gpu-tables.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
capture = ROOT / 'work/waffle/gpu/android-capture2'
result = m.generate(capture)
assert len(result['gx']) == 13 and len(result['cx']) == 3
assert result['gx'][1] == [0x00340201, 0xffffffff, 231000]
assert result['gx'][-1] == [0x0180070c, 0xffffffff, 903000]
assert result['cx'][1:] == [[0x00400202,260000],[0x00800303,625000]]
assert result['packet'][0] == 0x0020340f and len(result['packet']) == 52
header = (ROOT / 'kernel/files/bsd/sys/waffle_hfi_tables.h').read_text()
assert [int(v,16) for v in re.findall(r'0x([0-9a-f]+)u',header)] == result['packet'] + result['bw_packet']
assert len(result['bw_packet']) == 160 and result['bw_packet'][0] == 0x0030a003
assert result['bw_packet'][4:6] == [1,7]
assert result['ddr_rows'][0] == [0x40000000]*3
assert result['ddr_rows'][1] == [0x61bd06f4,0x61c6871a,0x60000000]
assert result['ddr_rows'][6][2] == 0x60000004
assert result['cnoc_rows'] == [[0x40000000],[0x60004001]]
for voltage in (500,):
    try:
        m.arc_vote([0,52,64],[0,64],voltage)
    except ValueError:
        pass
    else:
        raise AssertionError('Unsupported ARC level accepted')
with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    for name in result['sources']:
        (directory / name).write_bytes((capture / name).read_bytes())
    (directory / 'kgsl.txt').write_text('gpu_available_frequencies\n999000000\n')
    try:
        m.generate(directory)
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown live frequency accepted')
    (directory / 'kgsl.txt').write_bytes((capture / 'kgsl.txt').read_bytes())
    (directory / 'cmd-db.txt').write_text('no ARC data')
    try:
        m.generate(directory)
    except ValueError:
        pass
    else:
        raise AssertionError('Missing ARC data accepted')
print('Captured voltage/frequency/HFI table checks passed')
