/* SPDX-License-Identifier: MIT
 * NativeAdreno direct IOKit transport for the qualified Waffle backend.
 * CPU-view identity/drop ordering follows UniXNU Adreno740/NativeAdrenoPublish.cpp
 * (pinned in work/waffle/unixnu-audit/GPU_PROVENANCE.json). No iOS17 accelerator
 * vtable or AGX class layout is copied. Private PID1 connection, opt-in only. */
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <kern/task.h>
#include <sys/proc.h>
#include <sys/errno.h>
#include <pexpert/pexpert.h>
#include "../../bsd/sys/waffle_gpu_iokit.h"
#include "../../bsd/sys/waffle_gpu_memory.h"
extern "C" void redwood_tl(const char *,...) __printflike(1,2);
static IOReturn waffle_native_error(int error)
{
 switch(error){
 case 0:return kIOReturnSuccess;case EINVAL:return kIOReturnBadArgument;
 case EPERM:return kIOReturnNotPrivileged;case EBUSY:return kIOReturnBusy;
 case ENOMEM:return kIOReturnNoMemory;case ENOSPC:return kIOReturnNoResources;
 case ENOTSUP:return kIOReturnUnsupported;case ENXIO:return kIOReturnNotReady;
 default:return kIOReturnIOError;
 }
}
class WaffleNativeGPUUserClient : public IOUserClient {
 OSDeclareDefaultStructors(WaffleNativeGPUUserClient);
 struct View {uint32_t token;IOMemoryDescriptor *descriptor;};
 View *views_=nullptr;
 IOLock *gate_=nullptr;
 bool live_=false;
 void dropViews(uint32_t token){
  if(!views_)return;
  for(unsigned i=0;i<WAFFLE_GPU_BO_LIMIT;i++){
   auto &v=views_[i];if(!v.descriptor || (token && token!=v.token))continue;
   /* IOConnectUnmapMemory64 looks this descriptor up again. Reuse its identity
    * and remove every retained map before releasing the view/backing. */
   while(removeMappingForDescriptor(v.descriptor)){}
   v.descriptor->release();v={};
  }
 }
public:
 bool initWithTask(task_t task,void *security,UInt32 type,OSDictionary *properties) override {
  if(task!=current_task() || proc_pid(current_proc())!=1 || type)return false;
  if(!IOUserClient::initWithTask(task,security,type,properties))return false;
  gate_=IOLockAlloc();views_=static_cast<View *>(IOMallocZero(sizeof(View)*WAFFLE_GPU_BO_LIMIT));
  return gate_ && views_;
 }
 bool start(IOService *provider) override {
  if(!IOUserClient::start(provider))return false;
  live_=waffle_gpu_iokit_open(this)==0;
  if(!live_)IOUserClient::stop(provider);return live_;
 }
 IOReturn clientClose() override {
  if(!gate_)return kIOReturnNotReady;
  IOLockLock(gate_);dropViews(0);
  int error=live_?waffle_gpu_iokit_close(this):0;live_=false;
  IOLockUnlock(gate_);if(!error)terminate();return waffle_native_error(error);
 }
 void free() override {
  if(gate_){
   IOLockLock(gate_);dropViews(0);
   if(live_){int error=waffle_gpu_iokit_close(this);if(error)redwood_tl("waffle-unixnu-iokit: close_error=%d\n",error);live_=false;}
   IOLockUnlock(gate_);
  }
  if(views_){IOFree(views_,sizeof(View)*WAFFLE_GPU_BO_LIMIT);views_=nullptr;}
  if(gate_){IOLockFree(gate_);gate_=nullptr;}
  IOUserClient::free();
 }
 IOReturn clientMemoryForType(UInt32 type,IOOptionBits *options,IOMemoryDescriptor **memory) override {
  if(memory)*memory=nullptr;
  if(!memory || !options || !type || !gate_)return kIOReturnBadArgument;
  IOLockLock(gate_);
  uintptr_t raw=live_?waffle_gpu_iokit_memory(this,type):0;
  if(!raw){IOLockUnlock(gate_);return kIOReturnNotReady;}
  View &v=views_[(type-1)%WAFFLE_GPU_BO_LIMIT];
  if(v.descriptor && v.token!=type){IOLockUnlock(gate_);return kIOReturnBusy;}
  if(!v.descriptor){v.token=type;v.descriptor=reinterpret_cast<IOMemoryDescriptor *>(raw);v.descriptor->retain();}
  v.descriptor->retain();*memory=v.descriptor;*options=kIOMapAnywhere|kIOMapWriteCombineCache;
  IOLockUnlock(gate_);return kIOReturnSuccess;
 }
 IOReturn externalMethod(uint32_t method,IOExternalMethodArguments *args,IOExternalMethodDispatch *,OSObject *,void *) override {
  if(!args || !gate_)return kIOReturnBadArgument;
  size_t in=0,out=0;
  /* Exact upstream method selectors/records. Unsupported capabilities stay
   * unsupported; DeviceInfo comes from the pinned PJD110 profile. */
  switch(method){
  case 1:out=sizeof(waffle_unixnu_params);break;
  case 2:in=sizeof(waffle_unixnu_alloc);out=8;break;
  case 3:in=sizeof(waffle_unixnu_map);out=8;break;
  case 4:in=8;break;
  case 5:in=sizeof(waffle_unixnu_submit);out=8;break;
  case 6:in=sizeof(waffle_unixnu_wait);break;
  case 13:in=8;out=sizeof(waffle_unixnu_cpu_reply);break;
  case 14:in=sizeof(waffle_unixnu_cpu_unmap);break;
  case 15:out=sizeof(waffle_unixnu_device_info);break;
  default:return kIOReturnUnsupported;
  }
  if(args->scalarInputCount || args->scalarOutputCount || args->structureInputDescriptor || args->structureOutputDescriptor ||
     args->structureInputSize!=in || args->structureOutputSize!=out || (in && !args->structureInput) || (out && !args->structureOutput))return kIOReturnBadArgument;
  auto *call=static_cast<waffle_unixnu_call *>(IOMallocZero(sizeof(waffle_unixnu_call)));
  if(!call)return kIOReturnNoMemory;
  call->version=2;call->method=method;call->input_bytes=(uint32_t)in;call->output_bytes=(uint32_t)out;
  if(in)memcpy(call->payload,args->structureInput,in);
  IOLockLock(gate_);
  int error=live_?waffle_gpu_iokit_call(this,call):ENXIO;
  if(!error && method==14){
   waffle_unixnu_cpu_unmap request;memcpy(&request,args->structureInput,sizeof(request));
   if(!waffle_gpu_iokit_memory(this,request.token))dropViews(request.token);
  }
  if(!error && out)memcpy(args->structureOutput,call->payload,out);
  IOLockUnlock(gate_);IOFree(call,sizeof(*call));return waffle_native_error(error);
 }
};
OSDefineMetaClassAndStructors(WaffleNativeGPUUserClient,IOUserClient);
class NativeAdrenoGpuPublished : public IOService {
 OSDeclareDefaultStructors(NativeAdrenoGpuPublished);
public:
 IOReturn newUserClient(task_t task,void *security,UInt32 type,OSDictionary *properties,IOUserClient **handler) override {
  if(!handler)return kIOReturnBadArgument;*handler=nullptr;
  if(type || task!=current_task() || proc_pid(current_proc())!=1)return kIOReturnNotPrivileged;
  auto *client=OSTypeAlloc(WaffleNativeGPUUserClient);
  if(!client)return kIOReturnNoMemory;
  if(!client->initWithTask(task,security,type,properties) || !client->attach(this)) {client->release();return kIOReturnNotReady;}
  if(!client->start(this)){client->detach(this);client->release();return kIOReturnNotReady;}
  *handler=client;return kIOReturnSuccess;
 }
};
OSDefineMetaClassAndStructors(NativeAdrenoGpuPublished,IOService);
extern "C" bool waffle_gpu_iokit_register(void)
{
 uint32_t enabled=0;
 if(!PE_parse_boot_argn("waffle_unixnu_iokit",&enabled,sizeof(enabled)) || enabled!=1)return true;
 auto *provider=IOService::getResourceService();if(!provider)return false;
 auto *service=OSTypeAlloc(NativeAdrenoGpuPublished);if(!service)return false;
 if(!service->init() || !service->attach(provider)){service->release();return false;}
 if(!service->start(provider)){service->detach(provider);service->release();return false;}
 service->setName("NativeAdrenoGpuPublished");service->registerService();service->release();
 redwood_tl("waffle-unixnu-iokit: published=1 PID1_only=1 default_off=1 Metal=0\n");return true;
}
