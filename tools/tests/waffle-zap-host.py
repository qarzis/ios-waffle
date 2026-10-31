from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];data=(r/'work/waffle/gpu/android-capture2/gen70900_zap.mbn').read_bytes()
h='''#include <assert.h>\n#include <string.h>\n#include "waffle_zap.h"\n'''
h+='static const uint8_t image[]={'+','.join(str(b) for b in data)+'};\n'
t=r'''
static void put(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=n>>(8*i);}
int main(void){
 struct waffle_zap_image p;
 assert(waffle_zap_parse(image,sizeof(image),&p));
 assert(p.header_bytes==148 && p.hash_offset==8192 && p.hash_bytes==3896);
 assert(p.payload_offset==4096 && p.payload_bytes==1072 && p.memory_bytes==4096 && p.relocation==4096);
 for(unsigned n=0;n<sizeof(image);n++)assert(!waffle_zap_parse(image,n,&p));
 uint8_t copy[sizeof(image)];
 unsigned offsets[]={0,4,5,18,28,40,42,44,52,56,68,84+4,84+16,84+20,84+24,116,116+4,116+16};
 for(unsigned i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++){
  memcpy(copy,image,sizeof(copy));put(copy+offsets[i],0xffffffff);
  assert(!waffle_zap_parse(copy,sizeof(copy),&p));
 }
 assert(!waffle_zap_parse(NULL,0,&p));assert(!waffle_zap_parse(image,sizeof(image),NULL));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(h+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'t.c'),'-o',str(p/'t')],check=True);subprocess.run([str(p/'t')],check=True)
print('Offline signed ZAP ELF bounds/metadata/payload layout, every truncation and corrupt header tests passed; no hardware action')
