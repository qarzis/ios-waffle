#!/usr/bin/env python3
"""Run actual collector AST against a rolling UI log; retain strict overlap."""
from pathlib import Path
import ast,types,tempfile,json
root=Path(__file__).resolve().parents[2];path=root/'scripts/run_waffle_ios.py';tree=ast.parse(path.read_text())
main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
finished=next(n for n in ast.walk(main) if isinstance(n,ast.If) and ast.unparse(n.test)=="'running' not in line")
block=next(n for n in finished.body if isinstance(n,ast.If) and ast.unparse(n.test)=='args.display_completion_audit')
early=next(n for n in finished.body if isinstance(n,ast.If) and ast.unparse(n.test)=='args.gpu_dynamic_bo');assert finished.body.index(block)<finished.body.index(early)
code=compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),str(path),'exec')
with tempfile.TemporaryDirectory() as t:
 p=Path(t);head='identity'.ljust(256);body='BO publication index1\n'+''.join(f'{i:08x}\n' for i in range(3000));first=head+body;final=head+body[-6000:]+'END'
 (p/'kernel-1.log').write_text(first);(p/'kernel-final.log').write_text(final)
 for ui,double,haptic in ((False,False,False),(True,False,False),(False,True,False),(True,True,False),(False,False,True)):
  proof=p/'kernel-stream-proof.json';proof.unlink(missing_ok=True)
  ns=dict(ROOT=root,args=types.SimpleNamespace(display_completion_audit=False,gpu_ui=ui,double_buffer=double,haptic_pulse=haptic,haptic_service_test=False),out=p,json=json,final_text=final)
  exec(code,ns)
  assert proof.exists()==((ui and double) or haptic)
  assert ns['final_text']==(first+'END' if ((ui and double) or haptic) else final)
  if proof.exists():assert json.loads(proof.read_text())['bytes']==len((first+'END').encode())
 (p/'kernel-final.log').write_text(head+'z'*6000)
 try:exec(code,dict(ROOT=root,args=types.SimpleNamespace(display_completion_audit=False,gpu_ui=True,double_buffer=True),out=p,json=json,final_text=final))
 except ValueError:pass
 else:raise AssertionError('missing log overlap accepted')
print('PASS actual guarded UI collector before BO gates: exact rolling reconstruction, JSON proof, non-guarded defaults and gap refusal; host only')

call=next(n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='validate_ui_workload_log')
assert ast.unparse(next(k.value for k in call.keywords if k.arg=='guarded_display'))=='args.double_buffer'
for double,audit in ((True,False),(True,True),(False,False)):
 observed=[]
 ns=dict(final_text='text',args=types.SimpleNamespace(double_buffer=double,display_completion_audit=audit),validate_ui_workload_log=lambda text,guarded_display:observed.append(guarded_display))
 eval(compile(ast.Expression(call),str(path),'eval'),ns);assert observed==[double]
print('PASS actual UI proof selects framebuffer mode from double-buffer flag, independent of optional audit')
