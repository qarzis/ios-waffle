"""Generation/publication proof parser: synthetic positive and corrupt logs."""
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
capacity=8192;budget=134217728
declaration=f'GENERAL open pid=1 BO_limit={capacity} heap_bytes={budget} VA_bytes=268435456 generation_handles=1\n'
def cycle(index):
    handle=1+(index-1)*capacity
    return (f'GENERAL_BO published index={index} VA=100000000 bytes=16384 allocated=16384 flags=20000 pages=4\n'
            f'GENERAL gem_new handle={handle} bytes=16384 allocated=16384 flags=20000 VA=100000000\n'
            f'GENERAL_BO reclaimed index={index} VA=100000000 bytes=16384 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=0\n'
            f'GENERAL bo_retired handle={handle} bytes=16384 backing_retained=0\n')
def release(total):
    return f'GENERAL_BO released after GPU stop and context detach count=0 reclaimed_earlier={total} total={total}\n'
long=declaration+''.join(cycle(i) for i in range(1,8194))+release(8193)
assert len(m.validate_gl_bo_lifetimes(long,capacity,budget,268435456)[0])==8193
assert len(m.validate_gl_bo_lifetimes(long+long,capacity,budget,268435456)[0])==8193
short=declaration+cycle(1)+cycle(2)+release(2)
for bad in [
    long.replace(' generation_handles=1',''),
    short.replace('generation_handles=1','generation_handles=0'),
    short.replace('generation_handles=1','generation_handles=oops'),
    short.replace('generation_handles=1','generation_handles=1 generation_handles=1'),
    short.replace('gem_new handle=8193','gem_new handle=16385'),
    short.replace('bo_retired handle=8193','bo_retired handle=1'),
    short.replace('gem_new handle=8193','gem_new handle=0'),
    short.replace('gem_new handle=8193','gem_new handle=4294967297'),
    short.replace('bytes=16384 allocated=16384 flags=20000 VA=100000000',
                  'bytes=16384 allocated=16384 flags=20000 VA=100004000'),
    short.replace('GENERAL bo_retired handle=1 bytes=16384 backing_retained=0\n',''),
    short.replace('CPU_unmapped=1','CPU_unmapped=0'),
    short.replace('GENERAL gem_new handle=8193 bytes=16384 allocated=16384 flags=20000 VA=100000000\n',''),
]:
    try:m.validate_gl_bo_lifetimes(bad,capacity,budget,268435456)
    except RuntimeError:pass
    else:raise AssertionError('Corrupt generation lifetime proof accepted')
print('HOST parser:8193 issued identities in one reusable slot, exact console replay; legacy cumulative limit retained; malformed modes, missing/mismatched publication, stale/zero/overflow/skipped generations, missing retirement and failed CPU revoke refused. Synthetic logs only.')
