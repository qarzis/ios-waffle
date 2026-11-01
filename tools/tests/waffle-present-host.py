"""Exercise actual bounded framebuffer transfer and presentation cleanup."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
wrapper=source[source.index('static bool present_gpu_pixels('):source.index('enum submit_phase {')]
wrapper=wrapper.replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdarg.h>
#include "waffle_gpu_present.h"
typedef uintptr_t vm_offset_t;
static struct {uintptr_t v_baseaddr;uint64_t v_physaddr;unsigned v_width,v_height,v_depth,v_rowbytes;} vinfo;
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define NSEC_PER_USEC 1000
#define kernel_map 7
static uint32_t *frame,*backup;
static unsigned allocs,frees,holds,barriers,mode;
static uint32_t pixels[256];
static int kmem_alloc(unsigned map,uintptr_t *out,unsigned bytes,unsigned flags,unsigned tag){
 assert(map==7 && bytes==WAFFLE_PRESENT_BYTES && flags==7 && tag==5);allocs++;
 if(mode==1)return 1;
 backup=calloc(1,bytes);assert(backup);*out=(uintptr_t)backup;return 0;
}
static void kmem_free(unsigned map,uintptr_t ptr,unsigned bytes){assert(map==7 && ptr==(uintptr_t)backup && bytes==WAFFLE_PRESENT_BYTES);free(backup);frees++;}
static void say(const char *fmt,...){assert(fmt);}
static void delay_for_interval(unsigned amount,unsigned unit){assert(amount==5000000 && unit==1000);holds++;}
static void barrier(void){barriers++;if((mode==2 && barriers==1)||(mode==3 && barriers==2))frame[1456*1440+592]^=1;}
'''
test=r'''
int main(void){
 assert(waffle_present_bgra(0xff112233)==0xff332211);
 assert(waffle_present_bgra(0xff00ff00)==0xff00ff00);
 assert(waffle_present_valid(0x100000000,0xd5100000,1440,3168,32,5760));
 assert(!waffle_present_valid(0,0xd5100000,1440,3168,32,5760));
 assert(!waffle_present_valid(0x100000001,0xd5100000,1440,3168,32,5760));
 assert(!waffle_present_valid(UINTPTR_MAX-3,0xd5100000,1440,3168,32,5760));
 assert(!waffle_present_valid(0x100000000,0xd7b00000,1440,3168,32,5760));
 assert(!waffle_present_valid(0x100000000,0xd5000000,1440,3168,32,5760));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1441,3168,32,5760));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1440,3167,32,5760));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1440,3168,24,5760));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1440,3168,32,5756));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1440,3168,32,5761));
 assert(!waffle_present_valid(0x100000000,0xd5100000,1440,3168,32,32768));
 frame=malloc(1440*3168*4);assert(frame);
 for(unsigned i=0;i<256;i++)pixels[i]=0xff000000u|((i*41u)&0xffffffu);
 for(unsigned stride=5760;stride<=5808;stride+=48){
  unsigned count=stride/4*3168;uint32_t *fb=malloc((count+2)*4),*saved=malloc(WAFFLE_PRESENT_BYTES);assert(fb && saved);
  for(unsigned i=0;i<count+2;i++)fb[i]=i^0xa5f01000u;
  waffle_present_transfer(fb+1,stride,pixels,saved,0);
  for(unsigned y=0;y<3168;y++)for(unsigned x=0;x<stride/4;x++){
   unsigned i=1+y*(stride/4)+x;
   uint32_t expected=(x>=592 && x<848 && y>=1456 && y<1712)?waffle_present_bgra(pixels[((y-1456)/16)*16+(x-592)/16]):(i^0xa5f01000u);
   assert(fb[i]==expected);
  }
  assert(!waffle_present_transfer(fb+1,stride,pixels,saved,1));
  fb[1+1456*(stride/4)+592]^=1;assert(waffle_present_transfer(fb+1,stride,pixels,saved,1)==1);
  waffle_present_transfer(fb+1,stride,pixels,saved,2);assert(!waffle_present_transfer(fb+1,stride,pixels,saved,3));
  for(unsigned i=0;i<count+2;i++)assert(fb[i]==(i^0xa5f01000u));free(saved);free(fb);
 }
 for(mode=0;mode<5;mode++){
  allocs=frees=holds=barriers=0;
  for(unsigned i=0;i<1440*3168;i++)frame[i]=i^0x12340000u;
  vinfo.v_baseaddr=(uintptr_t)frame;vinfo.v_physaddr=0xd5100000;vinfo.v_width=mode==4?0:1440;vinfo.v_height=3168;vinfo.v_depth=32;vinfo.v_rowbytes=5760;
  assert(present_gpu_pixels(pixels)==(mode==0));
  assert(allocs==(mode==4?0:1));assert(frees==((mode==1 || mode==4)?0:1));
  assert(holds==((mode==0 || mode==3)?1:0));
  if(mode!=3)for(unsigned i=0;i<1440*3168;i++)assert(frame[i]==(i^0x12340000u));
 }
 free(frame);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code+wrapper+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Test strict runtime acceptance using actual saved E23 data plus ordered new markers.
spec=importlib.util.spec_from_file_location('runner',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
text=(root/'work/waffle/runs/20261101T071657Z/kernel-final.log').read_text()
markers=['PRESENT begin format=BGRA8 x=592 y=1456 width=256 height=256 cpu_blit=1','PRESENT write checked=65536 wrong=0','PRESENT restore checked=65536 wrong=0']
# Trim timestamp duplicate: acceptance requires ordered first occurrences.
text=text.split('[    0.')[0] if '[    0.' in text else text
needle='waffle-gmu: SESSION result=1 submitted=1 completed=1 next_sequence=45 OOB=1; bounded kernel session'
text=text.replace(needle,'\n'.join(markers)+'\n'+needle)
assert r.validate_aop_owner_log(text,2,3)==r.uploaded_image_pixels()
for m in markers:
 bad=text.replace(m,'')
 try:r.validate_aop_owner_log(bad,2,3)
 except RuntimeError:pass
 else:raise AssertionError('Missing presentation proof accepted')
for bad in [text.replace('checked=65536 wrong=0','checked=65536 wrong=1'),text.replace(markers[1],'SWAP_MARKER').replace(markers[2],markers[1]).replace('SWAP_MARKER',markers[2])]:
 try:r.validate_aop_owner_log(bad,2,3)
 except RuntimeError:pass
 else:raise AssertionError('Corrupt or unordered presentation accepted')
print('Actual presentation helper: geometry/PA/overflow gates, BGRA swizzle, padded strides, ROI guards, capture/write/readback/restore, allocation/refusal/corruption failures and strict log acceptance passed (host only)')
