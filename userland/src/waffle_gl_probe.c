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
#ifdef WAFFLE_GL_EAGL
#include "macan_gl.h"
#endif
#ifdef WAFFLE_GL_HOOK
#include <dlfcn.h>
#include <objc/message.h>
#include <objc/runtime.h>
#endif
#ifdef WAFFLE_GL_PRESENT
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurfaceRef.h>
#include <IOKit/IOKitLib.h>
#endif
extern int reboot(int);
#define RB_HALT 8
#ifdef WAFFLE_GL_FULLSIZE
#define WAFFLE_TARGET_WIDTH 750u
#define WAFFLE_TARGET_HEIGHT 1624u
#else
#define WAFFLE_TARGET_WIDTH 16u
#define WAFFLE_TARGET_HEIGHT 16u
#endif
#ifdef WAFFLE_GL_READBACK_BENCH
#include <mach/mach_time.h>
#define WAFFLE_PROBE_INVERTED 0
#else
#define WAFFLE_PROBE_INVERTED 1
#endif
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
#if defined(WAFFLE_GL_RECYCLE_BO) || defined(WAFFLE_GL_SURFACE_MAP_TEST)
#include <sys/stat.h>
#include <sys/ioctl.h>
#include "waffle_gpu_msm.h"
#endif
#ifdef WAFFLE_GL_RECYCLE_BO
#include "waffle_gl_recycle_probe.h"
#endif
#if defined(WAFFLE_GL_RECYCLE_BO) || defined(WAFFLE_GL_SURFACE_MAP_TEST)
static int existing_gpu_fd(void)
{
 struct stat device;
 if(stat("/dev/waffle-gpu-drm",&device) || !S_ISCHR(device.st_mode))return -1;
 for(int fd=0;fd<256;fd++){
  struct stat candidate;
  if(!fstat(fd,&candidate) && S_ISCHR(candidate.st_mode) && candidate.st_rdev==device.st_rdev)return dup(fd);
 }
 return -1;
}
#endif
#ifdef WAFFLE_GL_HOOK
#include "waffle_eagl_dispatch.h"
static IOSurfaceRef hook_surface;
#ifdef WAFFLE_GL_CONTEXTS
static bool check_context_switch(void)
{
 bool ok=false;void **first=waffle_hook_table;id second=nil;
 printf("waffle-gl-contexts: begin actual_EAGLContext=2 same_PID=1\n");
 Class cls=objc_getClass("EAGLContext");
 second=((id (*)(id,SEL))objc_msgSend)((id)cls,sel_registerName("alloc"));
 second=((id (*)(id,SEL,unsigned long,id))objc_msgSend)(second,sel_registerName("initWithAPI:properties:"),2,nil);
 if(!second){printf("waffle-gl-contexts: second initializer failed\n");goto done;}
 void **table=((void **(*)(id,SEL))objc_msgSend)(second,sel_registerName("getMacroContextPrivate"));
 if(!table || !table[0] || table==first || table[0]==first[0]){printf("waffle-gl-contexts: distinct table missing\n");goto done;}
 waffle_hook_table=table;
 glViewport(0,0,16,16);glDisable(GL_DITHER);glClearColor(0,0,1,1);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 uint32_t second_pixels[256];for(unsigned i=0;i<256;i++)second_pixels[i]=0xdeadbeef;
 glReadPixels(0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,second_pixels);
 GLenum error=glGetError();unsigned wrong=0;
 for(unsigned i=0;i<256;i++)wrong+=second_pixels[i]!=0xffff0000u;
 printf("waffle-gl-contexts: second checked=256 wrong=%u GL_error=%x color=%08x distinct_context=1\n",wrong,error,second_pixels[0]);
 if(wrong || error)goto done;
 waffle_hook_table=first;for(unsigned i=0;i<256;i++)second_pixels[i]=0xdeadbeef;
 glReadPixels(0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,second_pixels);
 error=glGetError();wrong=0;
 for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
  bool filled=(4*x+2>2*y+1) && (4*x+2<63-2*y);
  wrong+=second_pixels[y*16+x]!=(filled?0xff0040ffu:0xff000000u);
 }
 printf("waffle-gl-contexts: first_restored checked=256 wrong=%u GL_error=%x\n",wrong,error);
 ok=!wrong && !error;
