#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef void *IOSurfaceRef;
#define kIOSurfaceLockReadOnly 1
#define KERN_SUCCESS 0
struct eagl {int unused;};
struct image {bool shared,target,invert,alpha_first,wrapped;GLuint texture,mirror;GLenum to,format,type,internal;unsigned plane,seed;int width,height;IOSurfaceRef surface;};
static int pid=1,fail_lock,fail_tex,fail_unlock,locks,unlocks,uploads;static GLenum error;
static GLint bound=10,length=9,alignment=8,skip_rows=4,skip_pixels=3,buffer=8;
static uint32_t source[752*1624];
static int getpid(void){return pid;}
static unsigned IOSurfaceGetPixelFormat(IOSurfaceRef s){assert(s==source);return 0x42475241;}
static size_t IOSurfaceGetPlaneCount(IOSurfaceRef s){(void)s;return 0;}
static size_t IOSurfaceGetBytesPerElement(IOSurfaceRef s){(void)s;return 4;}
static size_t IOSurfaceGetWidth(IOSurfaceRef s){(void)s;return 750;}
static size_t IOSurfaceGetHeight(IOSurfaceRef s){(void)s;return 1624;}
static size_t IOSurfaceGetBytesPerRow(IOSurfaceRef s){(void)s;return 3008;}
static int IOSurfaceLock(IOSurfaceRef s,unsigned o,void *seed){assert(s==source&&o==1&&!seed);locks++;return fail_lock;}
static int IOSurfaceUnlock(IOSurfaceRef s,unsigned o,void *seed){assert(s==source&&o==1&&!seed);unlocks++;return fail_unlock;}
static void *IOSurfaceGetBaseAddress(IOSurfaceRef s){return s;}
static unsigned IOSurfaceGetSeed(IOSurfaceRef s){(void)s;return 17;}
static unsigned IOSurfaceGetID(IOSurfaceRef s){(void)s;return 1;}
static GLenum internal_format(GLenum a,GLenum b){assert(a==GL_RGBA&&b==GL_BGRA);return GL_RGBA;}
static void say(const char *s,...){(void)s;}
GLenum glGetError(void){GLenum e=error;error=0;return e;}
void glGetIntegerv(GLenum p,GLint *v){switch(p){case GL_TEXTURE_BINDING_2D:*v=bound;break;case GL_UNPACK_ROW_LENGTH:*v=length;break;case GL_UNPACK_ALIGNMENT:*v=alignment;break;case GL_UNPACK_SKIP_ROWS:*v=skip_rows;break;case GL_UNPACK_SKIP_PIXELS:*v=skip_pixels;break;case GL_PIXEL_UNPACK_BUFFER_BINDING:*v=buffer;break;default:assert(0);}}
void glBindTexture(GLenum t,GLuint n){assert(t==GL_TEXTURE_2D);bound=n;}
void glBindBuffer(GLenum t,GLuint n){assert(t==GL_PIXEL_UNPACK_BUFFER);buffer=n;}
void glPixelStorei(GLenum p,GLint v){switch(p){case GL_UNPACK_ROW_LENGTH:length=v;break;case GL_UNPACK_ALIGNMENT:alignment=v;break;case GL_UNPACK_SKIP_ROWS:skip_rows=v;break;case GL_UNPACK_SKIP_PIXELS:skip_pixels=v;break;default:assert(0);}}
void glTexImage2D(GLenum t,GLint l,GLint in,GLsizei w,GLsizei h,GLint b,GLenum f,GLenum ty,const void *p){assert(t==GL_TEXTURE_2D&&!l&&in==GL_RGBA&&w==750&&h==1624&&!b&&f==GL_BGRA&&ty==GL_UNSIGNED_BYTE&&p==source);assert(bound==20&&!buffer&&length==752&&alignment==1&&!skip_rows&&!skip_pixels);uploads++;if(fail_tex)error=GL_OUT_OF_MEMORY;}
#include "waffle_eagl_readonly_promote.h"
int main(void){struct eagl e={0};for(unsigned mode=0;mode<6;mode++){struct image image={.shared=true,.texture=20,.to=GL_TEXTURE_2D,.format=GL_BGRA,.type=GL_UNSIGNED_BYTE,.internal=GL_RGBA,.width=750,.height=1624,.surface=source};locks=unlocks=uploads=0;fail_lock=mode==1;fail_tex=mode==2;fail_unlock=mode==3;pid=mode==4?2:1;if(mode==5)image.target=true;assert(waffle_eagl_promote_readonly(&e,&image)==(mode==0));assert(image.shared==(mode!=0));assert(bound==10&&length==9&&alignment==8&&skip_rows==4&&skip_pixels==3&&buffer==8);if(mode==0)assert(image.seed==17&&uploads==1&&locks==1&&unlocks==1);if(mode==1)assert(uploads==0&&locks==1&&unlocks==0);if(mode>=4)assert(!uploads&&!locks&&!unlocks);}puts("PASS actual private RO promotion: PID/output/lock/allocation/unlock refusal, correct CPU stride/PBO reset and full GL restore; mock GPU only");}
