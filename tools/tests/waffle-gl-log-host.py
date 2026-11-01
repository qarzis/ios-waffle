"""GL hardware acceptance parser rejects synthetic incomplete/stale/CPU-only proofs."""
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2];spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
text='''GENERAL registered root_only=1 gated=1 BO_limit=32
waffle-gl-init: exec actual Darwin Mesa probe pid=1
waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16
AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1
full GPU owner returned live to init caller; no mutex held
SERVICE begin root_live=1 serialized=1
GENERAL open pid=1 BO_limit=32 heap_bytes=33554432
GENERAL_BO published index=1 VA=100000000 bytes=4096 allocated=16384 flags=20000 pages=4
waffle-gl-user: renderer=FD750 version=OpenGL Mesa
GENERAL_SUBMIT begin fence=1 seq=44 root_words=310 kernel_tail=15 extra_IB_depth=0
GENERAL_IB ACK matched seq44 value=00000000 valid=1
GENERAL_SUBMIT done fence=1 seq=44 control=00000001 checked=4096 wrong_words=0
GENERAL submitted fence=1 bos=1 roots=1 words=310
waffle-gl-user: checked=256 wrong=0 filled=128 GL_error=0
'''
pixels=[0xff0040ff if 4*x+2>2*y+1 and 4*x+2<63-2*y else 0xff000000 for y in range(16) for x in range(16)]
for offset in range(0,256,8):text+=f'waffle-gl-user: pixels offset={offset} values='+('/'.join(f'{v:08x}' for v in pixels[offset:offset+8]))+'\n'
text+='''GENERAL_BO released after GPU stop and context detach count=1
SMMU_OWNER released after child stop and context detach
CLOCK_OWNER released before CX restore result=1
POWER_OWNER released after clock child, CX and CFG restore result=1
AOP_OWNER released after power child and channel restore result=1 transport=0
SERVICE end consumed=1 result=1
GENERAL close passed=1 completed=1 buffers=1 context_null=1
waffle-gl-user: result=1 actual_OSMesa=1
'''
assert m.validate_gl_log(text)==pixels
for marker,replacement in [('GENERAL_SUBMIT done fence=1','GENERAL_SUBMIT done fence=2'),('control=00000001','control=00000000'),('renderer=FD750','renderer=softpipe'),('ff0040ff','dead0000'),('context_null=1','context_null=0'),('GENERAL_BO released','MISSING'),('flags=20000','flags=80000'),('VA=100000000','VA=100000001')]:
 try:m.validate_gl_log(text.replace(marker,replacement))
 except RuntimeError:pass
 else:raise AssertionError('Invalid GL hardware proof accepted: '+marker)
print('GL acceptance parser:actual pixel completeness,FD750 renderer,GPU tokens/ACK/sequence,BO ranges/permissions/free/context stop and8 corrupted-proof refusals; synthetic host fixture only')

# Budget-derived capacity is accepted only with its matching physical heap.
updated=text.replace('BO_limit=32','BO_limit=4096').replace('heap_bytes=33554432','heap_bytes=67108864')
assert m.validate_gl_log(updated)==pixels
try:m.validate_gl_log(updated.replace('heap_bytes=67108864','heap_bytes=33554432'))
except RuntimeError:pass
else:raise AssertionError('Inconsistent capacity/physical budget accepted')
larger=updated.replace('BO_limit=4096','BO_limit=8192').replace('heap_bytes=67108864','heap_bytes=134217728')
assert m.validate_gl_log(larger)==pixels
for bad in [larger.replace('heap_bytes=134217728','heap_bytes=67108864'),
            larger.replace('BO_limit=8192','BO_limit=4096')]:
 try:m.validate_gl_log(bad)
 except RuntimeError:pass
 else:raise AssertionError('Inconsistent128MiB descriptor capacity accepted')

