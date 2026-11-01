"""Actual general GMU root submit; real captured GL root and qualified completion tail."""
from pathlib import Path
import subprocess,tempfile,struct
root=Path(__file__).resolve().parents[2];parts={};s=(root/'tools/tests/waffle-submit-session-host.py').read_text();exec(s[:s.index('with tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-submit-session-host.py')},parts)
b=(root/'work/waffle/gpu/forensic-audit/gl-context-r3/msm-requests.jsonl-submit-1-cmd-0.bin').read_bytes();w=struct.unpack('<%dI'%(len(b)//4),b)
fixture='static const uint32_t actual_gl_root[]={'+','.join(hex(v)+'u' for v in w)+'};\n'
callback=r'''
static bool hfi_exchange_watch(uintptr_t gmu,uintptr_t hfi,const uint32_t *p,unsigned count,const char *name,bool zero,struct waffle_gmu_plan *watch){
 assert(gmu==2 && hfi==3 && count==5 && !strcmp(name,"GENERAL_IB") && zero && watch->compute_image==13);
 struct waffle_submit_session *s=watch->submit_session;
 assert(s->phase==SUBMIT_BUSY && s->owns_oob && s->completed+1==s->submitted);
 assert(p[1]==0x70bf8003 && p[4]==310+15 && ((uint64_t)p[3]<<32|p[2])==s->ib_va);
 for(unsigned i=0;i<310;i++)assert(dynamic_arena[256+i]==actual_gl_root[i]);
 for(unsigned i=0;i<15;i++)assert(dynamic_arena[256+310+i]==waffle_gpu_submit_tail(i,s->submitted,s->ib_va-1024+8192));
 assert(!dynamic_arena[2048]);sends++;
 if(mode==103)return false;
 if(mode!=100)dynamic_arena[2048]=mode==101?s->submitted-1:s->submitted;
 if(mode==102)dynamic_arena[4095]^=1;
 return true;
}
'''
t=r'''
int main(void){
 /* Byte-for-byte tail identity with already hardware-qualified Mesa export. */
 for(unsigned i=0;i<15;i++)assert(waffle_gpu_submit_tail(i,1,0x1ff800047a000ULL)==waffle_glsl_payload[432+i]);
 for(unsigned failure=0;failure<6;failure++){
  mode=0;sends=allocs=frees=maps=unmaps=releases=waits=delays=0;after_open=false;active_arena=arena;
  struct waffle_gmu_plan plan={.raw_stage_pause=true,.compute_mode=2,.compute_image=13};
  assert(submit_session_open(1,2,3,&plan));after_open=true;
  struct waffle_gmu_owner owner={.plan=&plan,.exercise_ok=true};
  struct waffle_gmu_region command={WAFFLE_GPU_DYNAMIC_ADDRESS,16384,(uintptr_t)dynamic_arena,true,false};
  assert(waffle_gmu_owner_bind_bo(&owner,&command));active_arena=dynamic_arena;
  struct waffle_gpu_memory bo={.object=1,.memory=(uintptr_t)actual_gl_root,.bytes=sizeof(actual_gl_root),.allocation_bytes=16384,.published=true};
  struct waffle_gpu_command cmd={.buffer=&bo,.bytes=sizeof(actual_gl_root)};
  struct waffle_gpu_submit_job job={.commands=&cmd,.count=1,.fence=99};
  cmd.offset=1;assert(!waffle_gmu_owner_submit(&owner,&job) && !job.fence && !sends);cmd.offset=0;
  bo.published=false;assert(!waffle_gmu_owner_submit(&owner,&job) && !sends);bo.published=true;
  cmd.bytes=sizeof(actual_gl_root)+4;assert(!waffle_gmu_owner_submit(&owner,&job) && !sends);cmd.bytes=sizeof(actual_gl_root);
  for(unsigned f=1;f<=3;f++){
   if(f==2 && failure)mode=failure==5?6:99+failure;
   bool ok=waffle_gmu_owner_submit(&owner,&job);
   if(f==2 && failure){assert(!ok && !job.fence && plan.submit_session->phase==SUBMIT_POISONED);assert(!submit_session_close(&plan) && !frees && unmaps==1);break;}
   assert(ok && job.fence==f && waffle_gmu_owner_memory_idle(&owner));
  }
  if(!failure){assert(sends==3 && plan.submit_session->completed==3);assert(submit_session_close(&plan));submit_session_destroy(&plan,63);assert(frees==1 && unmaps==2);}
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(parts['h']+fixture+parts['code']+callback+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual general root submit:captured310word Mesa GL IB copied verbatim,no extra nesting,15word tail equals qualified export,3 GPU-token-model fences, bounds/stale/absent token/guard/ACK/idle failures retain session; host only')
