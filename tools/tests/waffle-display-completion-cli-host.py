#!/usr/bin/env python3
from pathlib import Path
import ast,sys,subprocess,runpy,tempfile,hashlib,copy
root=Path(__file__).resolve().parents[2];path=root/'work/waffle/gpu/run-publish-test.py';source=path.read_text();prefix=source[:source.index("before=set(Path('work/waffle/runs').iterdir())")]
chain=['--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-dispatch','--gl-context','--ui-workload','--double-buffer','--hardware-vsync']
previous=sys.argv
try:
 sys.argv=['runner','94','artifact',*chain,'--display-completion-audit'];ns={};exec(prefix,ns);assert ns['display_completion_audit']
 calls=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='run' and n.args and 'scripts/run_waffle_ios.py' in ast.unparse(n.args[0])]
 assert len(calls)==1;cmd=eval(compile(ast.Expression(calls[0].args[0]),str(path),'eval'),ns);assert cmd.count('--display-completion-audit')==1
 for flags in [[*chain,'--display-completion-audit','--display-completion-audit'],[*chain,'--display-completion-audit','--display-survey'],[f for f in chain if f!='--double-buffer']+['--display-completion-audit'],[f for f in chain if f!='--hardware-vsync']+['--display-completion-audit'],['--display-completion-audit']]:
  sys.argv=['runner','94','artifact',*flags]
  try:exec(prefix,{})
  except AssertionError:pass
  else:raise AssertionError('Unbound completion audit admitted')
finally:sys.argv=previous
p=subprocess.run([sys.executable,str(root/'scripts/run_waffle_ios.py'),'--display-completion-audit'],capture_output=True,text=True);assert p.returncode and 'requires guarded hardware-VSync GPU UI' in p.stderr
check=runpy.run_path(str(root/'tools/run-waffle-auto.py'))['check_display_completion_binding']
with tempfile.TemporaryDirectory() as directory:
 r=Path(directory)/'repo';a=Path(directory)/'artifact';m={'display_completion_source_sha256':{}}
 names=['loader/waffle.h','kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp','kernel/files/bsd/sys/waffle_display_completion.h','kernel/files/bsd/sys/waffle_display_present.h']
 for name in names:
  for base in [r,a/'source']:
   p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name+' waffle_display_completion_audit=1')
  m['display_completion_source_sha256'][name]=hashlib.sha256((r/name).read_bytes()).hexdigest()
 check(r,a,m)
 for name in names:
  bad=copy.deepcopy(m);del bad['display_completion_source_sha256'][name]
  try:check(r,a,bad)
  except ValueError:pass
  else:raise AssertionError('Missing completion binding accepted')
  p=a/'source'/name;data=p.read_bytes();p.write_bytes(b'stale')
  try:check(r,a,m)
  except ValueError:pass
  else:raise AssertionError('Stale compiled completion binding accepted')
  p.write_bytes(data)
print('PASS actual completion CLI forwarding/admission + eight missing/stale compiled bindings before USB; synthetic only.')
# The actual capture block must precede every early GPU prerequisite gate.
import types,json
inner=root/'scripts/run_waffle_ios.py';tree=ast.parse(inner.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
finished=next(n for n in ast.walk(main) if isinstance(n,ast.If) and ast.unparse(n.test)=='\'running\' not in line')
collection=next(n for n in finished.body if isinstance(n,ast.If) and ast.unparse(n.test)=='args.display_completion_audit')
early=next(n for n in finished.body if isinstance(n,ast.If) and ast.unparse(n.test)=='args.gpu_dynamic_bo')
assert finished.body.index(collection)<finished.body.index(early)
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);kernel=p/'kernel';kernel.write_bytes(b'waffle-display-irq:')
 text='identity'.ljust(256)+'\nwaffle-display-completion: records=1 no_extra_writes=1 guard_frames=2 cntfrq=1000000\nwaffle-display-completion: row=0 seq=1 stage=2 ticks=100 valid=1 frame0=3 frame1=3 flush=0 scheduler=1 auto_status=0 write_line=0 read_line=1 address0=d5100000 address1=d5100000\nwaffle-display-irq: row=0 top_status=100 top_enable=0 ctl_status=200 ctl_enable=0 tear_status=4f tear_enable=0 active=2\n'
 (p/'kernel-1.log').write_text(text);(p/'kernel-final.log').write_text(text+'END')
 ns={'ROOT':root,'args':types.SimpleNamespace(display_completion_audit=True,kernel=kernel),'out':p,'json':json,'final_text':text+'END'}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[collection],type_ignores=[])),str(inner),'exec'),ns)
 assert json.loads((p/'display-completion.json').read_text())['irq_record_count']==1
 assert json.loads((p/'kernel-stream-proof.json').read_text())['bytes']==len((text+'END').encode())
print('PASS actual post-run collector before early GPU gates, paired IRQ requirement and valid JSON artifacts; synthetic snapshots only.')
