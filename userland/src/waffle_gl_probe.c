/* Controlled first real GL renderer test. Hardware success requires kernel
 * GENERAL_SUBMIT fence evidence and independent Android recovery as well. */
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <GL/gl.h>
#include <GL/glext.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
extern int reboot(int);
#define RB_HALT 8
static uint32_t pixels[256];
static GLuint compile(GLenum type,const char *text)
{
 GLuint s=glCreateShader(type);glShaderSource(s,1,&text,NULL);glCompileShader(s);GLint ok=0;glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
 if(!ok){char log[2048];glGetShaderInfoLog(s,sizeof(log),NULL,log);printf("waffle-gl-user: shader failed %s\n",log);return 0;}return s;
}
int main(void)
{
 setbuf(stdout,NULL);setbuf(stderr,NULL);
 printf("waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16\n");
 setenv("WAFFLE_GPU_DRM","1",1);setenv("OSMESA_SOFTWARE","0",1);
 int ok=0;OSMesaContext ctx=NULL;
 const int attrs[]={OSMESA_FORMAT,OSMESA_RGBA,OSMESA_PROFILE,OSMESA_CORE_PROFILE,OSMESA_CONTEXT_MAJOR_VERSION,3,OSMESA_CONTEXT_MINOR_VERSION,3,0};
 ctx=OSMesaCreateContextAttribs(attrs,NULL);
 if(!ctx){printf("waffle-gl-user: context failed\n");goto finish;}
 for(unsigned i=0;i<256;i++)pixels[i]=0xdead0000u+i;
 if(!OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16)){printf("waffle-gl-user: makecurrent failed\n");goto finish;}
 const char *renderer=(const char *)glGetString(GL_RENDERER);
 printf("waffle-gl-user: renderer=%s version=%s\n",renderer?renderer:"NULL",glGetString(GL_VERSION));
 if(!renderer || !strstr(renderer,"FD750")){printf("waffle-gl-user: GPU renderer not selected\n");goto finish;}
 GLuint vs=compile(GL_VERTEX_SHADER,"#version 330 core\nconst vec2 p[3]=vec2[3](vec2(-1,-1),vec2(1,-1),vec2(0,1));void main(){gl_Position=vec4(p[gl_VertexID],0,1);}");
 GLuint fs=compile(GL_FRAGMENT_SHADER,"#version 330 core\nout vec4 color;void main(){color=vec4(1,0.25,0,1);}");
 if(!vs || !fs)goto finish;
 GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);
 if(!linked){printf("waffle-gl-user: link failed\n");goto finish;}
 GLuint vao;glGenVertexArrays(1,&vao);glBindVertexArray(vao);
 glDisable(GL_DITHER);glViewport(0,0,16,16);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glUseProgram(program);glDrawArrays(GL_TRIANGLES,0,3);glFinish();
 GLenum error=glGetError();unsigned wrong=0,inside=0;
 for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
  bool filled=(4*x+2>2*y+1) && (4*x+2<63-2*y);
  uint32_t expected=filled?0xff0040ffu:0xff000000u;
  if(filled)inside++;if(pixels[y*16+x]!=expected)wrong++;
 }
 printf("waffle-gl-user: checked=256 wrong=%u filled=%u GL_error=%x\n",wrong,inside,error);
 for(unsigned i=0;i<256;i+=8)printf("waffle-gl-user: pixels offset=%u values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x\n",i,pixels[i],pixels[i+1],pixels[i+2],pixels[i+3],pixels[i+4],pixels[i+5],pixels[i+6],pixels[i+7]);
 ok=!wrong && !error && inside==128;
 glDeleteVertexArrays(1,&vao);glDeleteProgram(program);glDeleteShader(vs);glDeleteShader(fs);
finish:
 if(ctx)OSMesaDestroyContext(ctx);
 /* The libdrm shim caches a duplicate device fd. Close every non-console fd
  * in this isolated PID1 before reporting success or halting the machine. */
 for(int fd=3;fd<256;fd++)close(fd);
 printf("waffle-gl-user: result=%d actual_OSMesa=1\n",ok);
 reboot(RB_HALT);for(;;){}
}
