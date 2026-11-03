"""Compile the actual typed native GL read wrapper with an opaque PBO pointer."""
from pathlib import Path
import subprocess,tempfile
s=(Path(__file__).resolve().parents[2]/'userland/src/eagl.c').read_text()
b=s[s.index('static void\nmy_glReadPixels('):s.index('static void\nmy_glCopyTexSubImage2D(')]
code=r"""
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>
#include <assert.h>
typedef int GLint,GLsizei;typedef unsigned GLenum;
struct eagl{unsigned frames,framebuffer,colour;};
static unsigned frame_lines,eagl_tracing,calls,logs,enters,leaves;
#define EAGL_ENTER(e,n) do{assert((e)!=0 && (n)==0x770);enters++;}while(0)
#define EAGL_LEAVE(e,n) do{assert((e)!=0 && (n)==0x770);leaves++;}while(0)
static void eagl_trace(const char *f,...){(void)f;}
static void say(const char *f,...){(void)f;logs++;assert(calls==leaves+1);}
static const void *_dyld_get_shared_cache_range(size_t *n){*n=0;return 0;}
static void glReadPixels(GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,void *p){
 assert(x==-3 && y==5 && (w==750 || w==-1) && h==1624 && f==0x80e1 && t==0x1401 && p==(void *)(uintptr_t)0x100000001UL);calls++;
}
"""+b+r"""
int main(void){struct eagl e={7,8,9};void *p=(void *)(uintptr_t)0x100000001UL;
 my_glReadPixels(&e,-3,5,750,1624,0x80e1,0x1401,p);assert(!logs);
 frame_lines=1;my_glReadPixels(&e,-3,5,-1,1624,0x80e1,0x1401,p);assert(!logs);
 eagl_tracing=1;for(unsigned i=0;i<100;i++)my_glReadPixels(&e,-3,5,750,1624,0x80e1,0x1401,p);
 assert(logs==32 && calls==102 && enters==calls && leaves==calls);
}
"""
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual readpixels wrapper: typed argument forwarding, opaque64bit PBO offset never dereferenced, always one Mesa call, enter/leave pairing, diagnostics disabled/small/32-record cap. Host only.')
