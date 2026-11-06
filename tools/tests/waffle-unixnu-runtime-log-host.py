"""Reject incomplete runtime GPU evidence; fixtures are synthetic, not hardware results."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[2]
validate = runpy.run_path(str(root/'scripts/run_waffle_ios.py'))['validate_unixnu_runtime_log']
lines = [
    'waffle-unixnu-iokit: published=1 PID1_only=1 default_off=1 Metal=0',
    'waffle-unixnu-init: exec runtime probe pid=1',
    'waffle-unixnu-runtime: begin PID=1 CPU_fallback=0',
    'waffle-unixnu-runtime: device=FD750',
    'GENERAL_SUBMIT begin fence=1 seq=44',
    'GENERAL_IB ACK matched seq44 value=00000000 valid=1',
    'GENERAL_SUBMIT done fence=1 seq=44 control=00000001 checked=4096 wrong_words=0',
    'GENERAL submitted fence=1',
    'waffle-unixnu-runtime: checked=4096 filled=4064 guards=32 wrong=0 CPU_fallback=0',
    'GENERAL close passed=1 completed=1 buffers=4 context_null=1',
    'waffle-unixnu-runtime: resources_released=1',
    'waffle-unixnu-runtime: result=1 runtime_API=1 Metal_frontend=0',
]
text = '\n'.join(lines)
assert validate(text)['fences'] == 1
bad_cases = ['\n'.join(lines[:i]+lines[i+1:]) for i in range(len(lines))]
bad_cases += [text.replace(a,b) for a,b in (
    ('wrong=0','wrong=1'), ('buffers=4','buffers=0'),
    ('completed=1','completed=2'), ('control=00000001','control=00000002'),
    ('Metal_frontend=0','Metal_frontend=1'), ('FD750','CPU'),
)]
bad_cases += [text+'\nuncertain=1', '\n'.join(lines[:8]+[lines[9],lines[8]]+lines[10:])]
for index, bad in enumerate(bad_cases):
    try:
        validate(bad)
    except RuntimeError:
        continue
    raise AssertionError(f'Incomplete or corrupt runtime proof accepted: {index}')
print(f'PASS synthetic runtime proof and {len(bad_cases)} missing/corrupt/out-of-order cases; no hardware claim')
