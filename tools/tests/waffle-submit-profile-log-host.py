"""Sample schedule/completeness/conflict checks for phase timing reports."""
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('p',root/'tools/analyze-waffle-submit-profile.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ids=list(range(1,17))+[128,256,384]
text=''.join('GENERAL_PROFILE fence='+str(i)+' '+' '.join(name+'_us='+str(n+1) for n,name in enumerate(m.FIELDS))+'\n' for i in ids)
assert len(m.samples(text,482))==19 and m.samples(text+text,482)==m.samples(text,482)
for bad in [text.replace('fence=128','fence=129'),text.replace('stage_us=2','stage_us=-1'),text+text.replace('stage_us=2','stage_us=3')]:
    try:m.samples(bad,482)
    except RuntimeError:pass
    else:raise AssertionError('Incomplete/conflicting phase proof accepted')
print('HOST phase proof:exact sampled schedule/replay accepted; missing, unexpected, negative and conflicting values refused. Synthetic timing only.')
