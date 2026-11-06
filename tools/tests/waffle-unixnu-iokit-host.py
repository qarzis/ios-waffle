"""Actual IOKit adapter/cache and forced unmap ordering against framework model."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=re.sub(r'^#include .*$','',(root/'kernel/files/iokit/Kernel/WaffleNativeGPU.cpp').read_text(),flags=re.M)
h=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <cerrno>
#include "waffle_gpu_iokit.h"
#include "waffle_gpu_memory.h"
#define __printflike(a,b)
#define OSDeclareDefaultStructors(x)
#define OSDefineMetaClassAndStructors(a,b)
#define OSTypeAlloc(x) new x
using UInt32=uint32_t;using IOOptionBits=uint32_t;using IOReturn=int;using task_t=void*;
struct OSDictionary{};struct IOExternalMethodDispatch{};
struct IOExternalMethodArguments {unsigned scalarInputCount=0,scalarOutputCount=0;void *structureInputDescriptor=nullptr,*structureOutputDescriptor=nullptr;size_t structureInputSize=0,structureOutputSize=0;const void *structureInput=nullptr;void *structureOutput=nullptr;};
enum {kIOReturnSuccess=0,kIOReturnBadArgument=1,kIOReturnNotPrivileged=2,kIOReturnBusy=3,kIOReturnNoMemory=4,kIOReturnNoResources=5,kIOReturnUnsupported=6,kIOReturnNotReady=7,kIOReturnIOError=8,kIOMapAnywhere=1,kIOMapWriteCombineCache=2};
struct proc {int pid;};static proc process{1};static proc *current_proc(){return &process;}static int proc_pid(proc*p){return p->pid;}
static task_t active_task=(void*)0x111;static task_t current_task(){return active_task;}
static unsigned allocations,unmaps,descriptors_freed;static bool allocation_fail;
static void *IOMallocZero(size_t n){if(allocation_fail)return nullptr;allocations++;return calloc(1,n);}
static void IOFree(void*p,size_t){assert(p&&allocations);allocations--;free(p);}
struct IOLock {std::mutex mutex;};static unsigned held;
static IOLock *IOLockAlloc(){return new IOLock;}
static void IOLockFree(IOLock*p){delete p;}
static void IOLockLock(IOLock*p){p->mutex.lock();assert(!held);held++;}
static void IOLockUnlock(IOLock*p){assert(held==1);held--;p->mutex.unlock();}
class OSObject {public:unsigned refs=1;virtual~OSObject()=default;virtual void free(){};void retain(){refs++;}void release(){assert(refs);if(!--refs){free();delete this;}}};
class IOMemoryDescriptor:public OSObject {public:unsigned maps=0;~IOMemoryDescriptor(){assert(!maps);descriptors_freed++;}};
class IOUserClient;class IOService;static IOService *published;
class IOService:public OSObject {public:virtual bool init(){return true;}virtual bool attach(IOService*){return true;}virtual void detach(IOService*){}virtual bool start(IOService*){return true;}virtual void stop(IOService*){};void setName(const char*){}void registerService(){retain();published=this;}static IOService *getResourceService();virtual IOReturn newUserClient(task_t,void*,UInt32,OSDictionary*,IOUserClient**){return kIOReturnUnsupported;}};
static IOService resource;IOService *IOService::getResourceService(){return &resource;}
class IOUserClient:public IOService {public:virtual bool initWithTask(task_t,void*,UInt32,OSDictionary*){return true;}virtual IOReturn clientClose(){return 0;}virtual IOReturn clientMemoryForType(UInt32,IOOptionBits*,IOMemoryDescriptor**){return 0;}virtual IOReturn externalMethod(uint32_t,IOExternalMethodArguments*,IOExternalMethodDispatch*,OSObject*,void*){return 0;}bool removeMappingForDescriptor(IOMemoryDescriptor*d){if(!d->maps)return false;d->maps--;unmaps++;d->release();return true;}bool terminate(){return true;}};
static bool enabled;static bool PE_parse_boot_argn(const char*n,void*out,int bytes){assert(!strcmp(n,"waffle_unixnu_iokit")&&bytes==4);*(uint32_t*)out=enabled;return enabled;}
extern "C" void redwood_tl(const char*,...){}
static void *cookie;static unsigned leases,opens,closes;static uint32_t handle=1;static IOMemoryDescriptor *backing;
extern "C" int waffle_gpu_iokit_open(void*o){if(cookie)return EBUSY;cookie=o;opens++;return 0;}
extern "C" int waffle_gpu_iokit_close(void*o){assert(held);if(cookie!=o)return EPERM;assert(!backing || !backing->maps);if(backing){backing->release();backing=nullptr;}cookie=nullptr;leases=0;closes++;return 0;}
extern "C" uintptr_t waffle_gpu_iokit_memory(void*o,uint32_t t){assert(held);return cookie==o && process.pid==1 && t==handle && leases?(uintptr_t)backing:0;}
extern "C" int waffle_gpu_iokit_call(void*o,waffle_unixnu_call*c){
 assert(held);if(cookie!=o || process.pid!=1)return EPERM;
 if(c->method==2){assert(!backing);backing=new IOMemoryDescriptor;uint64_t h=handle;memcpy(c->payload,&h,8);return 0;}
 if(c->method==13){leases++;waffle_unixnu_cpu_reply r{handle,0,16384};memcpy(c->payload,&r,sizeof(r));return 0;}
 if(c->method==14){waffle_unixnu_cpu_unmap u;memcpy(&u,c->payload,sizeof(u));if(u.handle!=handle || u.token!=handle || u.reserved || !leases)return EINVAL;leases--;return 0;}
 if(c->method==4){if(leases)return EBUSY;assert(backing && !backing->maps && backing->refs==1);backing->release();backing=nullptr;return 0;}
 return 0;
}
'''
t=r'''
static IOReturn call(IOUserClient*c,unsigned m,const void*in,size_t n,void*out,size_t bytes){IOExternalMethodArguments a;a.structureInput=in;a.structureInputSize=n;a.structureOutput=out;a.structureOutputSize=bytes;return c->externalMethod(m,&a,nullptr,nullptr,nullptr);}
int main(){
 assert(waffle_gpu_iokit_register()&&!published&&!opens);enabled=true;assert(waffle_gpu_iokit_register()&&published&&!opens);
 IOUserClient *c=nullptr;process.pid=2;assert(published->newUserClient(active_task,nullptr,0,nullptr,&c)==kIOReturnNotPrivileged&&!c);process.pid=1;
 assert(!published->newUserClient(active_task,nullptr,0,nullptr,&c)&&c&&opens==1);
 IOUserClient *other=nullptr;assert(published->newUserClient(active_task,nullptr,0,nullptr,&other)==kIOReturnNotReady&&!other&&opens==1);
 waffle_unixnu_alloc alloc{4096,12,0};uint64_t h=0;assert(!call(c,2,&alloc,sizeof(alloc),&h,8)&&h==1);
 waffle_unixnu_cpu_reply reply{};assert(!call(c,13,&h,8,&reply,sizeof(reply)));assert(!call(c,13,&h,8,&reply,sizeof(reply))&&leases==2);
 IOMemoryDescriptor *first=nullptr,*second=nullptr;IOOptionBits options=0;
 assert(!c->clientMemoryForType(handle,&options,&first)&&first==backing);first->maps++;first->retain();first->release();
 assert(!c->clientMemoryForType(handle,&options,&second)&&second==first);second->maps++;second->retain();second->release();
 assert(backing->maps==2&&backing->refs==4);
 assert(call(c,4,&h,8,nullptr,0)==kIOReturnBusy&&!unmaps);
 waffle_unixnu_cpu_unmap u{h,handle,0};assert(!call(c,14,&u,sizeof(u),nullptr,0)&&leases==1&&!unmaps);assert(!call(c,14,&u,sizeof(u),nullptr,0)&&!leases&&unmaps==2&&backing->refs==1);
 assert(c->clientMemoryForType(handle,&options,&second)==kIOReturnNotReady&&!second);
 assert(!call(c,4,&h,8,nullptr,0)&&descriptors_freed==1);
 assert(call(c,15,nullptr,0,nullptr,0)==kIOReturnUnsupported);
 assert(call(c,2,&alloc,sizeof(alloc)-1,&h,8)==kIOReturnBadArgument);
 allocation_fail=true;assert(call(c,2,&alloc,sizeof(alloc),&h,8)==kIOReturnNoMemory);allocation_fail=false;
 handle+=WAFFLE_GPU_BO_LIMIT;assert(!call(c,2,&alloc,sizeof(alloc),&h,8));assert(!call(c,13,&h,8,&reply,sizeof(reply)));assert(!c->clientMemoryForType(handle,&options,&first));first->maps++;first->retain();first->release();
 process.pid=2;assert(c->clientMemoryForType(handle,&options,&second)==kIOReturnNotReady&&!second);
 assert(!c->clientClose()&&!cookie&&unmaps==3&&descriptors_freed==2&&closes==1);c->release();assert(!allocations&&!held);published->release();return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(h+source+t)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-pthread','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual IOKit adapter: default-off/PID1/exclusive open, same descriptor for repeated CPU maps, two leases/last-unmap revocation, generation reuse, malformed/OOM/unsupported refusal, worker-close revokes maps before backing release; framework/backend modeled')
