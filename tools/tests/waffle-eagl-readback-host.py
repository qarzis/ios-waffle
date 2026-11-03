"""Actual target_to_surface code:orientation, padded rows, calls and fallback."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'userland/src/eagl.c').read_text()
code=s[s.index('static void\ntarget_to_surface('):s.index('#define GL_TEXTURE_WIDTH')]
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned GLuint,GLenum;typedef int GLint,GLsizei;
#define GL_READ_FRAMEBUFFER_BINDING 1
#define GL_DRAW_FRAMEBUFFER_BINDING 2
#define GL_READ_FRAMEBUFFER 3
#define GL_DRAW_FRAMEBUFFER 4
#define GL_FRAMEBUFFER 5
#define GL_COLOR_ATTACHMENT0 6
#define GL_TEXTURE_2D 7
#define GL_COLOR_BUFFER_BIT 8
#define GL_NEAREST 9
#define GL_PACK_ROW_LENGTH 10
#define GL_PACK_ALIGNMENT 11
#define GL_BGRA 12
#define GL_UNSIGNED_BYTE 13
struct surface {uint8_t *base;size_t row;bool locked;};typedef struct surface *IOSurfaceRef;
struct eagl {unsigned frames;GLuint reader,writer,framebuffer;uint8_t *readback;size_t readback_bytes;};
struct image {GLuint mirror,texture;bool invert,drawn,shared;GLsizei width,height;IOSurfaceRef surface;};
static unsigned reads,allocations;static GLint pack_row,bound;static bool fail_alloc,fail_lock;
static uint64_t now_us(void){return 100;}
static int getpid(void){return 1;}
static unsigned frame_lines;
static void say(const char *fmt,...){(void)fmt;}
static unsigned IOSurfaceGetID(IOSurfaceRef s){assert(s);return 79;}
static void *scratch_realloc(void *p,size_t bytes){allocations++;return fail_alloc?NULL:realloc(p,bytes);}
#define realloc scratch_realloc
static size_t IOSurfaceGetBytesPerRow(IOSurfaceRef s){return s->row;}
static int IOSurfaceLock(IOSurfaceRef s,unsigned flags,void *seed){assert(!flags && !seed);if(fail_lock)return 1;assert(!s->locked);s->locked=true;return 0;}
static void IOSurfaceUnlock(IOSurfaceRef s,unsigned flags,void *seed){assert(s->locked && !flags && !seed);s->locked=false;}
static uint8_t *IOSurfaceGetBaseAddress(IOSurfaceRef s){assert(s->locked);return s->base;}
static void glGetIntegerv(GLenum p,GLint *v){(void)p;(void)v;assert(0);}
static void glGenFramebuffers(unsigned n,GLuint *out){assert(n==1);*out=123;}
static void glBindFramebuffer(GLenum to,GLuint fbo){assert(to==GL_FRAMEBUFFER);bound=fbo;}
static void glFramebufferTexture2D(GLenum to,GLenum attachment,GLenum target,GLuint tex,unsigned level){assert(to==GL_FRAMEBUFFER && attachment==GL_COLOR_ATTACHMENT0 && target==GL_TEXTURE_2D && tex==42 && !level);}
static void glBlitFramebuffer(int a,int b,int c,int d,int e,int f,int g,int h,unsigned mask,unsigned filter){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)mask;(void)filter;assert(0);}
static void glPixelStorei(GLenum p,GLint v){if(p==GL_PACK_ROW_LENGTH){assert(v>=0);pack_row=v;}else assert(p==GL_PACK_ALIGNMENT && v==4);}
static uint32_t pixel(unsigned x,unsigned y){return 0x53140000u^(y*0x101u)^x;}
static void glReadPixels(GLint x,GLint y,GLsizei w,GLsizei h,GLenum format,GLenum type,void *out){
 assert(x==0 && y>=0 && w>0 && h>0 && format==GL_BGRA && type==GL_UNSIGNED_BYTE && out);reads++;
 size_t stride=pack_row?(size_t)pack_row*4:(size_t)w*4;
 for(unsigned yy=0;yy<(unsigned)h;yy++)for(unsigned xx=0;xx<(unsigned)w;xx++){
  uint32_t value=pixel(xx,y+yy);memcpy((uint8_t *)out+yy*stride+xx*4,&value,4);
 }
}
'''
test=r'''
static void check(struct surface *surface,unsigned width,unsigned height,bool invert){
 for(unsigned y=0;y<height;y++){
  for(unsigned x=0;x<width;x++){uint32_t value;memcpy(&value,surface->base+y*surface->row+x*4,4);assert(value==pixel(x,invert?height-1-y:y));}
  for(size_t x=width*4;x<surface->row;x++)assert(surface->base[y*surface->row+x]==0xa5);
 }
}
int main(void){
 struct eagl e={.framebuffer=77};
 const unsigned dimensions[][3]={{1,1,16},{3,5,32},{750,1624,3072},{16,16,128}};
 for(unsigned n=0;n<4;n++)for(unsigned inv=0;inv<2;inv++){
  unsigned w=dimensions[n][0],h=dimensions[n][1];size_t row=dimensions[n][2];
  size_t bytes=row*h;uint8_t *storage=malloc(bytes+32);assert(storage);memset(storage,0xa5,bytes+32);
  struct surface surface={.base=storage+16,.row=row};
  struct image image={.texture=42,.invert=inv,.drawn=true,.width=w,.height=h,.surface=&surface};
  reads=0;target_to_surface(&e,&image);
  assert(!image.drawn && !surface.locked && !pack_row && bound==77);
#ifdef WAFFLE_GL_BATCH_READBACK
  assert(reads==1);
#else
  assert(reads==(inv?h:1));
#endif
  check(&surface,w,h,inv);
  for(unsigned i=0;i<16;i++)assert(storage[i]==0xa5 && storage[bytes+16+i]==0xa5);
  unsigned previous_allocations=allocations;reads=0;image.drawn=true;
  target_to_surface(&e,&image);assert(allocations==previous_allocations);check(&surface,w,h,inv);
  fail_lock=true;reads=0;target_to_surface(&e,&image);assert(!reads && !surface.locked && !pack_row);fail_lock=false;
  free(storage);
 }
#ifdef WAFFLE_GL_BATCH_READBACK
 free(e.readback);e.readback=NULL;e.readback_bytes=0;fail_alloc=true;
 uint8_t storage[64*5];memset(storage,0xa5,sizeof(storage));struct surface surface={.base=storage,.row=64};
 struct image image={.texture=42,.invert=true,.drawn=true,.width=3,.height=5,.surface=&surface};
 reads=0;target_to_surface(&e,&image);assert(reads==5 && !e.readback && !e.readback_bytes);check(&surface,3,5,true);
 fail_alloc=false;target_to_surface(&e,&image);assert(e.readback && e.readback_bytes==60);
 void *previous=e.readback;size_t previous_bytes=e.readback_bytes;fail_alloc=true;image.width=8;reads=0;
 target_to_surface(&e,&image);assert(reads==5 && e.readback==previous && e.readback_bytes==previous_bytes);check(&surface,8,5,true);
#endif
 free(e.readback);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(h+code+test)
 for batch in [False,True]:
  subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',
   '-DWAFFLE_GL_PROFILE_READBACK',*(['-DWAFFLE_GL_BATCH_READBACK'] if batch else []),
   '-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
print('HOST actual EAGL readback:legacy1624 row reads vs one packed read at750x1624, independent per-pixel orientation/BGRA/padding/canary checks, non-inverted path/state restore/scratch reuse/lockfailure and first/growth allocationfailure fallback. GL and IOSurface mocked; no GPU/FPS claim.')
