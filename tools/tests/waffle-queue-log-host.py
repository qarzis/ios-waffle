"""Focused queue-recycle proof validator: synthetic positive/corruption twins."""
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
text='GENERAL open pid=1 queue_generations=1\nwaffle-gl-queue: begin cycles=100 existing_Mesa_context=1\n'
text+=''.join(f'GENERAL queue_new id={2+i*32} priority=0 serialized=1\n' for i in range(100))
text+='''GENERAL request flags=10 fence=0 bos=1 roots=1 queue=2
GENERAL ioctl_refused op=46 error=22
GENERAL request flags=10 fence=0 bos=1 roots=1 queue=3170
waffle-gl-queue: result=1 cycles=100 queue=3170 stale=2 stale_submit_refused=1
'''
m.validate_gl_queue_recycle_log(text,3)
for bad in [text.replace('queue_generations=1','queue_generations=0'),
            text.replace('id=3170 priority=0 serialized=1','missing queue'),
            text.replace('stale_submit_refused=1','stale_submit_refused=0'),
            text.replace('GENERAL ioctl_refused op=46 error=22',''),
            text.replace('queue=3170 stale=2','queue=2 stale=2'),
            text.replace('roots=1 queue=3170','roots=1 queue=2'),
            text+'waffle-gl-queue: result=0\n']:
    try:m.validate_gl_queue_recycle_log(bad,3)
    except RuntimeError:pass
    else:raise AssertionError('Corrupt queue lifetime proof accepted')
print('HOST parser:100 created queue IDs/current3170/stale2 refusal then new submit; malformed mode, missing IDs/refusal, wrong generations/submission, failed probe refused. Synthetic logs only.')