# UI acceptance remains independent of off-screen GL pixel proofs. A declared
# observation window must match the actual stop, with real presentation markers.
ui=updated.replace('GENERAL open pid=1', 'GENERAL open pid=83')+'''
waffle-ui-init: GPU device owner=501 mode=600 chown=0 chmod=0 RAM_only=1
waffle-ui-gpu: selected process=backboardd pid=83 uid=501 bounded=1
FD750; shaders OpenGL ES GLSL ES 3.20
waffle-ui-gpu: bounded process stop pid=83 seconds=30
redwood-gl: frame 1: 136 GL calls, 4 draws
MiniIOMobileFramebuffer: swap 1 layer 0: surface 7 (
'''
assert m.validate_ui_workload_log(ui)['actual_backboardd_pid']==83
ui60=ui.replace('bounded=1\n','bounded=1 stop_seconds=60\n').replace('seconds=30','seconds=60')
assert m.validate_ui_workload_log(ui60)['GPU_fences']==1
ui240=ui60.replace('seconds=60','seconds=240')
assert m.validate_ui_workload_log(ui240)['GPU_fences']==1
for bad in [ui60.replace('stop_seconds=60','stop_seconds=90'),
            ui60.replace('pid=83 seconds=60','pid=83 seconds=30'),
            ui60.replace('MiniIOMobileFramebuffer: swap','missing swap'),
            ui60.replace('context_null=1','context_null=0')]:
 try:m.validate_ui_workload_log(bad)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete or mismatched bounded UI proof accepted')
print('UI observation-window proof: legacy30/declared60 accepted; unknown/mismatched window, missing presentation and failed teardown refused; synthetic host fixtures only')

pub1='GENERAL_BO published index=1 VA=100000000 bytes=4096 allocated=16384 flags=20000 pages=4'
pub2=pub1.replace('index=1','index=2')
freed='GENERAL_BO reclaimed index=1 VA=100000000 bytes=16384 CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=0'
release='GENERAL_BO released after GPU stop and context detach count=1 reclaimed_earlier=1 total=2'
reuse=text.replace(pub1,pub1+'\n'+freed+'\n'+pub2).replace(
 'GENERAL_BO released after GPU stop and context detach count=1',release).replace('completed=1 buffers=1','completed=1 buffers=2')
assert m.validate_gl_log(reuse)==pixels
for bad in [reuse.replace(freed+'\n',''),reuse.replace('CPU_unmapped=1','CPU_unmapped=0'),
            reuse.replace('dual_ASID_TLBI=1','dual_ASID_TLBI=0'),
            reuse.replace('reclaimed index=1 VA=100000000','reclaimed index=1 VA=100004000'),
            reuse.replace('used=0','used=16384'),reuse.replace('reclaimed_earlier=1 total=2','reclaimed_earlier=0 total=2'),
            reuse.replace(release,'GENERAL_BO released after GPU stop and context detach count=2')]:
 try:m.validate_gl_log(bad)
 except RuntimeError:pass
 else:raise AssertionError('Corrupt early-reclaim lifetime proof accepted')
life=pub1+'\n'+freed+'\n'+pub2+'\n'+release+'\n'
assert len(m.validate_gl_bo_lifetimes(life+life,32,33554432)[0])==2 # loader console replay
try:m.validate_gl_bo_lifetimes(life+freed.replace('index=1','index=2')+'\n',32,33554432)
except RuntimeError:pass
else:raise AssertionError('First revocation after context detach accepted')
print('GL BO lifetime proof: exact console replays and revoked-hole reuse accepted; missing revocation, CPU/TLB/VA/accounting/teardown corruption and post-detach new lifetime events refused; synthetic fixtures only')
longrun='\n'.join(f'GENERAL_SUBMIT done fence={f} seq={m.gl_sequence(f-1)} control={f:08x} checked=4096 wrong_words=0' for f in range(1,10001))
assert m.gl_completed_fences(longrun)==10000
for before in [1024,4051,8145]:
 bad=longrun.replace(f'fence={before} seq={m.gl_sequence(before-1)}',f'fence={before} seq=4095')
 try:m.gl_completed_fences(bad)
 except RuntimeError:pass
 else:raise AssertionError('Wrong wrapped HFI sequence accepted')
print('GL fences:10000 monotonic32bit tokens with bounded HFI tags; corrupted former1024/tag-wrap boundaries refused; synthetic fixtures only')
split=reuse.replace('BO_limit=32','BO_limit=8192').replace('heap_bytes=33554432','heap_bytes=134217728 VA_bytes=268435456')
split=split.replace(pub2,pub2.replace('VA=100000000','VA=108000000'))
assert m.validate_gl_log(split)==pixels
for bad in [split.replace('VA_bytes=268435456','VA_bytes=134217728'),
            split.replace('VA_bytes=268435456','VA_bytes=536870912'),
            split.replace('VA_bytes=268435456','VA_bytes=oops'),
            split.replace('index=2 VA=108000000','index=2 VA=110000000')]:
 try:m.validate_gl_log(bad)
 except RuntimeError:pass
 else:raise AssertionError('Invalid split physical/virtual budget proof accepted')
print('GL separated budgets:128MiB residency/256MiB virtual placement accepted; wrong/malformed/unqualified VA declaration and out-of-range placements refused; synthetic fixtures only')
