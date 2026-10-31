"""A cleanup marker alone must never turn a failed capture into success."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('capture', root / 'tools/capture-waffle-native-smmu-state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
good = '''MINIMAL_WINDOW_BEGIN
 task-1 [000] 1.0: meta: (func) base=0xffff000010000000 cb0=0x20000 page=4096 user_cb=0
 task-1 [000] 1.1: cp_done: (func) ret=0
MINIMAL_WINDOW_END
TRACE_CAPTURE_COMPLETE
TRACE_CLEANUP_DONE
'''
assert module.analyze(good)['evidence_valid']
for old, new in (
    ('TRACE_CAPTURE_COMPLETE', ''),
    ('TRACE_CLEANUP_DONE', ''),
    ('MINIMAL_WINDOW_BEGIN', ''),
    ('MINIMAL_WINDOW_END', ''),
    ('cb0=0x20000', 'cb0=0x30000'),
    ('page=4096', 'page=16384'),
    ('user_cb=0', 'user_cb=2'),
    ('base=0xffff000010000000', 'base=0x0'),
    ('ret=0', 'ret=-5'),
    ('cp_done:', 'another_event:'),
    ('meta:', 'another_event:'),
):
    assert not module.analyze(good.replace(old, new))['evidence_valid'], old
failed = "/system/bin/sh: can't create missing/filter: No such file or directory\nTRACE_CLEANUP_DONE\n"
assert not module.analyze(failed)['evidence_valid']
print('Offline SMMU capture classification: valid evidence accepted; cleanup-only, missing fields, wrong geometry and CP failures rejected')
