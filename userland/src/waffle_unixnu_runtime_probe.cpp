/* Controlled whole-runtime blit: actual metal2vulkan C bridge -> Turnip ->
 * NativeAdreno IOKit -> A750. Does not publish a system MTLDevice. */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
extern "C" int reboot(int);
#define RB_HALT 0x8
#include "NativeMetalObjects.h"
static int finish(bool ok){
 std::printf("waffle-unixnu-runtime: result=%u runtime_API=1 Metal_frontend=0\n",ok);
 std::fflush(stdout);reboot(RB_HALT);for(;;)pause();
}
#define LOAD(name) auto p_##name=reinterpret_cast<decltype(&name)>(dlsym(library,#name)); if(!p_##name){std::printf("waffle-unixnu-runtime: missing_export=%s\n",#name);return finish(false);}
int main(){
 int console=open("/dev/console",O_RDWR);if(console>=0){dup2(console,0);dup2(console,1);dup2(console,2);}setbuf(stdout,nullptr);
 std::printf("waffle-unixnu-runtime: begin PID=%d CPU_fallback=0\n",getpid());
 setenv("TU_DARWIN_SERVICE","NativeAdrenoGpuPublished",1);setenv("TU_DARWIN_OPEN_TYPE","0",1);
 setenv("TU_DEBUG","sysmem",1);
 setenv("METAL2VULKAN_SHADER_CACHE_OPTIONAL","1",1);
 const char *bundle="/redwood/lib/NativeAdrenoMetal.bundle/NativeAdrenoMetal";
 void *library=dlopen(bundle,RTLD_NOW|RTLD_LOCAL);
 if(!library){std::printf("waffle-unixnu-runtime: dlopen_failed=%s\n",dlerror());return finish(false);}
 /* Read-only frontend ABI inventory; never construct or publish a device here. */
 auto getClass=reinterpret_cast<void *(*)(const char *)>(dlsym(RTLD_DEFAULT,"objc_getClass"));
 auto instanceSize=reinterpret_cast<size_t (*)(void *)>(dlsym(RTLD_DEFAULT,"class_getInstanceSize"));
 auto getProtocol=reinterpret_cast<void *(*)(const char *)>(dlsym(RTLD_DEFAULT,"objc_getProtocol"));
 void *base=getClass?getClass("_MTLDevice"):nullptr;
 std::printf("waffle-unixnu-runtime: frontend_inventory base=%u bytes=%zu SPI=%u published=0\n",
             base!=nullptr,base&&instanceSize?instanceSize(base):0,
             getProtocol&&getProtocol("MTLDeviceSPI")!=nullptr);
 LOAD(nmb_device_open);LOAD(nmb_device_release);LOAD(nmb_last_error);LOAD(nmb_device_name);
 LOAD(nmb_queue_new);LOAD(nmb_queue_release);LOAD(nmb_buffer_new);LOAD(nmb_buffer_contents);LOAD(nmb_buffer_release);
 LOAD(nmb_command_buffer_new);LOAD(nmb_command_buffer_release);LOAD(nmb_command_buffer_commit);
 LOAD(nmb_command_buffer_wait);LOAD(nmb_command_buffer_status);LOAD(nmb_command_buffer_error);
 LOAD(nmb_blit_encoder_new);LOAD(nmb_blit_fill_buffer);LOAD(nmb_encoder_end);LOAD(nmb_encoder_discard);
 NmbDevice *device=nullptr;NmbQueue *queue=nullptr;NmbBuffer *buffer=nullptr;
 NmbCommandBuffer *command=nullptr;NmbEncoder *encoder=nullptr;
 bool ok=false,uncertain=false;const char *stage="device";
 do {
  device=p_nmb_device_open("/redwood/lib/NativeAdrenoMetal.bundle/libvulkan_freedreno.dylib","/tmp/waffle-native-cache");
  if(!device)break;
  char name[128]={};p_nmb_device_name(device,name,sizeof(name));std::printf("waffle-unixnu-runtime: device=%s\n",name);
  stage="queue";queue=p_nmb_queue_new(device);if(!queue)break;
  stage="buffer";buffer=p_nmb_buffer_new(device,4096,0,nullptr);if(!buffer)break;
  auto *bytes=static_cast<unsigned char *>(p_nmb_buffer_contents(buffer));if(!bytes)break;
  std::memset(bytes,0x3c,4096);
  stage="command";command=p_nmb_command_buffer_new(queue);if(!command)break;
  stage="blit";encoder=p_nmb_blit_encoder_new(command);if(!encoder)break;
  if(!p_nmb_blit_fill_buffer(encoder,buffer,16,4080,0xa5))break;
  bool ended=p_nmb_encoder_end(encoder);encoder=nullptr;if(!ended)break;
  stage="commit";if(!p_nmb_command_buffer_commit(command))break;
  uncertain=true;stage="wait";
  if(p_nmb_command_buffer_wait(command,15000)!=0 || p_nmb_command_buffer_status(command)!=4)break;
  uncertain=false;stage="verify";unsigned wrong=0;
  for(unsigned i=0;i<4096;i++)wrong+=bytes[i]!=(i>=16&&i<4080?0xa5:0x3c);
  std::printf("waffle-unixnu-runtime: checked=4096 filled=4064 guards=32 wrong=%u CPU_fallback=0\n",wrong);
  ok=!wrong;
 }while(false);
 if(!ok){char error[512]={};if(command)p_nmb_command_buffer_error(command,error,sizeof(error));std::printf("waffle-unixnu-runtime: failed_stage=%s reason=%s command=%s\n",stage,p_nmb_last_error(),error);}
 if(uncertain){std::printf("waffle-unixnu-runtime: uncertain=1 backing_retained=1\n");return finish(false);}
 if(encoder)p_nmb_encoder_discard(encoder);
 if(command)p_nmb_command_buffer_release(command);
 if(buffer)p_nmb_buffer_release(buffer);
 if(queue)p_nmb_queue_release(queue);
 if(device)p_nmb_device_release(device);
 /* Keep the library loaded: its dispatch callbacks must not point into an
  * unloaded image while the process is returning to the resident loader. */
 std::printf("waffle-unixnu-runtime: resources_released=1\n");return finish(ok);
}
