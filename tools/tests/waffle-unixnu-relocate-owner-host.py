"""Actual service/parent relocation gates with real mutex, SMMU modeled."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-service-host.py')}
s=(root/'tools/tests/waffle-service-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
mocks=ns['mocks'][:ns['mocks'].index('int main(void)')]
ns['h']=re.sub(r'^static bool waffle_smmu_owner_memory_relocate.*$', 'static bool waffle_smmu_owner_memory_relocate(struct waffle_smmu_owner *,struct waffle_gpu_memory *,uint64_t,bool);',ns['h'],flags=re.M)
mocks=re.sub(r'^static bool waffle_smmu_owner_memory_relocate.*$','',mocks,flags=re.M)
test=r'''
static unsigned moves;static struct waffle_gpu_memory target;
static bool waffle_smmu_owner_memory_relocate(struct waffle_smmu_owner *s,struct waffle_gpu_memory *b,uint64_t va,bool u){
 lock_held();assert(s==&smmu && b==&target && u && va==0x10f000000ULL);moves++;
 if(mode==8)return false;b->gpu_va=va;return true;
}
int main(void){
 struct waffle_gpu_context *ctx=waffle_gpu_context_begin();assert(ctx);
 target=(struct waffle_gpu_memory){.object=1,.published=true,.gpu_va=0x100000000ULL};
 assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,false) && !moves);
 struct waffle_gpu_context foreign=*ctx;
 assert(!waffle_gpu_context_memory_relocate(&foreign,&target,0x10f000000ULL,true) && !moves);
 assert(!pthread_mutex_lock(&service_lock));assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && !moves);assert(!pthread_mutex_unlock(&service_lock));
 root_owner.locked=true;assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && !moves);root_owner.locked=false;
 active_board_power=NULL;assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && !moves);active_board_power=&power;
 active_board_clocks=NULL;assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && !moves);active_board_clocks=&clocks;
 mode=8;assert(!waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && moves==1 && target.gpu_va==0x100000000ULL);
 mode=0;assert(waffle_gpu_context_memory_relocate(ctx,&target,0x10f000000ULL,true) && moves==2 && target.gpu_va==0x10f000000ULL);
 root_owner.exercise_ok=true;assert(waffle_gpu_context_end(&ctx) && !ctx);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(ns['h']+ns['source']+ns['adapter']+mocks+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-pthread','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual relocation service/parent: mutex, current context/board ownership, CPU-map gate and SMMU failure propagation; SMMU modeled')
