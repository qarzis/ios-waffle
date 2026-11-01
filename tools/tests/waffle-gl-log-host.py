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
