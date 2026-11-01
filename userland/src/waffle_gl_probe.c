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
#include <signal.h>
#include <sys/ucontext.h>
#include <mach-o/dyld.h>
#include <mach/arm/thread_status.h>
#include <stdarg.h>
#ifdef WAFFLE_GL_PRESENT
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurfaceRef.h>
#include <IOKit/IOKitLib.h>
#endif
extern int reboot(int);
#define RB_HALT 8
/* Direct console writes remain visible without stdio/launchd initialization. */
static long raw_call(long number,long a,long b,long c)
{
 register long x16 __asm__("x16")=number;
 register long x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c;
 __asm__ volatile("svc #0x80":"+r"(x0):"r"(x16),"r"(x1),"r"(x2):"memory","cc");
 return x0;
}
static int diagnostic_console=-1;
static void direct_log(const char *format,...)
{
 char line[2048];va_list ap;va_start(ap,format);int n=vsnprintf(line,sizeof(line),format,ap);va_end(ap);
 if(n>0)raw_call(4,diagnostic_console>=0?diagnostic_console:1,(long)line,n<(int)sizeof(line)?n:(int)sizeof(line)-1);
}
static void crash_log(int sig,siginfo_t *info,void *context)
{
 ucontext_t *u=context;
 direct_log("waffle-gl-crash: signal=%d fault=%p pc=%llx lr=%llx sp=%llx fp=%llx\n",sig,info->si_addr,
  (unsigned long long)arm_thread_state64_get_pc(u->uc_mcontext->__ss),
  (unsigned long long)arm_thread_state64_get_lr(u->uc_mcontext->__ss),
  (unsigned long long)arm_thread_state64_get_sp(u->uc_mcontext->__ss),
  (unsigned long long)u->uc_mcontext->__ss.__fp);
 for(unsigned i=0;i<8;i++)direct_log("waffle-gl-crash: x%u=%llx\n",i,(unsigned long long)u->uc_mcontext->__ss.__x[i]);
 raw_call(55,8,0,0);for(;;){}
}
#define printf direct_log
static uint32_t pixels[256];
#ifdef WAFFLE_GL_PRESENT
/* Same readback bridge used by eagl.c, through the existing display client.
 * This tests presentation with CPU readback, not direct GPU surface import. */
