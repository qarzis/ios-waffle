#!/usr/bin/env python3
"""Actual EAGL deferred clear + ReadPixels ordering, including PBO offsets."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'userland/src/eagl.c').read_text()
def function(name):
 start=source.index('static void\n'+name+'(');pos=source.index('{',start);depth=1;end=pos+1
 while depth:
  if source[end]=='{':depth+=1
  if source[end]=='}':depth-=1
  end+=1
 return source[start:end]
preamble=r'''
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
struct eagl {unsigned unclear,colour,clears,frames,framebuffer;bool unclear_boxed;GLint unclear_box[4];GLfloat unclear_colour[4];};
struct group_texture {int state;};
#define GROUP_FRESH 1
#define EAGL_ENTER(e,n) ((void)(e),(void)(n))
#define EAGL_LEAVE(e,n) ((void)(e),(void)(n))
static int eagl_tracing,frame_lines;static bool boxed=true,pbo;
static GLint box[4]={1,2,3,4};static GLfloat color[4]={0,1,0,1};
static uint32_t rendered=0xdeadbeef;static unsigned clear_calls,reads;
static void drawing(struct eagl *e){(void)e;}
static struct group_texture *group_of(struct eagl *e,GLuint t){(void)e;(void)t;return NULL;}
static void eagl_trace(const char *s,...){(void)s;}
static void say(const char *s,...){(void)s;}
static const void *_dyld_get_shared_cache_range(size_t *n){*n=0;return NULL;}
void glGetIntegerv(GLenum n,GLint *v){assert(n==GL_SCISSOR_BOX);for(unsigned i=0;i<4;i++)v[i]=box[i];}
void glGetFloatv(GLenum n,GLfloat *v){assert(n==GL_COLOR_CLEAR_VALUE);for(unsigned i=0;i<4;i++)v[i]=color[i];}
GLboolean glIsEnabled(GLenum n){assert(n==GL_SCISSOR_TEST);return boxed;}
void glEnable(GLenum n){assert(n==GL_SCISSOR_TEST);boxed=true;}
void glDisable(GLenum n){assert(n==GL_SCISSOR_TEST);boxed=false;}
void glScissor(GLint a,GLint b,GLsizei c,GLsizei d){box[0]=a;box[1]=b;box[2]=c;box[3]=d;}
void glClearColor(GLfloat a,GLfloat b,GLfloat c,GLfloat d){color[0]=a;color[1]=b;color[2]=c;color[3]=d;}
void glClear(GLbitfield mask){assert(mask==GL_COLOR_BUFFER_BIT);assert(color[0]==0&&color[1]==1&&color[2]==0&&color[3]==1);assert(boxed&&box[0]==1&&box[1]==2&&box[2]==3&&box[3]==4);rendered=0xff00ff00;clear_calls++;}
void glReadPixels(GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,void *p){assert(x==0&&y==0&&w==1&&h==1&&f==GL_RGBA&&t==GL_UNSIGNED_BYTE);reads++;if(pbo){assert(p==(void *)16);assert(rendered==0xff00ff00);}else *(uint32_t *)p=rendered;}
static void clear_now(struct eagl *e);
'''
main=r'''
int main(void){struct eagl e={.colour=2};uint32_t pixel=0;
 my_glClear(&e,GL_COLOR_BUFFER_BIT);assert(clear_calls==0&&e.unclear);
 /* The queued clear must retain its state, not the caller's later state. */
 boxed=false;box[0]=9;color[1]=0;color[2]=1;
 my_glReadPixels(&e,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,&pixel);
 assert(pixel==0xff00ff00 && clear_calls==1 && !e.unclear);
 assert(!boxed&&box[0]==9&&color[1]==0&&color[2]==1);
 my_glReadPixels(&e,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,&pixel);assert(clear_calls==1&&reads==2);
 boxed=true;box[0]=1;color[1]=1;color[2]=0;my_glClear(&e,GL_COLOR_BUFFER_BIT);
 pbo=true;my_glReadPixels(&e,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,(void *)16);
 assert(clear_calls==2&&!e.unclear);puts("PASS actual EAGL deferred clear materialized before CPU/PBO readback, state restored, no repeated clear; mock GL only");}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(preamble+'\n'.join(function(n) for n in ('my_glClear','clear_now','my_glReadPixels'))+main)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