done:
 if(second)((void (*)(id,SEL))objc_msgSend)(second,sel_registerName("release"));
 waffle_hook_table=first;
 printf("waffle-gl-contexts: result=%u second_released=1\n",ok);
 return ok;
}
#endif
#endif
static uint32_t pixels[256];
#ifdef WAFFLE_GL_READBACK_BENCH
static bool benchmark_blue;
#endif
#ifdef WAFFLE_GL_FULLSIZE
#ifdef WAFFLE_GL_SURFACE_IMPORT_TEST
static bool check_surface_import(void)
{
 int fd=existing_gpu_fd();if(fd<0)return false;
 uint32_t sid=IOSurfaceGetID(hook_surface),first=0,second=0;bool ok=false;
 struct waffle_msm_surface r={.surface=sid};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_IMPORT_TEST,&r) || !r.handle || r.size!=IOSurfaceGetAllocSize(hook_surface))goto done;
 first=r.handle;
 r=(struct waffle_msm_surface){.surface=sid};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_IMPORT_TEST,&r) || r.handle!=first)goto done;
 struct waffle_msm_gem_info info={.handle=first,.info=1};
 if(ioctl(fd,WAFFLE_MSM_INFO,&info) || !info.value)goto done;
 struct waffle_msm_map map={.handle=first,.bytes=r.size};
 if(ioctl(fd,WAFFLE_MSM_MAP,&map)!=-1 || errno!=ENOTSUP)goto done;
 struct waffle_msm_close retired={.handle=first};
 if(ioctl(fd,WAFFLE_MSM_CLOSE,&retired))goto done;
 first=0;
 if(ioctl(fd,WAFFLE_MSM_INFO,&info)!=-1 || errno!=EINVAL)goto done;
 r=(struct waffle_msm_surface){.surface=sid};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_IMPORT_TEST,&r) || !r.handle || r.handle==info.handle)goto done;
 second=r.handle;
 if(ioctl(fd,WAFFLE_MSM_INFO,&info)!=-1 || errno!=EINVAL)goto done;
 retired.handle=second;if(ioctl(fd,WAFFLE_MSM_CLOSE,&retired))goto done;second=0;
 printf("waffle-gl-surface-import: passed=1 sid=%u first=%u second=%u duplicate_same=1 stale_refused=1 CPU_map_refused=1 closed=2 GPU_memory_access=0\n",sid,info.handle,r.handle);ok=true;
 done:
 if(first){struct waffle_msm_close r={.handle=first};ioctl(fd,WAFFLE_MSM_CLOSE,&r);}
 if(second){struct waffle_msm_close r={.handle=second};ioctl(fd,WAFFLE_MSM_CLOSE,&r);}
 if(!ok)printf("waffle-gl-surface-import: passed=0\n");close(fd);return ok;
}
#endif
#ifdef WAFFLE_GL_SURFACE_RESOURCE_TEST
static bool check_surface_resource(void)
{
 void (*image_target)(GLenum,void *)=(void (*)(GLenum,void *))OSMesaGetProcAddress("glEGLImageTargetTexture2DOES");
 if(!image_target)return false;
 GLuint textures[2]={0};GLint previous=0;unsigned checked=0;bool ok=false;
 glGetIntegerv(GL_TEXTURE_BINDING_2D,&previous);
 if(glGetError()!=GL_NO_ERROR || setenv("WAFFLE_GPU_SURFACE_IMPORT_AUDIT","1",1))return false;
 glGenTextures(2,textures);
 for(unsigned i=0;i<2;i++){
  glBindTexture(GL_TEXTURE_2D,textures[i]);
  image_target(GL_TEXTURE_2D,(void *)(uintptr_t)IOSurfaceGetID(hook_surface));
  GLint width=0,height=0;
  glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&width);
  glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&height);
  if(glGetError()!=GL_NO_ERROR || width!=750 || height!=1624)goto done;
  checked++;
 }
 ok=true;
 done:
 unsetenv("WAFFLE_GPU_SURFACE_IMPORT_AUDIT");
 glBindTexture(GL_TEXTURE_2D,(GLuint)previous);glDeleteTextures(2,textures);
 if(glGetError()!=GL_NO_ERROR)ok=false;
 printf("waffle-gl-surface-resource: passed=%u sid=%u textures=%u width=750 height=1624 deleted=2 GPU_memory_access=0\n",ok,IOSurfaceGetID(hook_surface),checked);
 return ok;
}
#endif
static bool check_full_surface(void)
{
 if(!hook_surface || IOSurfaceGetWidth(hook_surface)!=750 || IOSurfaceGetHeight(hook_surface)!=1624 || IOSurfaceGetBytesPerRow(hook_surface)<3000)return false;
#ifdef WAFFLE_GL_SURFACE_RESOURCE_TEST
 if(!check_surface_resource())return false;
#endif
#ifdef WAFFLE_GL_SURFACE_IMPORT_TEST
 if(!check_surface_import())return false;
#endif
#if defined(WAFFLE_GL_SURFACE_MAP_TEST) && !defined(WAFFLE_GL_SURFACE_IMPORT_TEST) && !defined(WAFFLE_GL_SURFACE_RESOURCE_TEST)
 int fd=existing_gpu_fd();
 if(fd<0){printf("waffle-gl-surface-map: passed=0 stage=fd\n");return false;}
 struct waffle_msm_surface request={.surface=IOSurfaceGetID(hook_surface)};
#if defined(WAFFLE_GL_SURFACE_WRITE_TEST) || defined(WAFFLE_GL_SURFACE_READ_TEST)
 if(IOSurfaceLock(hook_surface,0,NULL)!=KERN_SUCCESS){close(fd);return false;}
#ifdef WAFFLE_GL_SURFACE_READ_TEST
 int mapped=ioctl(fd,WAFFLE_MSM_SURFACE_READ_TEST,&request);close(fd);
#else
 int mapped=ioctl(fd,WAFFLE_MSM_SURFACE_WRITE_TEST,&request);close(fd);
#endif
#else
 int mapped=ioctl(fd,WAFFLE_MSM_SURFACE_MAP_TEST,&request);close(fd);
#endif
 if(mapped || request.handle || request.surface!=IOSurfaceGetID(hook_surface) || request.size!=IOSurfaceGetAllocSize(hook_surface)){
#if defined(WAFFLE_GL_SURFACE_WRITE_TEST) || defined(WAFFLE_GL_SURFACE_READ_TEST)
  IOSurfaceUnlock(hook_surface,0,NULL);
#endif
  printf("waffle-gl-surface-map: passed=0 stage=map_revoke error=%d\n",mapped);return false;
 }
#if defined(WAFFLE_GL_SURFACE_WRITE_TEST) || defined(WAFFLE_GL_SURFACE_READ_TEST)
#ifdef WAFFLE_GL_SURFACE_READ_TEST
 printf("waffle-gl-surface-read: passed=1 GPU_memory_access=1 restored=1\n");
#else
 printf("waffle-gl-surface-write: passed=1 GPU_memory_access=1 restored=1\n");
#endif
#else
 printf("waffle-gl-surface-map: passed=1 native_registry=1 mapped_then_revoked=1 GPU_memory_access=0\n");
#endif
#endif
#if !defined(WAFFLE_GL_SURFACE_WRITE_TEST) && !defined(WAFFLE_GL_SURFACE_READ_TEST)
 if(IOSurfaceLock(hook_surface,0,NULL)!=KERN_SUCCESS)return false;
#endif
 const uint8_t *base=IOSurfaceGetBaseAddress(hook_surface);size_t stride=IOSurfaceGetBytesPerRow(hook_surface);
 if(!base || stride>16384 || IOSurfaceGetAllocSize(hook_surface)<stride*1624){IOSurfaceUnlock(hook_surface,0,NULL);return false;}
 unsigned wrong=0,filled=0,padding=0;
 for(unsigned y=0;y<1624;y++){
  const uint32_t *row=(const uint32_t *)(base+y*stride);unsigned gy=WAFFLE_PROBE_INVERTED?1623-y:y;
  for(unsigned x=0;x<750;x++){
   bool inside=(2*x+1)*3248>750*(2*gy+1) && (2*x+1)*3248<4872000-750*(2*gy+1);
   uint32_t outside=0xff000000u;
#ifdef WAFFLE_GL_READBACK_BENCH
   if(benchmark_blue)outside=0xff0000ffu;
#endif
   filled+=inside;wrong+=row[x]!=(inside?0xffff4000u:outside);
  }
  for(size_t x=3000;x<stride;x++)padding+=base[y*stride+x]!=0;
 }
 /* Keep the existing independent16x16 diagnostic proof using actual samples
  * of the full GPU result, with RGBA and GL bottom-up orientation. */
 for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
  unsigned sx=(x*750+375)/16,sy=((WAFFLE_PROBE_INVERTED?15-y:y)*1624+812)/16;
  uint32_t p=*(const uint32_t *)(base+sy*stride+sx*4);
  pixels[y*16+x]=(p&0xff00ff00u)|((p&0xffu)<<16)|((p>>16)&0xffu);
 }
 kern_return_t unlock=IOSurfaceUnlock(hook_surface,0,NULL);GLenum error=glGetError();
