"""Exercise real display-flush parser and actual inner command AST without USB."""
from pathlib import Path
import ast,sys,subprocess
root=Path(__file__).resolve().parents[2];path=root/'work/waffle/gpu/run-publish-test.py';source=path.read_text();prefix=source[:source.index("before=set(Path('work/waffle/runs').iterdir())")]
chain=['--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-dispatch','--gl-context','--ui-workload']
previous=sys.argv
try:
 sys.argv=['runner','94','artifact',*chain,'--display-flush-probe'];ns={};exec(prefix,ns);assert ns['display_flush']
 calls=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='run' and n.args and 'scripts/run_waffle_ios.py' in ast.unparse(n.args[0])]
 assert len(calls)==1
 command=eval(compile(ast.Expression(calls[0].args[0]),str(path),'eval'),ns)
 assert command.count('--display-flush-probe')==1 and '--display-survey' not in command and '--hardware-vsync' not in command
 for flags in [chain+['--display-flush-probe','--display-flush-probe'],chain+['--display-flush-probe','--display-survey'],chain+['--display-flush-probe','--hardware-vsync'],['--display-flush-probe']]:
  sys.argv=['runner','94','artifact',*flags]
  try:exec(prefix,{})
  except AssertionError:pass
  else:raise AssertionError('Unsafe or duplicate display-control mode accepted')
finally:sys.argv=previous
r=subprocess.run([sys.executable,str(root/'scripts/run_waffle_ios.py'),'--display-flush-probe'],capture_output=True,text=True)
assert r.returncode and 'requires isolated GPU UI' in r.stderr
r=subprocess.run([sys.executable,str(root/'tools/run-waffle-auto.py'),'--artifact',str(root/'work/waffle/diagnostic-display-map-d01'),'--display-flush-probe','--ui-workload','--gl-context','--compute','dispatch','--dynamic-bo','--session','--ib','--writeback','--zap','--lpac-cp-init','--lpac-map'],capture_output=True,text=True)
assert r.returncode and 'requires a bound dedicated GPU UI artifact' in r.stderr
print('PASS actual display-control CLI: dedicated artifact required before USB, standalone/mixed/duplicate modes rejected, native inner command forwards exactly one explicit opt-in')
