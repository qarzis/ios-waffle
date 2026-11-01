"""Actual GMU session crosses diagnostic/tag boundaries; firmware mocked."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-submit-host.py')}
s=(root/'tools/tests/waffle-general-submit-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
callback=ns['callback'].replace('sends++;','assert((p[0]>>20)==waffle_gpu_submit_sequence(s->submitted-1));sends++;')
test=r'''
int main(void){
 const unsigned checkpoints[]={0,1023,1024,4050,4051,4052,8144,8145,UINT32_MAX-1,UINT32_MAX};
 for(unsigned n=0;n<sizeof(checkpoints)/sizeof(checkpoints[0]);n++){
  for(unsigned failure=0;failure<3;failure++){
   mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;active_arena=arena;
   struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=13};
   assert(submit_session_open(1,2,3,&plan));after_open=true;
   struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
   struct waffle_gmu_region private={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
   assert(waffle_gmu_owner_bind_bo(&owner,&private));active_arena=dynamic_arena;
   struct waffle_submit_session *session=plan.submit_session;
   unsigned before=checkpoints[n];
   session->submitted=session->completed=before;session->next_sequence=waffle_gpu_submit_sequence(before);
   struct waffle_gpu_memory bo={.object=1,.memory=(uintptr_t)actual_gl_root,.bytes=sizeof(actual_gl_root),.allocation_bytes=16384,.published=true};
   struct waffle_gpu_command cmd={.buffer=&bo,.bytes=sizeof(actual_gl_root)};
   struct waffle_gpu_submit_job job={.commands=&cmd,.count=1,.fence=99};
   if(failure)mode=failure==1?103:101;
   bool ok=waffle_gmu_owner_submit(&owner,&job);
   if(before==UINT32_MAX){
    assert(!ok && !job.fence && !sends && session->phase==SUBMIT_READY);
   }else if(failure){
    assert(!ok && !job.fence && sends==1 && session->phase==SUBMIT_POISONED && !owner.exercise_ok);
    assert(!submit_session_close(&plan) && !frees);continue;
   }else{
    assert(ok && job.fence==before+1 && sends==1 && waffle_gmu_owner_memory_idle(&owner));
    assert(session->next_sequence==waffle_gpu_submit_sequence(before+1));
   }
   assert(submit_session_close(&plan));
   assert(plan.session_slumber_sequence>=1 && plan.session_slumber_sequence<=4094);
   submit_session_destroy(&plan,63);assert(frees==1);
  }
 }
 /* Ten thousand consecutive requests cross both former job and HFI limits. */
 mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;active_arena=arena;
 struct waffle_gmu_plan plan={.compute_mode=2,.compute_image=13};assert(submit_session_open(1,2,3,&plan));after_open=true;
 struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
 struct waffle_gmu_region private={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
 assert(waffle_gmu_owner_bind_bo(&owner,&private));active_arena=dynamic_arena;
 struct waffle_gpu_memory bo={.object=1,.memory=(uintptr_t)actual_gl_root,.bytes=sizeof(actual_gl_root),.allocation_bytes=16384,.published=true};
 struct waffle_gpu_command cmd={.buffer=&bo,.bytes=sizeof(actual_gl_root)};struct waffle_gpu_submit_job job={.commands=&cmd,.count=1};
 for(unsigned f=1;f<=10000;f++){assert(waffle_gmu_owner_submit(&owner,&job) && job.fence==f && waffle_gmu_owner_memory_idle(&owner));}
 assert(sends==10000 && !allocs /* reset by harness? */);
 return 0;
}
'''.replace('assert(sends==10000 && !allocs /* reset by harness? */);','assert(sends==10000);assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1);')
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['parts']['h']+ns['fixture']+ns['parts']['code']+callback+test)
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual GMU:10000 consecutive synchronous submissions, former1024 and multiple4094-tag boundaries,32bitfence overflow refusal, matching packet sequence/completion guards/shutdown tag; ACK/stale-token failures retain poisoned session. Firmware and GPU mocked.')
