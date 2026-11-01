"""Audit per-job fence patches and strict independent shader job results."""
from pathlib import Path
import importlib.util,json,re,struct,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
packets=json.loads((root/'work/waffle/gpu/forensic-audit/compute-tools/copy-packet-audit.json').read_text())['packets']
write=next(p for p in packets if p['opcode']=='CP_EVENT_WRITE7' and p['payload_words']==4)
wait=next(p for p in packets if p['opcode']=='CP_WAIT_REG_MEM')
assert write['word_offset']+256+4==430 and wait['word_offset']+256+4==435
header=(root/'kernel/files/bsd/sys/waffle_gpu_copy.h').read_text()
words=[int(v,16) for v in re.findall('0x([0-9a-f]+)u',re.search(r'waffle_copy_payload\[4096\]=\{(.*?)\};',header,re.S)[1])]
assert words[430]==words[435]==1
code=r'''
#include <assert.h>
#include "waffle_gpu_job.h"
int main(void){
 uint32_t source[256];for(unsigned i=0;i<256;i++)source[i]=waffle_copy_payload[3328+i];
 for(unsigned fence=1;fence<=3;fence++)for(unsigned i=0;i<4096;i++){
  uint32_t before=waffle_job_word(source,fence,i,false),after=waffle_job_word(source,fence,i,true);
  uint32_t expected=waffle_copy_initial(2,i);
  if(i==430 || i==435)expected=fence;
  assert(before==expected);
  if(i>=3072 && i<3328)expected=source[i-3072];
  if(i==2048)expected=fence;
  assert(after==expected);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
start=['AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1','full GPU owner returned live to init caller; no mutex held','COPY_SEQUENCE begin jobs=3 kernel_caller=1']
rows=[]
inputs=r.uploaded_image_pixels();outputs=[]
for fence,mask in enumerate((0x00010101,0x002a173c,0x0065ab19),1):
 pixels=[v^mask for v in inputs];outputs.append(pixels)
 rows += [f'COPY_JOB begin fence={fence} seq={43+fence} pixels=256',f'COMPUTE_IB ACK matched seq{43+fence} value=00000000 valid=1',f'COPY_JOB done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0']
 rows += [f'COPY_JOB pixels fence={fence} offset={i} values='+'/'.join(f'{v:08x}' for v in pixels[i:i+8]) for i in range(0,256,8)]
 rows += [f'COPY_CALLER fence={fence} checked=256 wrong=0']
end=['SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session','SMMU_OWNER released after child stop and context detach','CLOCK_OWNER released before CX restore result=1','POWER_OWNER released after clock child, CX and CFG restore result=1','AOP_OWNER released after power child and channel restore result=1 transport=0']
text='\n'.join(start+rows+end)
assert r.extract_copy_jobs(text)==outputs and r.validate_aop_owner_log(text,2,4)==outputs[-1]
assert r.extract_copy_jobs(text+'\n'+text)==outputs
bad=[text.replace('control=00000002','control=00000001'),text.replace('COPY_CALLER fence=2 checked=256 wrong=0',''),text.replace('checked=4096 wrong_words=0','checked=4096 wrong_words=1'),text.replace('next_sequence=47','next_sequence=45'),text.replace('fence=3 offset=248','fence=3 offset=247'),text.replace('seq45','seq44')]
row=next(x for x in rows if x.startswith('COPY_JOB pixels fence=2 offset=0 '))
bad += [text.replace(row,''),text+'\n'+row.replace(row.split('values=')[1].split('/')[0],'11111111',1)]
for value in bad:
 try:r.validate_aop_owner_log(value,2,4)
 except RuntimeError:pass
 else:raise AssertionError('Stale/missing/corrupt/incorrectly sequenced jobs accepted')
# A replayed job1 output under job2's ID must not qualify even with matching ACKs.
stale=text
for i in range(0,256,8):
 row=f'COPY_JOB pixels fence=2 offset={i} values='+'/'.join(f'{v:08x}' for v in outputs[1][i:i+8])
 replacement=f'COPY_JOB pixels fence=2 offset={i} values='+'/'.join(f'{v:08x}' for v in outputs[0][i:i+8])
 stale=stale.replace(row,replacement)
try:r.validate_aop_owner_log(stale,2,4)
except RuntimeError:pass
else:raise AssertionError('Old shader output accepted as new job')
print('Kernel copy jobs: symbolic EVENT_WRITE/WAIT fence offsets, only2 immediate patches, all4096 words, 3 actual-output parser groups, stale/control/missing/conflicting results rejected (host only)')
