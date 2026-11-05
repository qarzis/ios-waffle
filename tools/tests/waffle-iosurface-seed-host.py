#!/usr/bin/env python3
"""Actual IOSurface lock/unlock traps follow the SDK modification-seed contract."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/iokit/Kernel/MiniIOSurface.cpp').read_text()
start=s.index('IOReturn\nIOSurfaceRootUserClient::lockCommon(')
end=s.index('IOReturn\nIOSurfaceRootUserClient::trapDetach(',start)
code=s[start:end]
signature=code[code.index('lockCommon(')+len('lockCommon('):code.index(')\n{')]
h=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "waffle_surface_access.h"
using IOReturn=int;
using user_addr_t=uintptr_t;
constexpr int kIOReturnSuccess=0,kIOReturnNotFound=1,kIOReturnCannotLock=2,kIOReturnError=3;
constexpr uint32_t kSurfaceLockReadOnly=1;
static bool held;
static uint32_t gWaffleSurfaceLockAudit,gWaffleSurfaceLockRows,logs;
static int proc_selfpid(){return 1;}
static void loader_log_line(const char *line){assert(!held && strstr(line,"waffle-surface-lock: seq="));logs++;}
static int lock;
static int *gSurfaceLock=&lock;
static void IOLockLock(int *){assert(!held);held=true;}
static void IOLockUnlock(int *){assert(held);held=false;}
struct minisurf_shared{uint32_t seed=17;};
struct MiniIOSurface{waffle_surface_access access{};minisurf_shared state;minisurf_shared *shared(){return &state;}};
struct minisurf_client_ref{MiniIOSurface *surface;uint32_t cpuWriters=0;};
static constexpr unsigned WAFFLE_SURFACE_WAIT_MS=250,kMillisecondScale=1,THREAD_UNINT=0,THREAD_TIMED_OUT=1;
static unsigned sleeps,holds;static bool timeout;static void (*during_sleep)();
static void clock_interval_to_deadline(unsigned,unsigned,uint64_t *d){*d=250;}
static void surfaceHold(MiniIOSurface *){assert(held);holds++;}
static void surfaceUnhold(MiniIOSurface *){assert(held && holds);holds--;}
static void IOLockWakeup(int *,void *,bool){assert(held);}
static int IOLockSleepDeadline(int *,void *event,uint64_t,unsigned){
 assert(held);sleeps++;
 if(timeout)return THREAD_TIMED_OUT;
 auto *access=static_cast<waffle_surface_access *>(event);
 assert(access->waiting_writers==1 && access->gpu_readers==1);
 assert(waffle_surface_gpu_read_end(access));if(during_sleep)during_sleep();return 0;
}
static MiniIOSurface target;
static minisurf_client_ref ref{&target},moved{&target};
static minisurf_client_ref *current_ref=&ref;
static void remove_ref(){current_ref=nullptr;}
static void move_ref(){current_ref=&moved;ref.surface=nullptr;}

static void copyout(const void *source,user_addr_t dest,unsigned bytes){assert(!held);memcpy((void *)dest,source,bytes);}
class IOSurfaceRootUserClient {
public:
 minisurf_client_ref *findRef(uint32_t sid,bool create){assert(held && !create);return sid==1?current_ref:nullptr;}
 IOReturn lockCommon(SIGNATURE);
 IOReturn trapLock(void *,void *,void *,void *,void *,void *);
 IOReturn trapUnlock(void *,void *,void *,void *,void *,void *);
};
'''.replace('SIGNATURE',signature)
test=r'''
int main(){
 IOSurfaceRootUserClient client;uint32_t seed=0;
 auto lock=[&](unsigned id,unsigned flags){return client.trapLock((void *)(uintptr_t)id,(void *)(uintptr_t)flags,(void *)&seed,nullptr,nullptr,nullptr);};
 auto unlock=[&](unsigned id,unsigned flags){return client.trapUnlock((void *)(uintptr_t)id,(void *)(uintptr_t)flags,(void *)&seed,nullptr,nullptr,nullptr);};
 assert(lock(1,0)==0 && seed==17 && target.state.seed==17);
 assert(unlock(1,0)==0 && seed==18 && target.state.seed==18);
 for(unsigned i=0;i<100;i++){
  assert(lock(1,kSurfaceLockReadOnly)==0 && seed==18);
  assert(unlock(1,kSurfaceLockReadOnly)==0 && seed==18);
 }
 assert(lock(2,0)==kIOReturnNotFound && target.state.seed==18);
 assert(unlock(2,0)==kIOReturnNotFound && target.state.seed==18);
 target.state.seed=UINT32_MAX;
 assert(lock(1,0)==0 && seed==UINT32_MAX);
 assert(unlock(1,0)==0 && seed==0);
 assert(!held && !logs);
 assert(waffle_surface_gpu_read_begin(&target.access));
 assert(lock(1,2)==kIOReturnCannotLock && !ref.cpuWriters && !sleeps);
 assert(lock(1,1)==0 && unlock(1,1)==0 && target.access.gpu_readers==1);
 timeout=true;assert(lock(1,0)==kIOReturnCannotLock && !holds && !target.access.waiting_writers);
 timeout=false;assert(lock(1,0)==0 && !holds && !target.access.gpu_readers && ref.cpuWriters==1);
 assert(unlock(1,0)==0 && !target.access.cpu_writers);
 assert(waffle_surface_gpu_read_begin(&target.access));during_sleep=remove_ref;
 assert(lock(1,0)==kIOReturnNotFound && !holds && !target.access.waiting_writers && !target.access.cpu_writers);
 current_ref=&ref;assert(waffle_surface_gpu_read_begin(&target.access));during_sleep=move_ref;
 assert(lock(1,0)==0 && !holds && moved.cpuWriters==1 && !ref.cpuWriters);
 assert(unlock(1,0)==0 && !moved.cpuWriters && !target.access.cpu_writers);
 ref.surface=&target;current_ref=&ref;during_sleep=nullptr;
 target.state.seed=0;
 gWaffleSurfaceLockAudit=1;
 assert(lock(1,0)==0 && seed==0);assert(unlock(1,0)==0 && seed==1);
 for(unsigned i=0;i<200;i++){assert(lock(1,1)==0);assert(unlock(1,1)==0);}
 assert(logs==128 && gWaffleSurfaceLockRows==128 && seed==1 && !held);
 assert(lock(2,0)==kIOReturnNotFound && logs==128);
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.cpp').write_text(h+code+test)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I',str(root/'kernel/files/bsd/sys'),'-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual IOSurface traps: write-lock preserves seed, write-unlock increments once; readonly pairs/unknown surfaces/wraparound. Host only; no animation fix claim.')
