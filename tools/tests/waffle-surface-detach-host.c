#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static void *hook_surface;
static unsigned IOSurfaceGetID(void *s){(void)s;return 1;}
static int mode,replaced,clears;static GLenum pending_error;
static GLint texture=11,read_fb=4,draw_fb=5,pack=8,row=19;
static GLboolean mask[4]={1,0,1,0},scissor=1;
static GLfloat clear_color[4]={.25,.5,.75,1};
void glGetIntegerv(GLenum n,GLint *v){switch(n){case GL_TEXTURE_BINDING_2D:*v=texture;break;case GL_READ_FRAMEBUFFER_BINDING:*v=read_fb;break;case GL_DRAW_FRAMEBUFFER_BINDING:*v=draw_fb;break;case GL_PACK_ALIGNMENT:*v=pack;break;case GL_PACK_ROW_LENGTH:*v=row;break;default:assert(0);}}
void glGetBooleanv(GLenum n,GLboolean *v){assert(n==GL_COLOR_WRITEMASK);memcpy(v,mask,sizeof(mask));}
void glGetFloatv(GLenum n,GLfloat *v){assert(n==GL_COLOR_CLEAR_VALUE);memcpy(v,clear_color,sizeof(clear_color));}
GLboolean glIsEnabled(GLenum n){assert(n==GL_SCISSOR_TEST);return scissor;}
GLenum glGetError(void){GLenum e=pending_error;pending_error=0;return e;}
void glBindTexture(GLenum t,GLuint n){assert(t==GL_TEXTURE_2D);texture=n;}
void glTexImage2D(GLenum t,GLint l,GLint in,GLsizei w,GLsizei h,GLint border,GLenum f,GLenum ty,const void *p){assert(t==GL_TEXTURE_2D && !l && in==GL_RGBA && w==750 && h==1624 && !border && f==GL_RGBA && ty==GL_UNSIGNED_BYTE && !p);if(mode==1)pending_error=GL_INVALID_OPERATION;else replaced=1;}
void glGenFramebuffers(GLsizei n,GLuint *p){assert(n==1);*p=9;}
void glBindFramebuffer(GLenum t,GLuint n){if(t==GL_FRAMEBUFFER)read_fb=draw_fb=n;else if(t==GL_READ_FRAMEBUFFER)read_fb=n;else if(t==GL_DRAW_FRAMEBUFFER)draw_fb=n;else assert(0);}
void glFramebufferTexture2D(GLenum t,GLenum a,GLenum to,GLuint n,GLint l){assert(t==GL_FRAMEBUFFER&&a==GL_COLOR_ATTACHMENT0&&to==GL_TEXTURE_2D&&!l);if(n)assert(replaced);}
GLenum glCheckFramebufferStatus(GLenum t){assert(t==GL_FRAMEBUFFER);return mode==2?GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT:GL_FRAMEBUFFER_COMPLETE;}
void glDisable(GLenum n){assert(n==GL_SCISSOR_TEST);scissor=0;}
void glEnable(GLenum n){assert(n==GL_SCISSOR_TEST);scissor=1;}
void glColorMask(GLboolean a,GLboolean b,GLboolean c,GLboolean d){mask[0]=a;mask[1]=b;mask[2]=c;mask[3]=d;}
void glClearColor(GLfloat a,GLfloat b,GLfloat c,GLfloat d){clear_color[0]=a;clear_color[1]=b;clear_color[2]=c;clear_color[3]=d;}
void glClear(GLbitfield b){assert(replaced && b==GL_COLOR_BUFFER_BIT && !scissor && mask[0]&&mask[1]&&mask[2]&&mask[3]);clears++;}
void glPixelStorei(GLenum n,GLint v){if(n==GL_PACK_ALIGNMENT)pack=v;else if(n==GL_PACK_ROW_LENGTH)row=v;else assert(0);}
void glReadPixels(GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,void *p){assert(!x&&!y&&w==750&&h==1624&&f==GL_RGBA&&t==GL_UNSIGNED_BYTE&&replaced&&clears==1);uint32_t *v=p;for(unsigned i=0;i<750*1624;i++)v[i]=0xff00ff00;if(mode==3)v[750*1624-1]=0;if(mode==4)pending_error=GL_INVALID_OPERATION;}
void glDeleteFramebuffers(GLsizei n,const GLuint *p){assert(n==1&&*p==9);}
#include "waffle_surface_detach_probe.h"
int main(void){for(mode=0;mode<5;mode++){replaced=clears=0;assert(check_surface_detach(20)==(mode==0));assert(texture==11&&read_fb==4&&draw_fb==5&&pack==8&&row==19&&scissor==1&&mask[0]&&!mask[1]&&mask[2]&&!mask[3]&&clear_color[0]==.25&&clear_color[1]==.5&&clear_color[2]==.75&&clear_color[3]==1);if(mode==1||mode==2)assert(clears==0);}puts("PASS actual detach probe: replacement/FBO failure prevents render; last-pixel corruption/read error refused; GL state restored. Mock GPU only.");}
