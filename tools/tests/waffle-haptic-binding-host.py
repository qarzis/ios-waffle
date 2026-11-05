#!/usr/bin/env python3
"""Execute actual pre-USB pulse admission block with changed artifact inputs."""
import ast,hashlib,tempfile
from pathlib import Path
from types import SimpleNamespace
root=Path(__file__).resolve().parents[2]
t=ast.parse((root/'tools/run-waffle-auto.py').read_text())
blocks=[n for n in ast.walk(t) if isinstance(n,ast.If) and ast.unparse(n.test)=='args.haptic_pulse or args.haptic_service_test' and any(isinstance(x,ast.Constant) and x.value=='haptic_pulse_test' for x in ast.walk(n))]
assert len(blocks)==1
code=compile(ast.fix_missing_locations(ast.Module(body=[blocks[0]],type_ignores=[])),'actual-pulse-admission','exec')
class Parser:
 def error(self,msg):raise ValueError(msg)
names=['kernel/files/bsd/dev/macan_torch.c','kernel/files/bsd/sys/waffle_haptic_readonly.h','kernel/files/bsd/sys/waffle_haptic_pulse.h','kernel/files/bsd/sys/waffle_haptic_events.h','loader/waffle.h']
with tempfile.TemporaryDirectory() as d:
 p=Path(d);r=p/'root';a=p/'artifact'
 for case in range(14):
  for n in names:
   for x in [r/n,a/'source'/n]:x.parent.mkdir(parents=True,exist_ok=True);x.write_bytes(n.encode())
  (a/'kernel').write_bytes(b'haptic-waffle-pulse: passed=')
  m={'haptic_pulse_loader':True,'haptic_pulse_test':True,'kernel_sha256':hashlib.sha256((a/'kernel').read_bytes()).hexdigest(),'haptic_pulse_source_sha256':{n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}}
  if case==1:m['haptic_pulse_test']=False
  if case==2:m['haptic_pulse_source_sha256'].pop(names[2])
  if case in [3,4,5]:(r/names[case-3]).write_bytes(b'changed')
  if case in [6,7,8]:(a/'source'/names[case-6]).write_bytes(b'changed')
  if case==9:(a/'kernel').write_bytes(b'changed')
  if case==10:m['haptic_pulse_loader']=False
  if case==11:(r/names[3]).write_bytes(b'changed')
  if case==12:(a/'source'/names[3]).write_bytes(b'changed')
  if case==13:
   (a/'kernel').write_bytes(b'no-pulse-code');m['kernel_sha256']=hashlib.sha256((a/'kernel').read_bytes()).hexdigest()
  try:exec(code,{'args':SimpleNamespace(haptic_pulse=True,haptic_service_test=False),'artifact':a,'ROOT':r,'manifest':m,'parser':Parser(),'hashlib':hashlib})
  except ValueError:assert case!=0
  else:assert case==0
print('PASS actual haptic pre-USB admission: bound positive; capability, all current/snapshot sources, missing header and kernel tamper refused. No USB.')