#ifdef WAFFLE_GL_SURFACE_DESCRIBE
 printf("waffle-gl-surface: sid=%u bytes=%zu stride=%zu width=%zu height=%zu format=%x metadata_expected=1\n",
     IOSurfaceGetID(hook_surface),IOSurfaceGetAllocSize(hook_surface),IOSurfaceGetBytesPerRow(hook_surface),
     IOSurfaceGetWidth(hook_surface),IOSurfaceGetHeight(hook_surface),(unsigned)IOSurfaceGetPixelFormat(hook_surface));
#endif
 printf("waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=%u filled=%u padding_wrong=%u GL_error=%x hook_owned=1\n",wrong,filled,padding,error);
 return !wrong && !padding && !error && !unlock && filled==609000;
}
#endif
#ifdef WAFFLE_GL_READBACK_BENCH
static uint64_t benchmark_now_us(void)
{
 static mach_timebase_info_data_t timebase;
 if(!timebase.denom)mach_timebase_info(&timebase);
 return mach_absolute_time()*timebase.numer/timebase.denom/1000;
}
static bool benchmark_readback(void)
{
 printf("waffle-gl-bench: begin frames=240 width=750 height=1624 inverted=0 CPU_reference_outside_timing=1 panel_FPS=0\n");
 for(unsigned frame=0;frame<240;frame++){
  benchmark_blue=!(frame&1);
  uint64_t before=benchmark_now_us();
  glClearColor(0,0,benchmark_blue?1:0,1);glClear(GL_COLOR_BUFFER_BIT);
  glDrawArrays(GL_TRIANGLES,0,3);glFinish();
  uint64_t elapsed=benchmark_now_us()-before;
  if(!check_full_surface())return false;
  printf("waffle-gl-bench: frame=%u render_and_readback_us=%llu checked=1218000 wrong=0 blue=%u\n",frame,(unsigned long long)elapsed,benchmark_blue);
 }
 printf("waffle-gl-bench: result=1 frames=240 checked=292320000 wrong=0 inverted=0 panel_FPS=0\n");
 return true;
}
#endif
#ifdef WAFFLE_GL_FRAMES
static bool repeat_triangles(void)
{
 unsigned total_wrong=0;
 for(unsigned frame=0;frame<64;frame++){
  bool blue=!(frame&1);
  glClearColor(0,0,blue?1:0,1);glClear(GL_COLOR_BUFFER_BIT);
  glDrawArrays(GL_TRIANGLES,0,3);glFinish();
  glReadPixels(0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
  GLenum error=glGetError();unsigned wrong=0;
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
   bool filled=(4*x+2>2*y+1) && (4*x+2<63-2*y);
   uint32_t expected=filled?0xff0040ffu:blue?0xffff0000u:0xff000000u;
   wrong+=pixels[y*16+x]!=expected;
  }
  total_wrong+=wrong;
  printf("waffle-gl-frames: frame=%u checked=256 wrong=%u GL_error=%x outside=%08x inside=%08x\n",frame,wrong,error,pixels[240],pixels[120]);
  if(wrong || error)return false;
 }
 printf("waffle-gl-frames: frames=64 checked=16384 wrong=%u result=1\n",total_wrong);
 return true;
}
#endif
#ifdef WAFFLE_GL_PRESENT
/* Same readback bridge used by eagl.c, through the existing display client.
 * This tests presentation with CPU readback, not direct GPU surface import. */
