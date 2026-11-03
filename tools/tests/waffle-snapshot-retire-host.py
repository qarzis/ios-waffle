"""Actual image lifetime functions must publish before releasing the surface."""
from pathlib import Path
import subprocess,tempfile
s=(Path(__file__).resolve().parents[2]/'userland/src/eagl.c').read_text()
a=s.index('static struct image *\nimage_of(');b=s.index('static GLenum\ninternal_format(',a);functions=s[a:b]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
typedef int GLint;typedef unsigned GLuint;
#define GL_READ_FRAMEBUFFER_BINDING 1
#define GL_DRAW_FRAMEBUFFER_BINDING 2
#define GL_PACK_ROW_LENGTH 3
#define GL_PACK_ALIGNMENT 4
#define GL_PACK_SKIP_ROWS 5
#define GL_PACK_SKIP_PIXELS 6
#define GL_PIXEL_PACK_BUFFER_BINDING 7
#define GL_PIXEL_PACK_BUFFER 8
#define GL_READ_FRAMEBUFFER 9
#define GL_DRAW_FRAMEBUFFER 10
struct surface {unsigned id,refs,published;};typedef struct surface *IOSurfaceRef;
struct image {unsigned texture,mirror;IOSurfaceRef surface;bool target,drawn,shared;int width,height;};
struct eagl {unsigned frames,image_count;struct image images[2];};
static int state[8]={0,21,22,1792,8,3,5,97};
static unsigned frame_lines=1,copies,queries,releases,mirror_deletes;
static void say(const char *f,...){(void)f;}
static unsigned IOSurfaceGetID(IOSurfaceRef s){assert(s->refs);return s->id;}
static void *CFRetain(IOSurfaceRef s){assert(s->refs);s->refs++;return s;}
static void CFRelease(IOSurfaceRef s){assert(s->refs);s->refs--;releases++;}
static void glGetIntegerv(unsigned n,int *p){assert(n>=1 && n<=7);*p=state[n];queries++;}
static void glBindBuffer(unsigned n,unsigned v){assert(n==GL_PIXEL_PACK_BUFFER);state[7]=(int)v;}
static void glPixelStorei(unsigned n,int v){assert(n>=3 && n<=6);state[n]=v;}
static void glBindFramebuffer(unsigned n,unsigned v){assert(n==9 || n==10);state[n==9?1:2]=(int)v;}
static void glDeleteTextures(int n,unsigned *p){assert(n==1 && *p);mirror_deletes++;}
'''+functions+r'''
static void target_to_surface(struct eagl *e,struct image *im){
 (void)e;assert(im->surface->refs && im->target && im->drawn && !im->shared && !im->mirror);
 assert(!state[7] && !state[5] && !state[6]);
 im->surface->published++;im->drawn=false;copies++;
 state[1]=state[2]=123;state[3]=0;state[4]=4;
}
int main(void){
 struct surface a={79,1,0},b={90,1,0};int saved[8];memcpy(saved,state,sizeof(state));
 struct image original={.texture=114,.surface=&a,.target=true,.drawn=true,.width=750,.height=1624};
 struct eagl e={.image_count=1,.images={original}};
 image_forget(&e,114);assert(!e.image_count && a.refs==0 && a.published==1 && copies==1 && releases==1);
 assert(!memcmp(state,saved,sizeof(state)));
 a.refs=1;e.image_count=1;e.images[0]=original;
 struct image *new=image_new(&e,114,&b);assert(new && new->surface==&b && !new->target && !new->drawn);
 assert(!a.refs && a.published==2 && b.refs==2 && copies==2 && releases==2);
 assert(!memcmp(state,saved,sizeof(state)));
 unsigned before=queries;image_forget(&e,999);assert(queries==before && e.image_count==1);
 image_forget(&e,114);assert(!e.image_count && b.refs==1 && copies==2 && queries==before);
 // New image allocation must not publish an uninitialized slot.
 new=image_new(&e,5,&b);assert(new && b.refs==2 && copies==2);
 new->mirror=77;new->target=true;new->drawn=true;image_forget(&e,5);assert(copies==2 && mirror_deletes==1 && b.refs==1);
 new=image_new(&e,6,&b);new->target=true;new->drawn=true;new->shared=true;image_forget(&e,6);assert(copies==2 && b.refs==1);
 assert(!memcmp(state,saved,sizeof(state)));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual image lifetime: pending delete/rebind publishes before release/reset; independent read/draw FBO and pack row/alignment/skips/PBO restored; idle/unknown/new/shared/mirror guards. Readback mocked; no GPU claim.')
