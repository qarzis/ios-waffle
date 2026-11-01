"""E64 timing proof requires every independently checked alternating frame."""
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bench',root/'tools/analyze-waffle-readback-benchmark.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
text='''waffle-gl-bench: begin frames=240 width=750 height=1624 inverted=0 CPU_reference_outside_timing=1 panel_FPS=0
waffle-gl-hook: attachImage=1 surface=7 inverted=0
'''+''.join(f'waffle-gl-bench: frame={i} render_and_readback_us={5000+i} checked=1218000 wrong=0 blue={int(i%2==0)}\n' for i in range(240))+'''waffle-gl-bench: result=1 frames=240 checked=292320000 wrong=0 inverted=0 panel_FPS=0
'''
assert m.frames(text)==list(range(5000,5240))
assert m.frames(text+text)==list(range(5000,5240))
for bad in [text.replace('frame=239','frame=238'),text.replace('checked=1218000','checked=256'),
            text.replace('wrong=0 blue=1','wrong=1 blue=1'),text.replace('blue=1','blue=0'),
            text.replace('surface=7 inverted=0','surface=7 inverted=1'),
            text.replace('render_and_readback_us=5000','render_and_readback_us=0'),
            text.replace('result=1 frames=240','result=0 frames=240')]:
    try:m.frames(bad)
    except RuntimeError:pass
    else:raise AssertionError('Invalid frame/pixel/timing proof accepted')
assert m.summary([1,2,3,4])['median_us']==2.5
print('HOST benchmark proof:240 complete alternating fullsize checked frames/exact console replay accepted; missing/conflicting frame, partial/wrong pixels, wrong orientation, zero timing and failed result refused. Synthetic logs only; not a GPU/FPS result.')
