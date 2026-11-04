#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-surface-resource-log-host.py')}
exec((root/'tools/tests/waffle-surface-resource-log-host.py').read_text(),ns)
m=ns['m'];text=ns['text'];audit=ns['audit'];pixels=ns['pixels']
block='''GENERAL_SUBMIT begin fence={f} seq={s} root_words=310 kernel_tail=15 extra_IB_depth=0
GENERAL_IB ACK matched seq{s} value=00000000 valid=1
GENERAL_SUBMIT done fence={f} seq={s} control={f:08x} checked=4096 wrong_words=0
GENERAL submitted fence={f} bos=2 roots=1 words=310
'''
meta='SURFACE_IMPORT created=1 sid=1 handle=2 index=2 VA=100004000 bytes=4898816 lifetime_only=1\n'
sync='SURFACE_SAMPLE sync=1 handle=2 bytes=4898816 GPU_readonly=1\n'
audit=audit.replace('flags=80000','flags=80002').replace(meta,meta.replace('lifetime_only=1','lifetime_only=0')+'SURFACE_SAMPLE imported=1 sid=1 handle=2 index=2 GPU_readonly=1\n')
audit=audit.replace('GENERAL_BO reclaimed index=2',sync+block.format(f=3,s=46)+'GENERAL_BO reclaimed index=2')
proof='waffle-gl-surface-sample: passed=1 sid=1 checked=256 wrong=0 GL_error=0 stage=7 GPU_readonly=1\n'
samples=[]
for y in range(16):
 for x in range(16):
  sx=(2*x+1)*750//32;sy=(2*y+1)*1624//32;gy=1623-sy
  inside=(2*sx+1)*3248>750*(2*gy+1) and (2*sx+1)*3248<4872000-750*(2*gy+1)
  samples.append(0xff0040ff if inside else 0xff000000)
for i in range(0,256,8):proof+=f'waffle-gl-surface-sample: pixels offset={i} values='+('/'.join(f'{v:08x}' for v in samples[i:i+8]))+'\n'
audit=audit.replace('waffle-gl-surface-resource: passed=1',proof+'waffle-gl-surface-resource: passed=1').replace('deleted=2 GPU_memory_access=0','deleted=2 GPU_memory_access=1')
marker='GENERAL_BO released after GPU stop and context detach count=1'
at=text.index('waffle-gl-user: checked=256');end=text.index(marker)
result_rows=text[at:end];base=text[:at]+text[end:]
combined=base.replace(marker,block.format(f=2,s=45)+audit+result_rows+marker+' reclaimed_earlier=1 total=2').replace('completed=1 buffers=1','completed=3 buffers=2')
assert m.validate_gl_log(combined)==pixels
assert m.validate_gl_log(combined+'\n'+combined)==pixels
bad=[combined.replace(line,'') for line in (sync+proof+'SURFACE_SAMPLE imported=1 sid=1 handle=2 index=2 GPU_readonly=1\n').splitlines(True)]
for before,after in [('flags=80002','flags=80000'),('stage=7','stage=6'),('wrong=0 GL_error=0 stage','wrong=1 GL_error=0 stage'),('GPU_readonly=1','GPU_readonly=0'),('ff0040ff','deadbeef'),('lifetime_only=0','lifetime_only=1')]:bad.append(combined.replace(before,after))
bad.append(combined.replace(sync,'')+sync)
for t in bad:
 try:m.validate_gl_log(t)
 except RuntimeError:pass
 else:raise AssertionError('Incomplete shader sample evidence accepted')
print(f'PASS native shader sample: 256 independent texture pixels, read-only GEM identity, CPU clean before GPU completion, {len(bad)} corrupt proof refusals; synthetic only')
