/* Isolated native-texture sampler. Raw Mesa GL, deliberately no EAGL dispatch
 * macros: save/restore its current state and do not change the hook's images. */
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>
#include <string.h>
#include "waffle_surface_sample.h"
static GLuint sample_shader(GLenum type,const char *text)
{
 GLuint shader=glCreateShader(type);glShaderSource(shader,1,&text,NULL);glCompileShader(shader);
 GLint compiled=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&compiled);
 if(!compiled){glDeleteShader(shader);return 0;}return shader;
}
bool waffle_gl_sample_texture(unsigned source_texture,const uint8_t *source,size_t stride,unsigned width,unsigned height,struct waffle_surface_sample_result *r)
{
 if(!r)return false;
 memset(r,0,sizeof(*r));r->stage=1;
 if(!source_texture || !source || !width || !height || stride<(size_t)width*4)return false;
 for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
  unsigned sx=(2*x+1)*width/32,sy=(2*y+1)*height/32;
  uint32_t p;memcpy(&p,source+sy*stride+sx*4,4);
  r->expected[y*16+x]=(p&0xff00ff00u)|((p&255u)<<16)|((p>>16)&255u);
  r->pixels[y*16+x]=0xdead0000u+y*16+x;
 }
 GLint program_old=0,draw_old=0,read_old=0,viewport[4],active_old=0,texture_old=0;
 GLint pack_old=0,row_old=0,skip_row_old=0,skip_pixel_old=0,pbo_old=0;
 glGetIntegerv(GL_CURRENT_PROGRAM,&program_old);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw_old);
 glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read_old);glGetIntegerv(GL_VIEWPORT,viewport);
 glGetIntegerv(GL_ACTIVE_TEXTURE,&active_old);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&texture_old);
 glGetIntegerv(GL_PACK_ALIGNMENT,&pack_old);glGetIntegerv(GL_PACK_ROW_LENGTH,&row_old);
 glGetIntegerv(GL_PACK_SKIP_ROWS,&skip_row_old);glGetIntegerv(GL_PACK_SKIP_PIXELS,&skip_pixel_old);
 glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&pbo_old);
 GLboolean blend=glIsEnabled(GL_BLEND),depth=glIsEnabled(GL_DEPTH_TEST),scissor=glIsEnabled(GL_SCISSOR_TEST);
 GLuint vs=0,fs=0,program=0,target=0,framebuffer=0;bool ok=false;
 r->stage=2;
 if(glGetError()!=GL_NO_ERROR)goto done;
 vs=sample_shader(GL_VERTEX_SHADER,"#version 300 es\nconst vec2 p[3]=vec2[3](vec2(-1,-1),vec2(3,-1),vec2(-1,3));out vec2 uv;void main(){vec2 q=p[gl_VertexID];uv=(q+1.0)*0.5;gl_Position=vec4(q,0,1);}");
 fs=sample_shader(GL_FRAGMENT_SHADER,"#version 300 es\nprecision highp float;uniform sampler2D src;in vec2 uv;out vec4 color;void main(){color=texture(src,uv);}");
 if(!vs || !fs)goto done;
 program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);
 GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);r->stage=3;if(!linked)goto done;
 glGenTextures(1,&target);glBindTexture(GL_TEXTURE_2D,target);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,16,16,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);r->stage=4;
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)goto done;
 glBindTexture(GL_TEXTURE_2D,source_texture);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glUseProgram(program);GLint sampler=glGetUniformLocation(program,"src");r->stage=5;if(sampler<0)goto done;
 glUniform1i(sampler,0);glViewport(0,0,16,16);glDisable(GL_BLEND);glDisable(GL_DEPTH_TEST);glDisable(GL_SCISSOR_TEST);
 glDrawArrays(GL_TRIANGLES,0,3);glFinish();r->stage=6;
 glBindBuffer(GL_PIXEL_PACK_BUFFER,0);glPixelStorei(GL_PACK_ALIGNMENT,4);glPixelStorei(GL_PACK_ROW_LENGTH,0);
 glPixelStorei(GL_PACK_SKIP_ROWS,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);
 glReadPixels(0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,r->pixels);r->error=glGetError();
 for(unsigned i=0;i<256;i++)r->wrong+=r->pixels[i]!=r->expected[i];
 ok=!r->wrong && !r->error;r->stage=7;
 done:
 glUseProgram(program_old);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw_old);glBindFramebuffer(GL_READ_FRAMEBUFFER,read_old);
 glViewport(viewport[0],viewport[1],viewport[2],viewport[3]);
 glBindBuffer(GL_PIXEL_PACK_BUFFER,pbo_old);glPixelStorei(GL_PACK_ALIGNMENT,pack_old);glPixelStorei(GL_PACK_ROW_LENGTH,row_old);
 glPixelStorei(GL_PACK_SKIP_ROWS,skip_row_old);glPixelStorei(GL_PACK_SKIP_PIXELS,skip_pixel_old);
 if(blend)glEnable(GL_BLEND);if(depth)glEnable(GL_DEPTH_TEST);if(scissor)glEnable(GL_SCISSOR_TEST);
 glBindTexture(GL_TEXTURE_2D,texture_old);glActiveTexture(active_old);
 if(framebuffer)glDeleteFramebuffers(1,&framebuffer);if(target)glDeleteTextures(1,&target);
 if(program)glDeleteProgram(program);if(vs)glDeleteShader(vs);if(fs)glDeleteShader(fs);
 GLenum error=glGetError();if(error){r->error=error;ok=false;}
 return ok;
}
