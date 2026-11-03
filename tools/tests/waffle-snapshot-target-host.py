"""Reproduce missing IOSurface writeback eligibility with actual drawing code."""
from pathlib import Path
import subprocess,tempfile
s=(Path(__file__).resolve().parents[2]/'userland/src/eagl.c').read_text()
a=s.index('static void\ndrawing(struct eagl *e)');b=s.index('static void\nmy_glBindTexture(',a);fn=s[a:b]
x=fn.index(' /* texImageIOSurface');y=fn.index(' if (e->framebuffer != 0 && e->colour != 0 && (image = image_of(e, e->colour)) != NULL && image->target)',x)
old=(fn[:x]+fn[y:]).replace('drawing(struct','drawing_old(struct',1)
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define GL_TEXTURE_2D 0xde1
#define GL_BGRA 0x80e1
#define GL_UNSIGNED_BYTE 0x1401
#define GL_SCISSOR_TEST 1
#define GL_SCISSOR_BOX 2
struct surf{size_t width,height,planes,bpe;unsigned format;};
struct image{struct surf *surface;unsigned texture,to,format,type,plane,wrapped,invert;int width,height;bool target,drawn,painted,shared,alpha_first;};
struct eagl{unsigned frames,framebuffer,colour;struct image image;struct{unsigned into_display,surface;bool taken,boxed;int box[4];}line;};
static unsigned frame_lines;
static void frame_begin(struct eagl *e){assert(e);}
static struct image *image_of(struct eagl *e,unsigned t){return t==e->image.texture?&e->image:0;}
static unsigned IOSurfaceGetID(struct surf*s){assert(s);return 79;}
static unsigned IOSurfaceGetPixelFormat(struct surf*s){return s->format;}
static size_t IOSurfaceGetPlaneCount(struct surf*s){return s->planes;}
static size_t IOSurfaceGetBytesPerElement(struct surf*s){return s->bpe;}
static size_t IOSurfaceGetWidth(struct surf*s){return s->width;}
static size_t IOSurfaceGetHeight(struct surf*s){return s->height;}
static void say(const char *f,...){(void)f;}
static bool glIsEnabled(int n){(void)n;return false;}
static void glGetIntegerv(int n,int*p){(void)n;(void)p;}
'''+old+fn+r'''
int main(void){
 struct surf surface={750,1624,0,4,'BGRA'};
 struct image input={.surface=&surface,.texture=114,.to=GL_TEXTURE_2D,.format=GL_BGRA,.type=GL_UNSIGNED_BYTE,.width=750,.height=1624};
 struct eagl e={.framebuffer=22,.colour=114,.image=input};
 drawing_old(&e);assert(!e.image.target && !e.image.drawn); /* E110: skipped by frame_end's target&&drawn gate. */
 drawing(&e);assert(e.image.target && e.image.drawn && e.image.painted);
 e.image=input;frame_lines=1;drawing(&e);assert(e.image.target && e.image.drawn);
 for(unsigned bad=0;bad<15;bad++){
  e.image=input;e.framebuffer=22;e.colour=114;surface=(struct surf){750,1624,0,4,'BGRA'};
  switch(bad){case 0:e.framebuffer=0;break;case 1:e.colour=0;break;case 2:e.colour=115;break;case 3:e.image.shared=true;break;
   case 4:e.image.wrapped=1;break;case 5:e.image.alpha_first=true;break;case 6:e.image.to=0;break;case 7:e.image.format=0x1908;break;
   case 8:e.image.type=0x1406;break;case 9:e.image.plane=1;break;case 10:e.image.width=-1;break;case 11:surface.width=751;break;
   case 12:surface.planes=2;break;case 13:surface.bpe=2;break;case 14:surface.format=0;break;}
  drawing(&e);assert(!e.image.target && !e.image.drawn && !e.image.painted);
 }
 e.image=input;e.image.target=true;surface=(struct surf){750,1624,0,4,'BGRA'};drawing(&e);assert(e.image.drawn && e.image.painted);
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-multichar','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual drawing: E110 ordinary FBO source reproduces skipped writeback; candidate marks target/drawn/painted;15 format/geometry/attachment guards, existing target preserved. GL/IOSurface mocked; no hardware claim.')
