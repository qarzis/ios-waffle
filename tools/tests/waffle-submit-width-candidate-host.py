"""Rejected E66 access width: preserved byte-equivalence forensic model.

Uses synthetic command words and CPU memory. Experimental fixture only; current runtime uses the qualified scalar path.
"""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_gpu_submit.h"
_Static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__,"Model target is little endian ARM64");
static struct waffle_gpu_submit_check_result scalar_check(const volatile uint32_t *out,unsigned words,const uint32_t *commands,uint32_t fence,uint64_t va,bool done){
 struct waffle_gpu_submit_check_result result={0};
 for(unsigned i=0;i<4096;i++){
  uint32_t got=out[i],expected=waffle_gpu_submit_initial(i,words,commands,fence,va,done);
  if(got!=expected){if(!result.wrong){result.first=i;result.got=got;result.expected=expected;}result.wrong++;}
 }
 return result;
}
static uint32_t left[4128] __attribute__((aligned(64))),right[4128] __attribute__((aligned(64)));
static uint32_t commands[1536];
int main(void){
 for(unsigned i=0;i<1536;i++)commands[i]=0x53140000u^(i*0x10203u);
 const unsigned lengths[]={1,16,310,1536};const uint32_t fences[]={1,1024,4051,UINT32_MAX};
 for(unsigned offset=8;offset<=9;offset++)for(unsigned w=0;w<4;w++)for(unsigned f=0;f<4;f++){
  unsigned words=lengths[w];uint32_t fence=fences[f];uint64_t va=0x100002000ULL;
  for(unsigned i=0;i<4128;i++)left[i]=right[i]=0xdeadbeef;
  volatile uint32_t *a=left+offset,*b=right+offset;
  for(unsigned i=0;i<4096;i++)a[i]=waffle_gpu_submit_initial(i,words,commands,fence,va,false);
  waffle_gpu_submit_stage(b,words,commands,fence,va);assert(!memcmp(left,right,sizeof(left)));
  for(unsigned done=0;done<2;done++){
   if(done)a[2048]=b[2048]=fence;
   assert(!waffle_gpu_submit_check(b,words,commands,fence,va,done).wrong);
   if(words==310 && fence==4051){
    for(unsigned i=0;i<4096;i++){
     b[i]^=0x80;struct waffle_gpu_submit_check_result old=scalar_check(b,words,commands,fence,va,done),now=waffle_gpu_submit_check(b,words,commands,fence,va,done);
     assert(old.wrong==1 && old.first==i && !memcmp(&old,&now,sizeof(old)));b[i]^=0x80;
    }
    for(unsigned i=0;i<4096;i+=257)b[i]^=1;
    struct waffle_gpu_submit_check_result old=scalar_check(b,words,commands,fence,va,done),now=waffle_gpu_submit_check(b,words,commands,fence,va,done);
    assert(old.wrong==16 && !memcmp(&old,&now,sizeof(old)));
    for(unsigned i=0;i<4096;i+=257)b[i]^=1;
   }
   assert(!memcmp(left,right,sizeof(left)));
  }
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(code)
 (p/'waffle_gpu_submit.h').write_text((root/'tools/tests/fixtures/waffle-submit-wide-rejected.h').read_text())
 subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-fstrict-aliasing',
  '-fsanitize=address,undefined','-I',str(p),'-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('HOST rejected width fixture:32/64bit paths initialize identical full16KiB incl guards; all4096 single-word corruptions and multiword faults return identical counts/first-index/actual/expected, before/after completion,4/8-byte alignment,1..1536rootwords/fenceUINTMAX. Explicit may_alias and unaligned32bit fallback. Experimental fixture only; runtime restored to scalar after hardware showed no gain.')
