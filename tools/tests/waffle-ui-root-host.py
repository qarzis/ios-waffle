"""Replay the measured five-root UI shape through the actual GMU submit code.

Payload words are distinct host-model data, not captured/executed GPU commands.
"""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-submit-host.py')}
s=(root/'tools/tests/waffle-general-submit-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
callback=ns['callback'].replace('310','expected_words').replace('actual_gl_root','expected_root')
fixture='static uint32_t expected_root[1536];static unsigned expected_words;\n'
t=r'''
int main(void){
 mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;active_arena=arena;
 struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=13};
 assert(submit_session_open(1,2,3,&plan));after_open=true;
 struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
 struct waffle_gmu_region private={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
 assert(waffle_gmu_owner_bind_bo(&owner,&private));active_arena=dynamic_arena;
 uint32_t *source=calloc(1,4194304);assert(source);
 struct waffle_gpu_memory bo={.object=1,.memory=(uintptr_t)source,.bytes=4194304,.allocation_bytes=4194304,.published=true};
 const unsigned offsets[]={32768,131072,229376,360448,458752};
 const unsigned bytes[]={444,928,2800,928,428};
 struct waffle_gpu_command commands[5];expected_words=0;
 for(unsigned c=0;c<5;c++){
  commands[c]=(struct waffle_gpu_command){.buffer=&bo,.offset=offsets[c],.bytes=bytes[c]};
  for(unsigned i=0;i<bytes[c]/4;i++)expected_root[expected_words++]=source[offsets[c]/4+i]=0x12340000u^(c<<16)^i;
 }
 assert(expected_words==1382);
 struct waffle_gpu_submit_job job={.commands=commands,.count=5,.fence=99};
 if(WAFFLE_GPU_SUBMIT_WORDS==1024){
  assert(!waffle_gmu_owner_submit(&owner,&job) && !job.fence && !sends && plan.submit_session->phase==SUBMIT_READY);
 }else{
  assert(WAFFLE_GPU_SUBMIT_WORDS==1536);
  assert(waffle_gmu_owner_submit(&owner,&job) && job.fence==1 && sends==1 && waffle_gmu_owner_memory_idle(&owner));
  expected_words=1536;
  for(unsigned i=0;i<1536;i++)expected_root[i]=source[i]=0x98760000u^i;
  commands[0]=(struct waffle_gpu_command){.buffer=&bo,.bytes=1536*4};job.count=1;
  assert(waffle_gmu_owner_submit(&owner,&job) && job.fence==2 && sends==2);
  for(unsigned i=256+1536+15;i<2048;i++)assert(dynamic_arena[i]==(0xc0e00000u^i));
  assert(dynamic_arena[2048]==2);
  commands[0].bytes=1537*4;
  assert(!waffle_gmu_owner_submit(&owner,&job) && !job.fence && sends==2 && plan.submit_session->phase==SUBMIT_READY);
 }
 assert(submit_session_close(&plan));submit_session_destroy(&plan,63);free(source);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)
 for bound in (1024,1536):
  header=(root/'kernel/files/bsd/sys/waffle_gpu_submit.h').read_text()
  (p/'waffle_gpu_submit.h').write_text(re.sub(r'#define WAFFLE_GPU_SUBMIT_WORDS \d+u','#define WAFFLE_GPU_SUBMIT_WORDS '+str(bound)+'u',header))
  (p/'test.c').write_text('#include <stdlib.h>\n'+ns['parts']['h']+fixture+ns['parts']['code']+callback+t)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('Actual GMU submit:five measured UI root lengths/offsets total1382words refusedat1024/admittedat1536;distinct model payload copiedinorder/exactqualified15wordtail/fence+4096guards;1536max leaves241guardwords beforecontrol2048,1537 rejected; host model only')
