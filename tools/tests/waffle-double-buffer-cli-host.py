"""Parse and forward the double-buffer opt-in without accessing USB."""
from pathlib import Path
import ast,sys,subprocess,tempfile,json
root=Path(__file__).resolve().parents[2];path=root/'work/waffle/gpu/run-publish-test.py';source=path.read_text();prefix=source[:source.index("before=set(Path('work/waffle/runs').iterdir())")]
chain=['--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-dispatch','--gl-context','--ui-workload']
previous=sys.argv
try:
 for extras in [['--double-buffer'],['--double-buffer','--hardware-vsync']]:
  sys.argv=['runner','94','artifact',*chain,*extras];ns={};exec(prefix,ns);assert ns['double_buffer']
  call=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='run' and n.args and 'scripts/run_waffle_ios.py' in ast.unparse(n.args[0]))
  command=eval(compile(ast.Expression(call.args[0]),str(path),'eval'),ns)
  assert command.count('--double-buffer')==1 and ('--hardware-vsync' in command)==('--hardware-vsync' in extras)
 for extras in [['--double-buffer','--double-buffer'],['--double-buffer','--display-survey'],['--double-buffer','--display-flush-probe'],['--double-buffer','--display-flip-probe']]:
  sys.argv=['runner','94','artifact',*chain,*extras]
  try:exec(prefix,{})
  except AssertionError:pass
  else:raise AssertionError('Conflicting display modes admitted')
finally:sys.argv=previous
r=subprocess.run([sys.executable,str(root/'scripts/run_waffle_ios.py'),'--double-buffer'],capture_output=True,text=True)
assert r.returncode and 'requires isolated GPU UI' in r.stderr
with tempfile.TemporaryDirectory() as directory:
 Path(directory,'manifest.json').write_text(json.dumps({}))
 r=subprocess.run([sys.executable,str(root/'tools/run-waffle-auto.py'),'--artifact',directory,'--double-buffer','--ui-workload','--gl-context','--compute','dispatch','--dynamic-bo','--session','--ib','--writeback','--zap','--lpac-cp-init','--lpac-map'],capture_output=True,text=True)
 assert r.returncode and 'requires a bound dedicated GPU UI artifact' in r.stderr
print('PASS actual double-buffer CLI: explicit mode forwarded once, compatible hardware timestamps, other display modes/duplicates/standalone rejected, dedicated artifact required before USB')
