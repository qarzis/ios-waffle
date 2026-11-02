"""Exercise actual bounded upload observation without changing texture data."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
s=(root/'userland/src/eagl.c').read_text()
start=s.index(' if (frame_lines && pixel == 4 &&')
end=s.index(' glGetIntegerv(GL_UNPACK_ALIGNMENT',start)
block=s[start:end]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
struct image {unsigned texture,target,wrapped,invert,format,type;int width,height;};
struct eagl {unsigned frames;};
static unsigned frame_lines,records,last_count,last_nonzero[4];
static unsigned IOSurfaceGetID(void *surface){assert(surface);return 3;}
static void say(const char *fmt,...){
 (void)fmt;va_list ap;va_start(ap,fmt);
 for(unsigned i=0;i<7;i++)(void)va_arg(ap,unsigned);
 (void)va_arg(ap,int);(void)va_arg(ap,int);(void)va_arg(ap,size_t);
 (void)va_arg(ap,unsigned);(void)va_arg(ap,unsigned);
 last_count=va_arg(ap,unsigned);
 for(unsigned c=0;c<4;c++)last_nonzero[c]=va_arg(ap,unsigned);
 (void)va_arg(ap,unsigned);records++;va_end(ap);
}
static void observe(struct eagl *e,struct image *image,uint8_t *base,size_t row,unsigned pixel){
 bool alpha_first=false;void *surface=image;
''' + block + r'''
}
int main(){
 struct eagl e={.frames=70};struct image image={.texture=2,.format=0x80e1,.type=0x1401,.width=375,.height=700};
 size_t row=1536,bytes=row*image.height;uint8_t *data=calloc(1,bytes),*before=malloc(bytes);assert(data && before);
 frame_lines=0;observe(&e,&image,(void *)1,row,4);assert(!records);
 frame_lines=1;observe(&e,&image,data,row,4);assert(records==1 && last_count==16);
 for(unsigned c=0;c<4;c++)assert(!last_nonzero[c]);
 for(unsigned y=0;y<700;y++)for(unsigned x=0;x<375;x++)data[y*row+x*4+3]=255;
 memcpy(before,data,bytes);observe(&e,&image,data,row,4);assert(records==2 && !memcmp(before,data,bytes));
 assert(!last_nonzero[0] && !last_nonzero[1] && !last_nonzero[2] && last_nonzero[3]==16);
 observe(&e,&image,(void *)1,1,4);observe(&e,&image,(void *)1,row,2);assert(records==2);
 for(unsigned i=0;i<200;i++)observe(&e,&image,data,row,4);
 assert(records==96 && !memcmp(before,data,bytes));free(data);free(before);
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual upload observation: transparent/opaque input, padded rows, disabled/invalid stride/type guards,96-record bound and unchanged bytes. No GPU/content correctness claim.')
