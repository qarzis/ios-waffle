/* Host-only frontend audit. The stock no-op DRM shim executes NO GPU work. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <gbm.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
static GLuint shader(GLenum type,const char *source){
 GLuint s=glCreateShader(type);glShaderSource(s,1,&source,NULL);glCompileShader(s);
 GLint ok=0;glGetShaderiv(s,GL_COMPILE_STATUS,&ok);if(!ok){char log[2048];glGetShaderInfoLog(s,sizeof(log),NULL,log);fprintf(stderr,"shader: %s\n",log);return 0;}return s;
}
int main(void){
 fprintf(stderr,"HOST ONLY: no-op MSM adapter; GL success does not prove GPU execution\n");
 int fd=open("/dev/dri/renderD128",O_RDWR|O_CLOEXEC);if(fd<0){perror("render node");return 1;}
 struct gbm_device *gbm=gbm_create_device(fd);if(!gbm){fprintf(stderr,"gbm failed\n");return 2;}
 PFNEGLGETPLATFORMDISPLAYEXTPROC display=(void *)eglGetProcAddress("eglGetPlatformDisplayEXT");
 EGLDisplay d=display(EGL_PLATFORM_GBM_KHR,gbm,NULL);EGLint major,minor;
 if(!eglInitialize(d,&major,&minor)){fprintf(stderr,"eglInitialize: %x\n",eglGetError());return 3;}
 eglBindAPI(EGL_OPENGL_ES_API);
 EGLConfig cfg;EGLint count;
 const EGLint attrs[]={EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_SURFACE_TYPE,EGL_WINDOW_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
 if(!eglChooseConfig(d,attrs,&cfg,1,&count) || !count){fprintf(stderr,"config: %x count=%d\n",eglGetError(),count);return 4;}
 const EGLint ctxattrs[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
 EGLContext ctx=eglCreateContext(d,cfg,EGL_NO_CONTEXT,ctxattrs);
 if(ctx==EGL_NO_CONTEXT || !eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,ctx)){fprintf(stderr,"context: %x\n",eglGetError());return 5;}
 fprintf(stderr,"renderer=%s version=%s\n",glGetString(GL_RENDERER),glGetString(GL_VERSION));
 GLuint vs=shader(GL_VERTEX_SHADER,"#version 300 es\nconst vec2 p[3]=vec2[3](vec2(-1,-1),vec2(1,-1),vec2(0,1));void main(){gl_Position=vec4(p[gl_VertexID],0,1);}");
 GLuint fs=shader(GL_FRAGMENT_SHADER,"#version 300 es\nprecision mediump float;out vec4 color;void main(){color=vec4(1,0.25,0,1);}");
 if(!vs || !fs)return 6;
 GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);if(!linked)return 7;
 GLuint tex,fbo;glGenTextures(1,&tex);glBindTexture(GL_TEXTURE_2D,tex);glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,16,16);
 glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0);
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)return 8;
 glViewport(0,0,16,16);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glUseProgram(program);glDrawArrays(GL_TRIANGLES,0,3);glFlush();
 GLenum error=glGetError();fprintf(stderr,"frontend submitted triangle, GL error=%x; NO GPU correctness or pixel readback claim\n",error);
 glDeleteFramebuffers(1,&fbo);glDeleteTextures(1,&tex);glDeleteProgram(program);glDeleteShader(vs);glDeleteShader(fs);
 eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);eglDestroyContext(d,ctx);eglTerminate(d);gbm_device_destroy(gbm);close(fd);
 return error?9:0;
}