static bool present_triangle(void)
{
 bool ok=false,locked=false;IOSurfaceRef surface=NULL;io_connect_t display=0;
 printf("waffle-gl-present: begin CPU_readback=1 IOSurface_import=0\n");
 CFMutableDictionaryRef props=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
 if(!props)return false;
 const CFStringRef keys[]={kIOSurfaceWidth,kIOSurfaceHeight,kIOSurfacePixelFormat,kIOSurfaceBytesPerElement};
 const int values[]={16,16,0x42475241,4};
 for(unsigned i=0;i<4;i++){
  CFNumberRef n=CFNumberCreate(NULL,kCFNumberIntType,&values[i]);
  if(!n){CFRelease(props);return false;}CFDictionarySetValue(props,keys[i],n);CFRelease(n);
 }
 surface=IOSurfaceCreate(props);CFRelease(props);
 if(!surface){printf("waffle-gl-present: IOSurfaceCreate failed\n");goto done;}
 size_t row=IOSurfaceGetBytesPerRow(surface),size=IOSurfaceGetAllocSize(surface);
 uint32_t sid=IOSurfaceGetID(surface);
 printf("waffle-gl-present: surface=%u width=%zu height=%zu stride=%zu bytes=%zu\n",sid,IOSurfaceGetWidth(surface),IOSurfaceGetHeight(surface),row,size);
 if(!sid || IOSurfaceGetWidth(surface)!=16 || IOSurfaceGetHeight(surface)!=16 ||
    IOSurfaceGetPixelFormat(surface)!=0x42475241 || IOSurfaceGetPlaneCount(surface) ||
    row<64 || row>4096 || (row&3) || size<row*16)goto done;
 if(IOSurfaceLock(surface,0,NULL)!=KERN_SUCCESS)goto done;
 locked=true;uint8_t *base=IOSurfaceGetBaseAddress(surface);if(!base)goto done;
 memset(base,0xa5,row*16);
 glPixelStorei(GL_PACK_ALIGNMENT,4);
 for(unsigned y=0;y<16;y++)glReadPixels(0,15-y,16,1,GL_BGRA,GL_UNSIGNED_BYTE,base+y*row);
 GLenum error=glGetError();unsigned wrong=0,padding=0;
 for(unsigned y=0;y<16;y++){
  uint32_t *words=(uint32_t *)(base+y*row);
  for(unsigned x=0;x<16;x++){
   uint32_t p=pixels[(15-y)*16+x];
   uint32_t bgra=(p&0xff00ff00u)|((p&0xffu)<<16)|((p>>16)&0xffu);
   wrong+=words[x]!=bgra;
  }
  for(size_t x=64;x<row;x++)padding+=base[y*row+x]!=0xa5;
 }
 printf("waffle-gl-present: checked=256 wrong=%u padding_wrong=%u GL_error=%x top_down=1\n",wrong,padding,error);
 if(wrong || padding || error)goto done;
 if(IOSurfaceUnlock(surface,0,NULL)!=KERN_SUCCESS)goto done;
 locked=false;
 io_service_t service=IOServiceGetMatchingService(0,IOServiceMatching("IOMobileFramebuffer"));
 if(!service){printf("waffle-gl-present: display service missing\n");goto done;}
 kern_return_t kr=IOServiceOpen(service,mach_task_self(),0,&display);IOObjectRelease(service);
 if(kr){printf("waffle-gl-present: display open error=%x\n",kr);goto done;}
 uint64_t dimensions[2]={0},swapid=0;uint32_t count=2;
 kr=IOConnectCallScalarMethod(display,8,NULL,0,dimensions,&count);
 if(kr || count!=2 || dimensions[0]<256 || dimensions[1]<256 || dimensions[0]>4096 || dimensions[1]>8192)goto done;
 count=1;kr=IOConnectCallScalarMethod(display,4,NULL,0,&swapid,&count);
 if(kr || count!=1 || !swapid || swapid>UINT32_MAX)goto done;
 /* MiniIOMobileFramebuffer.cpp's existing swap packet, not an inferred ABI. */
 uint32_t swap[0x46c/4]={0};
 swap[0x50/4]=(uint32_t)swapid;swap[0x54/4]=sid;
 swap[0x64/4+2]=16;swap[0x64/4+3]=16;swap[0xa4/4]=1;
 swap[0xc4/4]=(uint32_t)(dimensions[0]-256)/2;swap[0xc4/4+1]=(uint32_t)(dimensions[1]-256)/2;
 swap[0xc4/4+2]=256;swap[0xc4/4+3]=256;swap[0x104/4]=1;
 printf("waffle-gl-present: swap=%u surface=%u display=%llux%llu destination=%u,%u,256,256\n",(unsigned)swapid,sid,(unsigned long long)dimensions[0],(unsigned long long)dimensions[1],swap[0xc4/4],swap[0xc4/4+1]);
 kr=IOConnectCallStructMethod(display,5,swap,sizeof(swap),NULL,NULL);
 printf("waffle-gl-present: swap_accepted=%u error=%x hold_seconds=5\n",kr==KERN_SUCCESS,kr);
 if(kr)goto done;
 sleep(5);ok=true;
done:
 if(display)IOServiceClose(display);
 if(locked)IOSurfaceUnlock(surface,0,NULL);
 if(surface)CFRelease(surface);
 printf("waffle-gl-present: result=%u CPU_readback=1\n",ok);
 return ok;
}
#endif
static GLuint compile(GLenum type,const char *text)
{
 GLuint s=glCreateShader(type);glShaderSource(s,1,&text,NULL);glCompileShader(s);GLint ok=0;glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
 if(!ok){char log[2048];glGetShaderInfoLog(s,sizeof(log),NULL,log);printf("waffle-gl-user: shader failed %s\n",log);return 0;}return s;
}
int main(void)
{
 diagnostic_console=(int)raw_call(5,(long)"/dev/console",2,0);
 struct sigaction action;memset(&action,0,sizeof(action));action.sa_sigaction=crash_log;action.sa_flags=SA_SIGINFO;
 sigemptyset(&action.sa_mask);int se=sigaction(SIGSEGV,&action,NULL),bu=sigaction(SIGBUS,&action,NULL);
 direct_log("waffle-gl-diag: signal_handlers segv=%d bus=%d console=%d\n",se,bu,diagnostic_console);
 for(uint32_t i=0;i<_dyld_image_count();i++)direct_log("waffle-gl-image: base=%p slide=%llx name=%s\n",_dyld_get_image_header(i),(unsigned long long)_dyld_get_image_vmaddr_slide(i),_dyld_get_image_name(i));
 printf("waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16\n");
 setenv("WAFFLE_GPU_DRM","1",1);setenv("OSMESA_SOFTWARE","0",1);
 int ok=0;OSMesaContext ctx=NULL;
 const int attrs[]={OSMESA_FORMAT,OSMESA_RGBA,OSMESA_PROFILE,OSMESA_CORE_PROFILE,OSMESA_CONTEXT_MAJOR_VERSION,3,OSMESA_CONTEXT_MINOR_VERSION,3,0};
 direct_log("waffle-gl-diag: before_create_context\n");
 ctx=OSMesaCreateContextAttribs(attrs,NULL);
 direct_log("waffle-gl-diag: after_create_context ptr=%p\n",ctx);
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
 ok=!wrong && !error && inside==128;
#ifdef WAFFLE_GL_PRESENT
 if(ok)ok=present_triangle();
#endif
 printf("waffle-gl-user: checked=256 wrong=%u filled=%u GL_error=%x\n",wrong,inside,error);
 for(unsigned i=0;i<256;i+=8)printf("waffle-gl-user: pixels offset=%u values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x\n",i,pixels[i],pixels[i+1],pixels[i+2],pixels[i+3],pixels[i+4],pixels[i+5],pixels[i+6],pixels[i+7]);
 glDeleteVertexArrays(1,&vao);glDeleteProgram(program);glDeleteShader(vs);glDeleteShader(fs);
finish:
 if(ctx)OSMesaDestroyContext(ctx);
 /* dyld may close inherited0/1/2: device FDs can reuse those numbers.
  * Close every FD except the independently opened diagnostic console. */
 for(int fd=0;fd<256;fd++)if(fd!=diagnostic_console)close(fd);
 printf("waffle-gl-user: result=%d actual_OSMesa=1\n",ok);
 reboot(RB_HALT);for(;;){}
}
