"""Verify high-level Mesa compiler output and its exact bounded command stream."""
from pathlib import Path
import hashlib,importlib.util,json,re,struct,subprocess,tempfile
root=Path(__file__).resolve().parents[2];out=root/'work/waffle/gpu/forensic-audit/compute-tools'
subprocess.run(['python3',str(root/'tools/build-waffle-glsl-tools.py')],check=True,stdout=subprocess.DEVNULL)
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 for n in (1,2):
  result=subprocess.run([str(out/'waffle-glsl-compile'),str(root/'tools/tests/fixtures/waffle-glsl-copy.comp'),str(p/f'{n}.bin'),str(p/f'{n}.json'),str(p/f'{n}.disasm')],capture_output=True,text=True)
  assert not result.returncode,result.stdout+result.stderr
 assert (p/'1.bin').read_bytes()==(p/'2.bin').read_bytes()
 assert (p/'1.json').read_bytes()==(p/'2.json').read_bytes()
 assert (p/'1.disasm').read_bytes()==(p/'2.disasm').read_bytes()
 metadata=json.loads((p/'1.json').read_text());assert metadata['binary_bytes']==128 and metadata['local_size']==[256,1,1] and metadata['constlen']==metadata['private_bytes']==metadata['shared_bytes']==0
 disasm=(p/'1.disasm').read_text();assert 'ldib.' in disasm and 'stib.' in disasm and '.base0' in disasm and 'early-preamble' in disasm
 (p/'bad.comp').write_text('#version 450\nthis is not a shader\n')
 bad=subprocess.run([str(out/'waffle-glsl-compile'),str(p/'bad.comp'),str(p/'bad.bin'),str(p/'bad.json'),str(p/'bad.disasm')],capture_output=True,text=True)
 assert bad.returncode and not (p/'bad.bin').exists()
 subprocess.run(['python3',str(root/'tools/build-waffle-glsl-tools.py'),'--compute-export'],check=True,stdout=subprocess.DEVNULL)
 for n in (1,2):
  subprocess.run([str(out/'waffle-glsl-export'),str(root/'tools/tests/fixtures/waffle-glsl-copy.comp'),str(p/f'{n}.payload'),str(p/f'{n}.command'),str(p/f'{n}.manifest'),str(root/'tools/tests/fixtures/waffle-input16.ppm')],check=True)
 assert (p/'1.payload').read_bytes()==(p/'2.payload').read_bytes()
 payload=(p/'1.payload').read_bytes();assert payload[4096:4224]==(p/'1.bin').read_bytes()
 header=(root/'kernel/files/bsd/sys/waffle_gpu_glsl.h').read_text();body=re.search(r'waffle_glsl_payload\[4096\]=\{(.*?)\};',header,re.S)[1]
 assert payload==struct.pack('<4096I',*[int(v,16) for v in re.findall('0x([0-9a-f]+)u',body)])
 spec=importlib.util.spec_from_file_location('audit',root/'tools/check-waffle-compute.py');check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
 enums=json.loads((root/'tools/tests/fixtures/waffle-compute-opcodes.json').read_text());enum_header='\n'.join(f'{k} = {v},' for k,v in enums.items())
 audit=check.audit(payload,json.loads((p/'1.manifest').read_text()),enum_header,(root/'kernel/files/bsd/sys/waffle_gen7_tables.h').read_text(),True,True)
 assert audit['command_dwords']==191 and audit['protected_register_writes']==0 and len(audit['register_writes'])==76
 assert audit['exec_word_offset']==171
 events=[x for x in audit['packets'] if x['opcode']=='CP_EVENT_WRITE7' and x['payload_words']==4];waits=[x for x in audit['packets'] if x['opcode']=='CP_WAIT_REG_MEM'];assert events[0]['word_offset']+260==437 and waits[0]['word_offset']+260==442
 registers={int(x['index'],16):int(x['value'],16) for x in audit['register_writes']}
 assert registers[0xa9e8]==0x479103 and registers[0xa9e9]==0x1ff80
 assert (registers[0xa9e8]&~0x3f | registers[0xa9e9]<<32)==0x1ff8000479100
# New modes require their own proof; old real data cannot silently qualify.
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
text=(root/'work/waffle/runs/20261101T083504Z/kernel-final.log').read_text()
try:r.validate_aop_owner_log(text,2,8)
except RuntimeError:pass
else:raise AssertionError('Old handwritten shader accepted as GLSL proof')
text=text.replace('waffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256','GLSL_JOB mode=dispatch command_words=191 bindless=1 source=GLSL450\nwaffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256')
assert r.validate_aop_owner_log(text,2,8)==r.extract_copy_jobs(text)[-1]
print('Mesa GLSL: deterministic GLSL/link/NIR/FD750 IR3 and PM4 export, malformed source refusal, binary/payload identity, bindless state,191 words/76regs/zeroCPprotectconflicts; host only')