static IOSurfaceRef make_triangle_surface(void)
{
 CFMutableDictionaryRef props=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
 if(!props)return NULL;
 const CFStringRef keys[]={kIOSurfaceWidth,kIOSurfaceHeight,kIOSurfacePixelFormat,kIOSurfaceBytesPerElement};
 const int values[]={WAFFLE_TARGET_WIDTH,WAFFLE_TARGET_HEIGHT,0x42475241,4};
 for(unsigned i=0;i<4;i++){
  CFNumberRef n=CFNumberCreate(NULL,kCFNumberIntType,&values[i]);
  if(!n){CFRelease(props);return NULL;}CFDictionarySetValue(props,keys[i],n);CFRelease(n);
 }
 IOSurfaceRef surface=IOSurfaceCreate(props);CFRelease(props);return surface;
}
static bool present_triangle(void)
{
 bool ok=false,locked=false;IOSurfaceRef surface=NULL;io_connect_t display=0;
 printf("waffle-gl-present: begin CPU_readback=1 IOSurface_import=0\n");
#ifdef WAFFLE_GL_HOOK
 if(hook_surface)surface=(IOSurfaceRef)CFRetain(hook_surface);
 printf("waffle-gl-hook: IOSurface_readback_owner=EAGL_hook probe_writes=0\n");
#else
 surface=make_triangle_surface();
#endif
 if(!surface){printf("waffle-gl-present: IOSurfaceCreate failed\n");goto done;}
 size_t row=IOSurfaceGetBytesPerRow(surface),size=IOSurfaceGetAllocSize(surface);
 uint32_t sid=IOSurfaceGetID(surface);
 printf("waffle-gl-present: surface=%u width=%zu height=%zu stride=%zu bytes=%zu\n",sid,IOSurfaceGetWidth(surface),IOSurfaceGetHeight(surface),row,size);
 if(!sid || IOSurfaceGetWidth(surface)!=WAFFLE_TARGET_WIDTH || IOSurfaceGetHeight(surface)!=WAFFLE_TARGET_HEIGHT ||
    IOSurfaceGetPixelFormat(surface)!=0x42475241 || IOSurfaceGetPlaneCount(surface) ||
    row<WAFFLE_TARGET_WIDTH*4 || row>16384 || (row&3) || size<row*WAFFLE_TARGET_HEIGHT)goto done;
 if(IOSurfaceLock(surface,0,NULL)!=KERN_SUCCESS)goto done;
 locked=true;uint8_t *base=IOSurfaceGetBaseAddress(surface);if(!base)goto done;
#ifndef WAFFLE_GL_HOOK
 memset(base,0xa5,row*16);
 glPixelStorei(GL_PACK_ALIGNMENT,4);
 for(unsigned y=0;y<16;y++)glReadPixels(0,15-y,16,1,GL_BGRA,GL_UNSIGNED_BYTE,base+y*row);
#endif
 GLenum error=glGetError();unsigned wrong=0,padding=0;
 for(unsigned y=0;y<16;y++){
  unsigned sy=(y*WAFFLE_TARGET_HEIGHT+WAFFLE_TARGET_HEIGHT/2)/16;
  uint32_t *words=(uint32_t *)(base+sy*row);
  for(unsigned x=0;x<16;x++){
   uint32_t p=pixels[(15-y)*16+x];
   uint32_t bgra=(p&0xff00ff00u)|((p&0xffu)<<16)|((p>>16)&0xffu);
   unsigned sx=(x*WAFFLE_TARGET_WIDTH+WAFFLE_TARGET_WIDTH/2)/16;
   wrong+=words[sx]!=bgra;
  }
  for(size_t x=WAFFLE_TARGET_WIDTH*4;x<row;x++)padding+=base[sy*row+x]!=
#ifdef WAFFLE_GL_HOOK
   0;
#else
   0xa5;
#endif
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
 unsigned dw=256,dh=256;
#ifdef WAFFLE_GL_FULLSIZE
 dw=750;dh=1624;
#endif
 if(kr || count!=2 || dimensions[0]<dw || dimensions[1]<dh || dimensions[0]>4096 || dimensions[1]>8192)goto done;
 count=1;kr=IOConnectCallScalarMethod(display,4,NULL,0,&swapid,&count);
 if(kr || count!=1 || !swapid || swapid>UINT32_MAX)goto done;
 /* MiniIOMobileFramebuffer.cpp's existing swap packet, not an inferred ABI. */
 uint32_t swap[0x46c/4]={0};
 swap[0x50/4]=(uint32_t)swapid;swap[0x54/4]=sid;
 swap[0x64/4+2]=WAFFLE_TARGET_WIDTH;swap[0x64/4+3]=WAFFLE_TARGET_HEIGHT;swap[0xa4/4]=1;
 swap[0xc4/4]=(uint32_t)(dimensions[0]-dw)/2;swap[0xc4/4+1]=(uint32_t)(dimensions[1]-dh)/2;
 swap[0xc4/4+2]=dw;swap[0xc4/4+3]=dh;swap[0x104/4]=1;
 printf("waffle-gl-present: swap=%u surface=%u display=%llux%llu destination=%u,%u,%u,%u\n",(unsigned)swapid,sid,(unsigned long long)dimensions[0],(unsigned long long)dimensions[1],swap[0xc4/4],swap[0xc4/4+1],dw,dh);
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
#ifdef WAFFLE_GL_SURFACE_DESCRIBE
 setenv("WAFFLE_GPU_SURFACE_AUDIT","1",1);
 printf("waffle-gl-surface: audit=1 metadata_only=1 import_unsupported=1\n");
#endif
 diagnostic_console=(int)raw_call(5,(long)"/dev/console",2,0);
#ifdef WAFFLE_GL_HOOK
 if(diagnostic_console>=0)dup2(diagnostic_console,2);
#endif
 struct sigaction action;memset(&action,0,sizeof(action));action.sa_sigaction=crash_log;action.sa_flags=SA_SIGINFO;
 sigemptyset(&action.sa_mask);int se=sigaction(SIGSEGV,&action,NULL),bu=sigaction(SIGBUS,&action,NULL);
 direct_log("waffle-gl-diag: signal_handlers segv=%d bus=%d console=%d\n",se,bu,diagnostic_console);
 for(uint32_t i=0;i<_dyld_image_count();i++)direct_log("waffle-gl-image: base=%p slide=%llx name=%s\n",_dyld_get_image_header(i),(unsigned long long)_dyld_get_image_vmaddr_slide(i),_dyld_get_image_name(i));
 printf("waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16\n");
 setenv("WAFFLE_GPU_DRM","1",1);setenv("OSMESA_SOFTWARE","0",1);
 int ok=0;
#ifdef WAFFLE_GL_EAGL
#ifdef WAFFLE_GL_HOOK
 id ctx=nil;
 printf("waffle-gl-eagl: begin actual_adapter=gl_osmesa API=2 texture_FBO=1\n");
 printf("waffle-gl-hook: begin actual_library=libredwood-gl private_table=1 public_GL_TLS=0\n");
 void *framework=dlopen("/System/Library/Frameworks/OpenGLES.framework/OpenGLES",RTLD_NOW|RTLD_LOCAL);
 if(!framework){printf("waffle-gl-hook: framework failed %s\n",dlerror());goto finish;}
 void *hook=dlopen("/redwood/lib/libredwood-gl.dylib",RTLD_NOW|RTLD_LOCAL);
 if(!hook){printf("waffle-gl-hook: library failed %s\n",dlerror());goto finish;}
 Class cls=objc_getClass("EAGLContext");
 SEL init=sel_registerName("initWithAPI:properties:"),table=sel_registerName("getMacroContextPrivate");
 if(!cls || !class_getInstanceMethod(cls,init) || !class_getInstanceMethod(cls,table)){
  printf("waffle-gl-hook: EAGL class or existing methods missing\n");goto finish;
 }
 ctx=((id (*)(id,SEL))objc_msgSend)((id)cls,sel_registerName("alloc"));
 ctx=((id (*)(id,SEL,unsigned long,id))objc_msgSend)(ctx,init,2,nil);
 if(!ctx){printf("waffle-gl-hook: initializer failed\n");goto finish;}
 waffle_hook_table=((void **(*)(id,SEL))objc_msgSend)(ctx,table);
 if(!waffle_hook_table || !waffle_hook_table[0]){printf("waffle-gl-hook: private table missing\n");goto finish;}
 printf("waffle-gl-hook: actual_EAGLContext=1 table_nonnull=1 context_nonnull=1\n");
#else
 struct redwood_gl *ctx=NULL;
 printf("waffle-gl-eagl: begin actual_adapter=gl_osmesa API=2 texture_FBO=1\n");
 ctx=redwood_gl_create(2);
 if(!ctx || !redwood_gl_make_current(ctx)){printf("waffle-gl-eagl: context failed\n");goto finish;}
#endif
 for(unsigned i=0;i<256;i++)pixels[i]=0xdead0000u+i;
#else
 OSMesaContext ctx=NULL;
 const int attrs[]={OSMESA_FORMAT,OSMESA_RGBA,OSMESA_PROFILE,OSMESA_CORE_PROFILE,OSMESA_CONTEXT_MAJOR_VERSION,3,OSMESA_CONTEXT_MINOR_VERSION,3,0};
 direct_log("waffle-gl-diag: before_create_context\n");
 ctx=OSMesaCreateContextAttribs(attrs,NULL);
 direct_log("waffle-gl-diag: after_create_context ptr=%p\n",ctx);
 if(!ctx){printf("waffle-gl-user: context failed\n");goto finish;}
 for(unsigned i=0;i<256;i++)pixels[i]=0xdead0000u+i;
 if(!OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16)){printf("waffle-gl-user: makecurrent failed\n");goto finish;}
#endif
 const char *renderer=(const char *)glGetString(GL_RENDERER);
 printf("waffle-gl-user: renderer=%s version=%s\n",renderer?renderer:"NULL",glGetString(GL_VERSION));
 if(!renderer || !strstr(renderer,"FD750")){printf("waffle-gl-user: GPU renderer not selected\n");goto finish;}
#ifdef WAFFLE_GL_RECYCLE_BO
 int recycle_fd=existing_gpu_fd();
 if(recycle_fd<0){printf("waffle-gl-recycle: existing device FD missing\n");goto finish;}
#ifdef WAFFLE_GL_QUEUE_RECYCLE
 if(!waffle_gl_queue_probe_begin(recycle_fd)){printf("waffle-gl-queue: result=0 begin failed\n");close(recycle_fd);goto finish;}
#endif
 bool recycled=waffle_gl_recycle_buffers(recycle_fd,9000);
#ifdef WAFFLE_GL_QUEUE_RECYCLE
 if(recycled)recycled=waffle_gl_queue_probe_end(recycle_fd);
#endif
 close(recycle_fd);
 if(!recycled)goto finish;
#endif
#ifdef WAFFLE_GL_EAGL
 const char *version=(const char *)glGetString(GL_VERSION);
 if(!version || !strstr(version,"OpenGL ES")){printf("waffle-gl-eagl: ES profile missing\n");goto finish;}
#ifdef WAFFLE_GL_HOOK
 /* Actual hook adds GLSL300 and translates legacy syntax. An explicit
  * version here would duplicate its version directive (E43 first failure). */
#define WAFFLE_ES_SOURCE_VERSION ""
 printf("waffle-gl-hook: input_version_directive=0 shader_translation=actual_hook\n");
#else
#define WAFFLE_ES_SOURCE_VERSION "#version 100\n"
#endif
 GLuint vs=compile(GL_VERTEX_SHADER,WAFFLE_ES_SOURCE_VERSION "attribute vec2 position;void main(){gl_Position=vec4(position,0,1);}");
 GLuint fs=compile(GL_FRAGMENT_SHADER,WAFFLE_ES_SOURCE_VERSION "precision mediump float;void main(){gl_FragColor=vec4(1,0.25,0,1);}");
#else
 GLuint vs=compile(GL_VERTEX_SHADER,"#version 330 core\nconst vec2 p[3]=vec2[3](vec2(-1,-1),vec2(1,-1),vec2(0,1));void main(){gl_Position=vec4(p[gl_VertexID],0,1);}");
 GLuint fs=compile(GL_FRAGMENT_SHADER,"#version 330 core\nout vec4 color;void main(){color=vec4(1,0.25,0,1);}");
#endif
 if(!vs || !fs)goto finish;
 GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);
 if(!linked){printf("waffle-gl-user: link failed\n");goto finish;}
