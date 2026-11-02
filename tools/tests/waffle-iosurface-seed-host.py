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
using IOReturn=int;
using user_addr_t=uintptr_t;
constexpr int kIOReturnSuccess=0,kIOReturnNotFound=1;
constexpr uint32_t kSurfaceLockReadOnly=1;
static bool held;
static int lock;
static int *gSurfaceLock=&lock;
static void IOLockLock(int *){assert(!held);held=true;}
static void IOLockUnlock(int *){assert(held);held=false;}
struct minisurf_shared{uint32_t seed=17;};
struct MiniIOSurface{minisurf_shared state;minisurf_shared *shared(){return &state;}};
struct minisurf_client_ref{MiniIOSurface *surface;};
static MiniIOSurface target;
static minisurf_client_ref ref{&target};
static void copyout(const void *source,user_addr_t dest,unsigned bytes){assert(!held);memcpy((void *)dest,source,bytes);}
class IOSurfaceRootUserClient {
public:
 minisurf_client_ref *findRef(uint32_t sid,bool create){assert(held && !create);return sid==1?&ref:nullptr;}
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
 assert(!held);
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.cpp').write_text(h+code+test)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual IOSurface traps: write-lock preserves seed, write-unlock increments once; readonly pairs/unknown surfaces/wraparound. Host only; no animation fix claim.')
