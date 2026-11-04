#!/usr/bin/env python3
"""Exercise actual private GPU write adapter with modeled GPU/cache callbacks."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
h=ns['h']
for name in ['waffle_gpu_memory_surface_sync','waffle_gpu_context_submit']:
 h=re.sub(r'^.*\b'+name+r'\([^\n]*\)\{[^\n]*\}\n','',h,flags=re.M)
h=h.replace('static void loader_return(void){assert(0);}','static void loader_return(void){longjmp(reset_trap,1);}')
helper=r'''
static unsigned mode,cleans,invalidates;static uint32_t native_pixels[8];
bool waffle_gpu_memory_surface_sync(const struct waffle_gpu_memory *b,uint32_t o,uint32_t n,unsigned d){
 assert(held && b->storage==WAFFLE_GPU_STORAGE_SURFACE && o==0 && n==16);
 if(d==WAFFLE_GPU_SURFACE_TO_GPU){cleans++;return mode!=1;}
 assert(d==WAFFLE_GPU_SURFACE_TO_CPU);invalidates++;return mode!=4;
}
bool waffle_gpu_context_submit(struct waffle_gpu_context *c,struct waffle_gpu_submit_job *j){
 assert(held && c==&context && j->count==1 && j->commands[0].bytes==32);
 uint32_t expected[9];assert(waffle_writeback_packet(expected,9,1,0x200000000ULL)==9);
 assert(!memcmp((void *)(j->commands[0].buffer->memory+j->commands[0].offset),expected+1,32));
 copies++;if(mode==2)return false;
 for(unsigned i=0;i<4;i++)native_pixels[i]=waffle_writeback_values[i];
 if(mode==3)native_pixels[2]^=1;
 j->fence=++context.fence;return true;
}
'''
test=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));
 held=1;
 struct waffle_gpu_memory b={.object=79,.memory=(uintptr_t)native_pixels,.bytes=32768,.allocation_bytes=32768,.storage=WAFFLE_GPU_STORAGE_SURFACE,.flags=WAFFLE_GPU_BO_CACHED,.published=true,.gpu_va=0x200000000ULL};
 for(mode=0;mode<=4;mode++){
  uint32_t original[8];for(unsigned i=0;i<8;i++)original[i]=native_pixels[i]=0xabcd0000+i;
  struct waffle_surface_write_result r;cleans=invalidates=0;unsigned before=live_reclaims,submitted=copies;
  if(mode==2 || mode==4){
   if(!setjmp(reset_trap)){drm_surface_write_probe(&b,0,&r);assert(0);}
   assert(r.uncertain && !r.restored && live_reclaims==before && storage[stored-1].published);
   /* Reset model only after checking retention, no implicit uncertain reclaim. */
   free((void *)storage[stored-1].memory);memset(&storage[stored-1],0,sizeof(storage[0]));
  }else{
   int e=drm_surface_write_probe(&b,0,&r);assert(e==(mode?EIO:0));
   assert(live_reclaims==before+1 && !memcmp(native_pixels,original,sizeof(original)));
   assert(r.restored==(mode!=1) && r.wrong==(mode==3));
   assert(copies==submitted+(mode!=1));
  }
  assert(!memcmp(native_pixels+4,original+4,16));
  assert(!drm_count && !drm_issued && !mapped);
 }
 held=0;assert(!drm_close(0,0,0,&owner));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(root/'tools/tests/waffle-surface-write-host.c'),'-o',str(p/'pure')],check=True)
 subprocess.run([str(p/'pure')],check=True)
 (p/'test.c').write_text(h+ns['parts']['ioc']+ns['uapi']+helper+ns['source']+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual private write adapter: qualified packet/address, real fence accounting, restore/mismatch/initial-sync failure, uncertain submit/invalidate retains command and backing; host model only')