#ifdef WAFFLE_GL_EAGL
 GLuint buffer,texture,framebuffer;const GLfloat vertices[]={-1,-1,1,-1,0,1};
 glGenBuffers(1,&buffer);glBindBuffer(GL_ARRAY_BUFFER,buffer);glBufferData(GL_ARRAY_BUFFER,sizeof(vertices),vertices,GL_STATIC_DRAW);
 GLint attribute=glGetAttribLocation(program,"position");if(attribute<0)goto finish;
 glVertexAttribPointer((GLuint)attribute,2,GL_FLOAT,GL_FALSE,0,NULL);glEnableVertexAttribArray((GLuint)attribute);
 glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,WAFFLE_TARGET_WIDTH,WAFFLE_TARGET_HEIGHT,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
#ifdef WAFFLE_GL_HOOK
 hook_surface=make_triangle_surface();if(!hook_surface)goto finish;
 SEL attach=sel_registerName("attachImage:toCoreSurface:invertedRender:");
 if(!class_getInstanceMethod(cls,attach))goto finish;
 BOOL attached=((BOOL (*)(id,SEL,unsigned long,IOSurfaceRef,BOOL))objc_msgSend)(ctx,attach,GL_TEXTURE_2D,hook_surface,WAFFLE_PROBE_INVERTED?YES:NO);
 printf("waffle-gl-hook: attachImage=%u surface=%u inverted=%u\n",attached,IOSurfaceGetID(hook_surface),WAFFLE_PROBE_INVERTED);
 if(!attached)goto finish;
