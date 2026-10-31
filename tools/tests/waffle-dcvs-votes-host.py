from pathlib import Path
import subprocess,tempfile,json
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/waffle_gmu.c').read_text();code=s[s.index('static bool hfi_boot_votes('):s.index('static bool hfi_boot_acd(')]
native=json.loads((r/'work/waffle/gpu/native-dcvs-audit.json').read_text())['before_first_raw']
expected='static const uint32_t expected[2][3]={'+','.join('{'+','.join(str(x)+'u' for x in p[1:])+'}' for p in native)+'};\n'
h=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
static unsigned calls,fail;
static uint32_t sent[2][4];
static bool hfi_exchange(uintptr_t g,uintptr_t a,const uint32_t *p,unsigned n,const char *name,bool zero){
 assert(g==1 && a==2 && n==4 && zero && calls<2);
 assert(!strcmp(name,calls?"NATIVE_DDR_AB":"MINIMUM_DCVS"));
 memcpy(sent[calls],p,16);return ++calls!=fail;
}
'''
t=r'''
int main(void){
 assert(hfi_boot_votes(1,2,74)&&calls==1&&sent[0][3]==1);
 for(unsigned probe=75;probe<=80;probe++){
 calls=0;assert(hfi_boot_votes(1,2,probe)&&calls==2);
 for(unsigned i=0;i<2;i++){assert(!memcmp(sent[i]+1,expected[i],12));assert((sent[i][0]&0xfffff)==0x41e);}
 assert(sent[0][0]>>20==32 && sent[1][0]>>20==41);
 for(fail=1;fail<=2;fail++){calls=0;assert(!hfi_boot_votes(1,2,probe)&&calls==fail);}
 fail=0;
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(h+code+expected+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'t.c'),'-o',str(p/'t')],check=True);subprocess.run([str(p/'t')],check=True)
print('Actual DCVS helper matches native frequency/AB+IB pair; old profile and every ACK failure stop passed')
