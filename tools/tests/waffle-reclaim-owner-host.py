"""Actual service/parent reclaim ownership and real mutex, SMMU stubbed."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-service-host.py')}
s=(root/'tools/tests/waffle-service-host.py').read_text()
exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
mocks=ns['mocks'][:ns['mocks'].index('int main(void)')]
mocks=re.sub(r'^static bool waffle_smmu_owner_memory_reclaim.*$','',mocks,flags=re.M)
test=r'''
static unsigned reclaim_calls;static struct waffle_gpu_memory target;
static bool waffle_smmu_owner_memory_reclaim(struct waffle_smmu_owner *s,struct waffle_gpu_memory *bo,bool cpu_unmapped){
 lock_held();assert(s==&smmu && active_aop_gpu==&root_owner && cpu_unmapped);reclaim_calls++;
 if(mode==8 || bo!=&target)return false;
 assert(bo->object);memset(bo,0,sizeof(*bo));return true;
}
int main(void){
 struct waffle_gpu_context *ctx=waffle_gpu_context_begin();assert(ctx);
 target=(struct waffle_gpu_memory){.object=1,.published=true};
 assert(!waffle_gpu_context_memory_reclaim(ctx,&target,false) && !reclaim_calls && target.object);
 assert(!waffle_gpu_context_memory_reclaim(ctx,NULL,true) && !reclaim_calls);
 struct waffle_gpu_context foreign=*ctx;
 assert(!waffle_gpu_context_memory_reclaim(&foreign,&target,true) && !reclaim_calls);
 assert(!pthread_mutex_lock(&service_lock));
 assert(!waffle_gpu_context_memory_reclaim(ctx,&target,true) && !reclaim_calls && target.object);
 lock_held();assert(!pthread_mutex_unlock(&service_lock));
 root_owner.locked=true;assert(!waffle_gpu_context_memory_reclaim(ctx,&target,true) && !reclaim_calls);root_owner.locked=false;
 active_board_power=NULL;assert(!waffle_gpu_context_memory_reclaim(ctx,&target,true) && !reclaim_calls);active_board_power=&power;
 active_board_clocks=NULL;assert(!waffle_gpu_context_memory_reclaim(ctx,&target,true) && !reclaim_calls);active_board_clocks=&clocks;
 mode=8;assert(!waffle_gpu_context_memory_reclaim(ctx,&target,true) && reclaim_calls==1 && target.object);
 mode=0;assert(waffle_gpu_context_memory_reclaim(ctx,&target,true) && reclaim_calls==2 && !target.object);
 struct waffle_gpu_context *stale=ctx;root_owner.exercise_ok=true;
 assert(waffle_gpu_context_end(&ctx) && !ctx && allocs==frees && ends==1);
 assert(!waffle_gpu_context_memory_reclaim(stale,&target,true) && reclaim_calls==2);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(ns['h']+ns['source']+ns['adapter']+mocks+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',
  '-Wno-misleading-indentation','-fsanitize=address,undefined','-pthread','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST actual service/parent:CPU-mapped/foreign-context/busy mutex/locked owner/wrong power-clock topology/stale context refusals; SMMU refusal retains backing, success forwarded under lock, full context teardown balanced. Actual SMMU tested separately; no hardware claim.')
