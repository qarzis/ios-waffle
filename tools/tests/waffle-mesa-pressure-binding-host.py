"""Exercise actual builder gate against preserved baseline/correct/rejected Mesa."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'tools/build-waffle-ui-probe.py'
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='validate_pressure_mesa')
ns=dict(ROOT=ROOT,hashlib=hashlib,json=json)
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
validate=ns['validate_pressure_mesa']
for name in ['xnu-deps/build/mesa/out-26.3.0-rc1/libOSMesa.8.dylib','work/waffle/gpu/e73-mesa-pressure/libOSMesa.candidate.dylib']:
 try:validate(ROOT/name)
 except (ValueError,OSError):pass
 else:raise AssertionError('Unsupported or rejected pressure binary admitted')
r=validate(ROOT/'work/waffle/gpu/e75-mesa-pressure/libOSMesa.8.dylib')
assert r['binary_sha256']=='749e5da7ca49a294dc57b90a50e9c45b2dc0251198462f46bee955b89c699a0f'
assert not r['hardware_stability_qualified']
print('PASS actual builder pressure gate: baseline and rejected binary refused; corrected binary/source/provenance bound; no hardware stability claim')
