"""Actual runner acceptance: require new lifetime, real markers and teardown order."""
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('waffle_runner', root / 'scripts/run_waffle_ios.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
lines = [
    'AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1',
    'full GPU owner returned live to init caller; no mutex held',
    'SESSION fence=1 seq=44 values=56404747/4d444651/12569ade/2569ade1 wrong_words=0',
    'SESSION fence=2 seq=45 values=55434444/4e474552/115599dd/266aaee2 wrong_words=0',
    'SESSION fence=3 seq=46 values=54424545/4f464453/105498dc/276bafe3 wrong_words=0',
    'SMMU_OWNER released after child stop and context detach',
    'CLOCK_OWNER released before CX restore result=1',
    'POWER_OWNER released after clock child, CX and CFG restore result=1',
    'AOP_OWNER released after power child and channel restore result=1 transport=0',
]
module.validate_aop_owner_log('\n'.join(lines))
invalid = ['\n'.join(lines[:i] + lines[i+1:]) for i in range(len(lines))]
invalid += ['\n'.join(lines).replace('wrong_words=0', 'wrong_words=1', 1),
            '\n'.join(lines).replace('56404747', '00000000'),
            '\n'.join(lines).replace('mutex_held=0', 'mutex_held=1'),
            '\n'.join(lines) + '\nREBOOT REQUIRED',
            '\n'.join(lines[:-2] + [lines[-1], lines[-2]])]
for text in invalid:
    try:
        module.validate_aop_owner_log(text)
    except RuntimeError:
        continue
    raise AssertionError('Incomplete or invalid hardware result was accepted')
print('Actual AOP runner validation: positive result, all missing markers, wrong GPU values, held mutex and teardown order checks passed')
