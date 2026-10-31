#!/usr/bin/env python3
"""Compare a full prepare-only XNU restore list with captured native CP init."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def native_snapshots(path):
    snapshots = []
    for line in path.read_text(errors='replace').splitlines():
        if not re.search(r'bytes=44 id=131\b', line) or not re.search(r'\bw4=0x0*94b\b', line):
            continue
        words = []
        for index, count in ((0, 63), (1, 63), (2, 28)):
            match = re.search(r'\bpwrup' + str(index) + r'=\{([^}]*)\}', line)
            if not match:
                raise ValueError('Native CP init has no complete restore snapshot')
            chunk = [int(word.strip(), 16) for word in match.group(1).split(',')]
            if len(chunk) != count:
                raise ValueError('Native restore chunk size differs')
            words.extend(chunk)
        snapshots.append(words)
    if not snapshots:
        raise ValueError('No matching native CP init with 154 restore words')
    return snapshots


def compare(native, port, probe):
    if f'RESTORE_SNAPSHOT complete probe={probe} words=154; RAW not sent' not in port:
        raise ValueError('Missing complete prepare-only restore marker')
    matches = re.findall(r'RESTORE_SNAPSHOT probe=' + str(probe) + r' word\[([0-9]+)\]=([0-9a-f]{8})', port)
    words = {}
    for index, value in matches:
        index, value = int(index), int(value, 16)
        if index in words and words[index] != value:
            raise ValueError('Conflicting snapshot words')
        words[index] = value
    if set(words) != set(range(154)):
        raise ValueError('Expected exactly 154 unique indexed snapshot words')
    actual = [words[i] for i in range(154)]
    reference = native[0]
    if any(snapshot[3::2] != reference[3::2] or snapshot[4::2] != reference[4::2] for snapshot in native[1:]):
        raise ValueError('Native restore payload differs across captured CP init packets')
    differences = []
    for pair in range(75):
        i = 4 + pair * 2
        if actual[i:i+2] != reference[i:i+2]:
            differences.append({'pair': pair, 'native_register': hex(reference[i]),
                                'port_register': hex(actual[i]), 'native_value': hex(reference[i+1]),
                                'port_value': hex(actual[i+1])})
    return {'native_snapshots': len(native), 'native_header': reference[:4], 'port_header': actual[:4],
            'lock_flags_clear': actual[0:2] == [0, 0], 'turn_in_range': actual[2] in (0, 1),
            'list_lengths_match': actual[3] == reference[3], 'register_pairs': 75,
            'register_order_match': actual[4::2] == reference[4::2],
            'pair_differences': differences, 'native_words': reference, 'port_words': actual,
            'cp_ack_confirmed': False, 'frame_confirmed': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--port', type=Path, required=True)
    p.add_argument('--probe', type=int, default=60)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = compare(native_snapshots(a.native), a.port.read_text(errors='replace'), a.probe)
    report['sources'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.native, a.port)}
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('native_words', 'port_words')}, indent=2))


if __name__ == '__main__':
    main()
