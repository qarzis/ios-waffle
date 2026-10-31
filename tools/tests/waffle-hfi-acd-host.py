#!/usr/bin/env python3
"""Compare the offline ACD table encoder against full native PJD110 packets."""

from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
trace = root / 'work/waffle/gpu/android-live-audit-20261028/hfi-native-20261028T140555Z.trace'
packets = []
for line in trace.read_text().splitlines():
    if 'hfi_cmd:' not in line or ' id=7 ' not in line:
        continue
    assert 'bytes=276 ' in line
    words = {int(i): int(value, 16) for i, value in
             re.findall(r'\bw(\d+)=(0x[0-9a-f]+)', line)}
    assert sorted(words) == list(range(69))
    packets.append([words[i] for i in range(69)])
assert len(packets) >= 2
assert all(packet[1:] == packets[0][1:] for packet in packets)

expected = packets[0]
expected[0] = (5 << 20) | (69 << 8) | 7
values = ','.join(f'0x{value:08x}u' for value in expected)
code = f'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "waffle_hfi.h"
int main(void) {{
    const uint32_t native[69] = {{{values}}};
    uint32_t packet[70];
    for (unsigned i=0;i<70;++i) packet[i]=0xdeadbeefu;
    assert(waffle_hfi_acd_table_packet(packet,69,5)==69);
    assert(!memcmp(packet,native,sizeof(native)));
    assert(packet[69]==0xdeadbeefu);
    assert(waffle_hfi_acd_table_packet(packet,68,5)==0);
    assert(waffle_hfi_acd_table_packet(packet,69,0)==0);
    assert(waffle_hfi_acd_table_packet(packet,69,4096)==0);
    assert(waffle_hfi_acd_table_packet(NULL,69,5)==0);
    puts("Native ACD table: all 69 words, sequence and boundaries passed");
}}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'test.c'
    binary = Path(directory) / 'test'
    source.write_text(code)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g', '-I',
                    str(root / 'kernel/files/bsd/sys'), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
