"""Actual 64-bit lower-VA mapping and GPU descriptor relocation tests."""
from pathlib import Path
import importlib.util,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
fixture=(root/'tools/tests/waffle-dynamic-bo-host.py').read_text();parts={}
exec(fixture[:fixture.index('with tempfile.TemporaryDirectory()')],{'__file__':str(root/'tools/tests/waffle-dynamic-bo-host.py')},parts)
h=parts['harness'].replace('static unsigned allocated,mode,tlbs,cleans,binds,after_start_allocs;', 'static unsigned allocated,mode,tlbs,cleans,binds,after_start_allocs;static uintptr_t user_data_memory;')
h=h.replace('if(live && mode==1)return 1;', 'if(live && (mode==1 || (mode==6 && after_start_allocs==1)))return 1;')
h=h.replace('*out=(uintptr_t)memory[allocated++];', '*out=(uintptr_t)memory[allocated++];if(live && !after_start_allocs)user_data_memory=*out;')
h=h.replace('if(live && mode==6 && i==allocated-1 && p>=(uintptr_t)memory[i]+4096)', 'if(live && mode==9 && p>=user_data_memory+4096 && p<user_data_memory+16384)')
h=h.replace('after_start_allocs==1);cleans++;', 'after_start_allocs>=1);cleans++;')
types=parts['types'];start=types.index('static bool waffle_gmu_owner_bind_user_buffer(');end=types.index('static bool waffle_gmu_owner_bind_data_bo(',start);types=types[:start]+types[end:]
types+=r'''
static bool waffle_gmu_owner_bind_user_buffer(struct waffle_gmu_owner *g,const struct waffle_gpu_buffer *bo){
 assert(g==&child && bo==&active->user_buffer && live && tlbs==2);
 assert(bo->memory && bo->memory!=active->dynamic.memory && bo->gpu_va==0x100000000ULL && bo->bytes==16384 && !bo->readonly);
 for(unsigned off=0;off<16384;off+=4096){uint64_t entry=pte(&active->pool,bo->gpu_va+off);assert((entry&PTE_ADDRESS)==kvtophys(bo->memory+off) && (entry&0xc3)==0x43);}
 /* 4GiB must use root index4; truncating to32bit would map root0 instead. */
 assert(((uint64_t *)active->pool.memory[0])[4]);
 assert(!pte(&active->pool,0) && !pte(&active->pool,0x47c000));
 binds++;return mode!=8;
}
'''
t=r'''
int main(void){
 assert(waffle_gpu_user_buffer_valid(0x100000000ULL,16384));
 assert(waffle_gpu_user_buffer_valid((1ULL<<39)-16384,16384));
 assert(!waffle_gpu_user_buffer_valid(0xffffc000ULL,16384));
 assert(!waffle_gpu_user_buffer_valid(0x100000001ULL,16384));
 assert(!waffle_gpu_user_buffer_valid(1ULL<<39,16384));
 assert(!waffle_gpu_user_buffer_valid(UINT64_MAX-16383,16384));
 assert(!waffle_gpu_user_buffer_valid(0x100000000ULL,4096));
 for(mode=0;mode<10;mode++){
  allocated=tlbs=cleans=binds=after_start_allocs=0;user_data_memory=0;live=false;
  struct smmu_owner owner={.child=&child,.firmware={.compact_gpu_va=true},.permission_context={.cb=1,.lpac_cb=2}};
  active=&owner;owner.permission_context.tables=&owner.pool;
  assert(new_table(&owner.pool));
  assert(map_page(&owner.pool,WAFFLE_GPU_DYNAMIC_ADDRESS,0x20000000,false));
  uintptr_t command=0;assert(!kmem_alloc(7,&command,16384,7,5));
  owner.dynamic=(struct waffle_gmu_region){WAFFLE_GPU_DYNAMIC_ADDRESS,16384,command,true,false};
  if(mode==3)assert(map_page(&owner.pool,WAFFLE_GPU_USER_TEST_VA,0x20000000,false));
  if(mode==4)((uint64_t *)owner.pool.memory[0])[4]=0x30000003;
  live=true;
  if(mode==5){assert(!smmu_user_buffer_allocate_map(&owner,0xffffc000ULL) && !after_start_allocs);continue;}
  if(setjmp(reset_trap)){assert((mode==6 || mode==7 || mode==9) && owner.user_buffer.memory && !binds);continue;}
  bool ok=smmu_user_buffer_allocate_map(&owner,WAFFLE_GPU_USER_TEST_VA);
  assert(ok==(mode==0));
  if(mode==0 || mode==8){assert(owner.user_buffer.memory && after_start_allocs==3 && tlbs==2 && binds==1);assert(!smmu_user_buffer_allocate_map(&owner,WAFFLE_GPU_USER_TEST_VA));}
  else assert(!owner.user_buffer.memory && !after_start_allocs && !binds && !tlbs);
 }
 /* Typewide address must reach both halves of the actual FDL descriptor. */
 uint32_t input[256]={0};
 assert(waffle_glsl_command_word(1,1092,0x100000000ULL,false,false)==0);
 assert(waffle_glsl_command_word(1,1093,0x100000000ULL,false,false)==1);
 for(unsigned i=0;i<256;i++)assert(waffle_data_word(input,i,false)==0xdead0000u+i);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+parts['mapping']+types+parts['dynamic']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Strict runtime parser must not accept old high-VA execution as lower64bit proof.
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
text=(root/'work/waffle/runs/20261101T085112Z/kernel-final.log').read_text()
try:r.validate_aop_owner_log(text,2,10)
except RuntimeError:pass
else:raise AssertionError('Old highVA BO accepted as lower64bit execution proof')
text=text.replace('DATA_BO published separately VA=8007c000 pages=4 aliases=2 unprivileged=1','USER_BO published VA=100000000 pages=4 lower39=1 unprivileged=1').replace('DATA_BO released after GPU stop and context detach','USER_BO released after GPU stop and context detach')
assert r.validate_aop_owner_log(text,2,10)==r.extract_copy_jobs(text)[-1]
print('64bit lower GPU VA: 10 actual PTE/root-index4/range/overflow/allocation/partialmap/TLB/bind cases, distinct BO lifetime and descriptorhighword preserved; host only')
