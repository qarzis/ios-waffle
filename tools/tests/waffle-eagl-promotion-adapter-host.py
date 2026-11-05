#!/usr/bin/env python3
"""Actual FBO wrapper must stop before attachment when promotion fails."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2]
s=(r/'userland/src/eagl.c').read_text();start=s.index('static void\nmy_glFramebufferTexture2D(');end=s.index('\nstatic void\nmy_glDeleteFramebuffers',start)
fixture=(r/'tools/tests/waffle-eagl-readonly-promote-host.c').read_text().split('int main(void)')[0].replace('struct eagl {int unused;};','struct eagl {unsigned colour;};')
adapter=r'''
#define WAFFLE_GL_READONLY_SHARED_SOURCE 1
#define EAGL_ENTER(e,n) ((void)(e),(void)(n))
#define EAGL_LEAVE(e,n) ((void)(e),(void)(n))
static int eagl_tracing,attachments;static struct image *mapped;
static void clear_now(struct eagl *e){(void)e;}
static void eagl_trace(const char *s,...){(void)s;}
static struct image *image_of(struct eagl *e,GLuint texture){(void)e;return texture==20?mapped:NULL;}
void glFramebufferTexture2D(GLenum t,GLenum a,GLenum to,GLuint texture,GLint level){assert(a==GL_COLOR_ATTACHMENT0&&to==GL_TEXTURE_2D&&!level);if(texture==20&&t!=GL_READ_FRAMEBUFFER)assert(!mapped->shared);attachments++;}
'''
main=r'''
int main(void){for(unsigned mode=0;mode<6;mode++){struct eagl e={.colour=7};struct image image={.shared=true,.texture=20,.to=GL_TEXTURE_2D,.format=GL_BGRA,.type=GL_UNSIGNED_BYTE,.internal=GL_RGBA,.width=750,.height=1624,.surface=source};mapped=&image;attachments=uploads=locks=unlocks=0;fail_lock=mode==1;fail_tex=mode==2;fail_unlock=mode==3;pid=mode==4?2:1;if(mode==5)image.target=true;
 my_glFramebufferTexture2D(&e,GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,20,0);
 assert(attachments==(mode==0));assert(e.colour==(mode==0?20u:7u));assert(bound==10&&buffer==8&&length==9&&alignment==8&&skip_rows==4&&skip_pixels==3);
 }
 puts("PASS actual EAGL FBO wrapper: failed PID/lock/allocation/unlock/output promotion never attaches readonly storage; mock GL only");}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(fixture+adapter+s[start:end]+main)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-multichar','-fsanitize=address,undefined','-I',str(r/'userland/src'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
