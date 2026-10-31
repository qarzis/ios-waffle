#!/usr/bin/env python3
"""Check native power evidence classification against saved trace mutations."""
from pathlib import Path
import importlib.util
import re

root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_power',root/'tools/capture-waffle-native-power.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
trace=(root/'work/waffle/gpu/android-live-audit-20261030/power-native-20261030T203201Z.trace').read_text()
report=module.analyze(trace)
assert report['evidence_valid'] and report['paired_cp_successes']==1
assert report['cp_entry_clocks'][0]['last_gmu_rate_Hz']==260000000
assert not module.analyze(trace.replace('MINIMAL_WINDOW_END','INCOMPLETE'))['evidence_valid']
assert not module.analyze(trace.replace('ret=0','ret=-5'))['evidence_valid']
assert not module.analyze(trace.replace('hz=625000000','hz=260000000'))['evidence_valid']
assert not module.analyze('\n'.join(line for line in trace.splitlines() if ': voltage_done:' not in line))['evidence_valid']
assert not module.analyze('\n'.join(line for line in trace.splitlines() if ': cp_done:' not in line))['evidence_valid']
assert not module.analyze(re.sub(r'min=192\b','min=128',trace))['evidence_valid']
assert not module.analyze(re.sub(r'min=128\b','min=56',trace))['evidence_valid']
print('Native power capture: paired success; missing window/returns, failures, missing625/MX192/CX128 rejected; CP clock260 established')
