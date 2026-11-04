#!/usr/bin/env python3
"""Reject battery diagnostics outside the isolated DSP path before USB access."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
for script, prefix in [('scripts/run_waffle_ios.py', []),
                       ('tools/run-waffle-auto.py', ['--artifact', '/nonexistent-battery-fixture'])]:
    cases = [(['--battery-readonly'], 'requires isolated --audio-boot'),
             (['--battery-report-test'], 'requires --battery-readonly'),
             (['--battery-readonly', '--audio-preflight', '--audio-boot', '--audio-graph'],
              'requires isolated --audio-boot'),
             (['--battery-readonly', '--audio-preflight', '--audio-boot', '--cpus', '7'],
              'isolated test' if script.startswith('scripts/') else 'separately from other diagnostics')]
    for args, expected in cases:
        result = subprocess.run([sys.executable, str(root / script), *prefix, *args],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode and expected in result.stderr, (script, args, result.stderr)
print('PASS actual battery CLI: standalone, graph combination and multicore load rejected before artifact/USB access')