#endif
 glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 GLenum status=glCheckFramebufferStatus(GL_FRAMEBUFFER);
 printf("waffle-gl-eagl: FBO_status=%x\n",status);if(status!=GL_FRAMEBUFFER_COMPLETE)goto finish;
#else
 GLuint vao;glGenVertexArrays(1,&vao);glBindVertexArray(vao);
#endif
 glDisable(GL_DITHER);glViewport(0,0,WAFFLE_TARGET_WIDTH,WAFFLE_TARGET_HEIGHT);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glUseProgram(program);glDrawArrays(GL_TRIANGLES,0,3);glFinish();
#ifdef WAFFLE_GL_EAGL
#ifdef WAFFLE_GL_FULLSIZE
 if(!check_full_surface())goto finish;
#else
 glReadPixels(0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
#endif
#endif
#ifdef WAFFLE_GL_READBACK_BENCH
 if(!benchmark_readback())goto finish;
#endif
#ifdef WAFFLE_GL_FRAMES
 if(!repeat_triangles())goto finish;
#endif
 GLenum error=glGetError();unsigned wrong=0,inside=0;
 for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
  bool filled=(4*x+2>2*y+1) && (4*x+2<63-2*y);
  uint32_t expected=filled?0xff0040ffu:0xff000000u;
  if(filled)inside++;if(pixels[y*16+x]!=expected)wrong++;
 }
 ok=!wrong && !error && inside==128;
