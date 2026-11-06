#!/usr/bin/env python3
"""Execute actual post-run haptic/FIFO acceptance blocks without USB."""
from pathlib import Path
import ast,re,tempfile
from types import SimpleNamespace
r=Path(__file__).resolve().parents[2];tree=ast.parse((r/'scripts/run_waffle_ios.py').read_text())
errors=('Native bounded haptic pulse/stop/restore proof failed','Native FIFO empty/status/selector restore proof incomplete','Native zero FIFO transport/flush/restore proof incomplete')
blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test).startswith('args.haptic_pulse') and any(isinstance(x,ast.Constant) and isinstance(x.value,str) and x.value.startswith(errors) for x in ast.walk(n))]
assert len(blocks)==3
code=compile(ast.fix_missing_locations(ast.Module(body=blocks,type_ignores=[])),'actual-haptic-FIFO-proof','exec')
text='''haptic-waffle-pulse: passed=1 admitted=1 start=1
haptic-waffle-pulse: stopped=1 restored=1 emergency=0 writes=7
haptic-waffle-pulse: amplitude=32 requested_us=16000 HBST_writes=0
haptic-fifo-status: passed=1 restored=1 writes=4
haptic-fifo-status: FIFO_writes=0 motor_started=0
haptic-fifo-status: fill=0 capacity=1920 empty=0 full=0
haptic-fifo-buffer: passed=1 loaded=1 cleared=1
haptic-fifo-buffer: fill=144 final=0 commands=36
haptic-fifo-buffer: selectors=1 SWR_restored=1 source=1
haptic-fifo-buffer: zeros=144 motor_STARTED=0 HBST_writes=0
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'kernel';p.write_bytes(b'haptic-fifo-status: passed= haptic-fifo-buffer: passed=')
 def check(t):exec(code,{'args':SimpleNamespace(haptic_pulse=True,kernel=p),'final_text':t,'out':Path(d),'re':re})
 check(text)
 bad=[text.replace(line,'') for line in text.splitlines(True)]
 for a,b in [('loaded=1','loaded=0'),('fill=144','fill=140'),('final=0','final=4'),('commands=36','commands=37'),('SWR_restored=1','SWR_restored=0'),('source=1','source=4'),('source=1','source=31')]:bad.append(text.replace(a,b))
 for t in bad:
  try:check(t)
  except RuntimeError:pass
  else:raise AssertionError('Incomplete/corrupt FIFO transport proof accepted')
print(f'PASS actual haptic/FIFO post-run checker: {len(bad)} missing/corrupt evidence refusals; no USB or hardware claim.')
