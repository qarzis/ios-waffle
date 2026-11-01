"""E54 proposed partition of measured E53 root descriptors, host only.

Executes actual GMU submission code with synthetic payloads and hardware stubs.
The cdev still rejects this workload; this model does not change the driver.
"""
from pathlib import Path
import hashlib,json,subprocess,tempfile

root=Path(__file__).resolve().parents[2]
record=json.loads((root/'work/waffle/gpu/forensic-audit/E53-first-submit.json').read_text())
raw=root/record['run']/record['raw_snapshot']
assert hashlib.sha256(raw.read_bytes()).hexdigest()==record['raw_sha256']
descriptors=record['commands']
assert len(descriptors)==57 and sum(c['bytes']//4 for c in descriptors)==7492
assert all(c['type']==1 and not c['bytes']%4 for c in descriptors)
ns={'__file__':str(root/'tools/tests/waffle-general-submit-host.py')}
source=(root/'tools/tests/waffle-general-submit-host.py').read_text()
exec(source[:source.index('\nwith tempfile.TemporaryDirectory()')],ns)
callback=ns['callback'].replace('310','expected_words').replace('actual_gl_root','expected_root')
fixture='static uint32_t expected_root[1536];static unsigned expected_words;\n'
fixture+='static const unsigned descriptor[][3]={'+','.join(
    '{%d,%d,%d}'%(c['submit_idx'],c['offset'],c['bytes']) for c in descriptors)+'};\n'
test=r'''
int main(void){
 for(unsigned failure=0;failure<3;failure++){
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;
  after_open=false;active_arena=arena;
  struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=13};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
  struct waffle_gmu_region private={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  assert(waffle_gmu_owner_bind_bo(&owner,&private));active_arena=dynamic_arena;
  struct waffle_gpu_memory memory[2];
  for(unsigned b=0;b<2;b++){
   uint32_t *data=calloc(1,4194304);assert(data);
   for(unsigned i=0;i<4194304/4;i++)data[i]=0x53140000u^(b<<24)^i;
   memory[b]=(struct waffle_gpu_memory){.object=1,.memory=(uintptr_t)data,
    .bytes=4194304,.allocation_bytes=4194304,.published=true};
  }
  struct waffle_gpu_command commands[57];
  for(unsigned i=0;i<57;i++){
   assert(descriptor[i][0]==9 || descriptor[i][0]==232);
   commands[i]=(struct waffle_gpu_command){.buffer=&memory[descriptor[i][0]==232],
    .offset=descriptor[i][1],.bytes=descriptor[i][2]};
   assert(waffle_gpu_command_valid(&commands[i]));
  }
  /* Current direct request is rejected before any GPU work. */
  struct waffle_gpu_submit_job job={.commands=commands,.count=57};
  assert(!waffle_gmu_owner_submit(&owner,&job) && !sends);
  unsigned cursor=0,windows=0,total=0;
  while(cursor<57){
   unsigned begin=cursor;expected_words=0;
   while(cursor<57 && cursor-begin<WAFFLE_GPU_SUBMIT_COMMANDS){
    const struct waffle_gpu_command *c=&commands[cursor];
    assert(c->bytes/4<=WAFFLE_GPU_SUBMIT_WORDS);
    if(c->bytes/4>WAFFLE_GPU_SUBMIT_WORDS-expected_words)break;
    const uint32_t *data=(const uint32_t *)(c->buffer->memory+c->offset);
    for(unsigned i=0;i<c->bytes/4;i++)expected_root[expected_words++]=data[i];
    cursor++;
   }
   assert(cursor>begin);windows++;
   job=(struct waffle_gpu_submit_job){.commands=commands+begin,.count=cursor-begin};
   if(failure && windows==3)mode=failure==1?103:101;
   bool ok=waffle_gmu_owner_submit(&owner,&job);
   if(failure && windows==3){
    assert(!ok && !job.fence && sends==3);
    assert(plan.submit_session->phase==SUBMIT_POISONED);
    assert(!submit_session_close(&plan) && !frees);
    break; /* No later window may be submitted after an uncertain completion. */
   }
   assert(ok && job.fence==windows && waffle_gmu_owner_memory_idle(&owner));
   total+=expected_words;
  }
  if(!failure){
   assert(cursor==57 && windows==5 && total==7492 && sends==5);
   assert(submit_session_close(&plan));submit_session_destroy(&plan,63);
   assert(frees==1 && unmaps==2);
  }
  for(unsigned b=0;b<2;b++)free((void *)memory[b].memory);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 (p/'test.c').write_text('#include <stdlib.h>\n'+ns['parts']['h']+fixture+ns['parts']['code']+callback+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
  '-Wno-unused-variable','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),
  str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST ONLY: actual GMU code preserves all57 measured root ranges/7492 synthetic words in5 ordered windows, unchanged1536-word/16-root/private16KiB/tail/guards; ACK/stale-token failure stops before later windows and retains poisoned session. Cdev implementation and real GPU state preservation remain untested.')
