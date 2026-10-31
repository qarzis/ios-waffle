"""Production PAS13 orchestration: native ABI/order and first-failure retention."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[2]
v=root/'work/waffle/gpu/vendor'
pm4=(v/'adreno_pm4types.h').read_text()
def func(name):return re.search(r'static inline uint '+name+r'\([^}]+\n\}',pm4)[0]
native=func('pm4_calc_odd_parity_bit')+'\n'+func('cp_type7_packet')
source=(root/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
packet=re.search(r'const uint32_t packet\[\]=\{\(43u<<20\).*?;',source)[0]
image=(root/'work/waffle/gpu/android-capture2/gen70900_zap.mbn').read_bytes()
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_zap_load.h"
typedef uint32_t uint;
#define CP_TYPE7_PKT (7u<<28)
static unsigned calls,copies,fail_step;
static bool service_failure;
static bool call(void *ctx,uint32_t fn,uint32_t info,const uint64_t *a,uint64_t *ret) {
 assert(ctx==(void *)1);unsigned n=calls++;
 const unsigned commands[]={7,1,2,5};
 assert(n<4 && fn==(0x42000200|commands[n]) && a[0]==13 && !a[3]);
 assert(info==(n==1?0x82:n==2?3:1));
 if(n==1)assert(a[1]==0x1230000 && !a[2]);
 else if(n==2)assert(a[1]==0x9b09a000 && a[2]==4096 && !copies);
 else assert(!a[1] && !a[2]);
 if(n==3)assert(copies==1);
 if(fail_step==n+1){*ret=service_failure?(n==0?0:1):0;return service_failure;}
 *ret=n==0?1:0;return true;
}
static bool copy(void *ctx,const uint8_t *bytes,unsigned size,unsigned memory) {
 assert(ctx==(void *)1 && calls==3 && !copies && size==1072 && memory==4096);
 assert(!memcmp(bytes,image+4096,size));++copies;return fail_step!=5;
}
'''
# Declare firmware before callbacks (never saved in Git/generated source).
h=h.replace('static unsigned calls,','static const uint8_t image[]={'+','.join(map(str,image))+'};\nstatic unsigned calls,')
t=r'''
int main(void) {
 struct waffle_zap_io io={(void *)1,call,copy};struct waffle_zap_state state;
 for(unsigned service=0;service<2;++service)for(fail_step=0;fail_step<=5;++fail_step) {
  calls=copies=0;service_failure=service;
  bool ok=waffle_zap_load(&io,image,sizeof(image),0x1230000,&state);
  assert(ok==(fail_step==0) && state.authenticated==ok);
  assert(state.retain==(fail_step!=1));
  assert(calls==(fail_step==0?4:fail_step==5?3:fail_step));
  assert(copies==(fail_step==0 || fail_step>=4));
 }
 calls=0;assert(!waffle_zap_load(&io,image,sizeof(image),0x1230001,&state) && !calls && !state.retain);
 assert(!waffle_zap_load(&io,image,100,0x1230000,&state) && !calls);
 assert(!waffle_zap_load(NULL,image,sizeof(image),0x1230000,&state) && !calls);
'''
t+=packet+'\nassert(packet[0]==((43u<<20)|(3u<<8)|131u) && packet[1]==cp_type7_packet(0x66,1) && !packet[2]);\nreturn 0;\n}\n'
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+native+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual PAS13 sequence/ABI, payload order, native PM4 secure switch and failure retention passed (host only)')
