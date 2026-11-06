"""Actual registry relocation, failure retention and neighbor preservation."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
parts={'__file__':str(root/'tools/tests/waffle-reclaim-host.py')}
s=(root/'tools/tests/waffle-reclaim-host.py').read_text();exec(s[:s.index("test=r")],parts)
code=parts['code'].replace('static unsigned mode,','static unsigned maps;\nstatic unsigned mode,').replace('ptes[slot(address)]=pa|0x43','if(mode==8 || (mode==9 && ++maps==2))return false;ptes[slot(address)]=pa|0x43').replace('return gpu_ok && lpac_ok;','return gpu_ok && lpac_ok && !(mode==10 && tlbs==4);').replace('return mode!=1 &&','return !(mode==11 && tlbs==4) && mode!=1 &&')
test=r'''
int main(void){
 for(unsigned failure=0;failure<=11;failure++){
  reset_all();struct waffle_gpu_registry r={.buffers=entries};
  struct waffle_gpu_memory *a=waffle_gpu_registry_new(&r,&base,32768,WAFFLE_GPU_BO_WC);
  struct waffle_gpu_memory *neighbor=waffle_gpu_registry_new(&r,&base,16384,WAFFLE_GPU_BO_WC);
  uint64_t old=a->gpu_va,target=old+0x100000,neighbor_pte=ptes[slot(neighbor->gpu_va)];
  reset_phase();
  assert(!waffle_gpu_registry_relocate(&r,&ops,a,neighbor->gpu_va,true));
  assert(!waffle_gpu_registry_relocate(&r,&ops,a,target,false));
  assert(!waffle_gpu_registry_relocate(&r,&ops,a,target+4096,true));
  assert(!waffle_gpu_registry_relocate(&r,&ops,a,~0ULL-16383,true));
  assert(!cleared && !r.poisoned && a->gpu_va==old);
  reset_phase();maps=0;mode=failure;
  bool ok=waffle_gpu_registry_relocate(&r,&ops,a,target,true);
  assert(ok==(failure==0 || failure==7));
  assert(!frees && r.used==49152 && a->object && a->published);
  assert(ptes[slot(neighbor->gpu_va)]==neighbor_pte);
  if(ok){
   assert(a->gpu_va==target && !r.poisoned && cleans==2 && tlbs==4);
   for(unsigned off=0;off<32768;off+=4096){assert(!ptes[slot(old+off)]);assert(owns((void*)1,target+off,waffle_gpu_memory_page(a,off),false));}
   mode=0;reset_phase();assert(waffle_gpu_registry_reclaim(&r,&ops,a,true));assert(r.used==16384);
  }else{assert(a->gpu_va==old);assert(r.poisoned==(failure>=3));}
  mode=0;assert(waffle_gpu_registry_destroy(&r,true) && frees==objects);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual BO relocation: chosen VA, all leaves, collision/alignment/range/CPU-map refusal, idle/ownership/unmap/TLB/map failure retention, neighbors and reclaim; host only')