#ifdef WAFFLE_GL_CONTEXTS
 if(ok)ok=check_context_switch();
#endif
#if defined(WAFFLE_GL_PRESENT) && !defined(WAFFLE_GL_READBACK_BENCH)
 if(ok)ok=present_triangle();
#endif
 printf("waffle-gl-user: checked=256 wrong=%u filled=%u GL_error=%x\n",wrong,inside,error);
 for(unsigned i=0;i<256;i+=8)printf("waffle-gl-user: pixels offset=%u values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x\n",i,pixels[i],pixels[i+1],pixels[i+2],pixels[i+3],pixels[i+4],pixels[i+5],pixels[i+6],pixels[i+7]);
#ifdef WAFFLE_GL_EAGL
 glDeleteFramebuffers(1,&framebuffer);glDeleteTextures(1,&texture);glDeleteBuffers(1,&buffer);
 printf("waffle-gl-eagl: result=%d actual_adapter=gl_osmesa API=2\n",ok);
#else
 glDeleteVertexArrays(1,&vao);
#endif
 glDeleteProgram(program);glDeleteShader(vs);glDeleteShader(fs);
finish:
#ifdef WAFFLE_GL_EAGL
#ifdef WAFFLE_GL_HOOK
 if(ctx)((void (*)(id,SEL))objc_msgSend)(ctx,sel_registerName("release"));
 if(hook_surface)CFRelease(hook_surface);
#else
 if(ctx)redwood_gl_destroy(ctx);
#endif
#else
 if(ctx)OSMesaDestroyContext(ctx);
#endif
 /* dyld may close inherited0/1/2: device FDs can reuse those numbers.
  * Close every FD except the independently opened diagnostic console. */
 for(int fd=0;fd<256;fd++)if(fd!=diagnostic_console)close(fd);
 printf("waffle-gl-user: result=%d actual_OSMesa=1\n",ok);
 reboot(RB_HALT);for(;;){}
}
