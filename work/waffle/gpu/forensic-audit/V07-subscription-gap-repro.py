"""Compile actual native callback adapter; GL, MMIO and notifications are mocked."""
from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parents[4];s=subprocess.check_output(['git','show','238986e63f515e5acfea010a22854892195b52da:kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp'],cwd=r,text=True);a=s.index('void\nIOMobileFramebufferUserClient::armVSync(void)');b=s.index('IOReturn\nIOMobileFramebufferUserClient::externalMethod',a);body=s[a:b]
code=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include "waffle_vsync_phase.h"
#define NSEC_PER_SEC 1000000000ULL
#define NSEC_PER_USEC 1000ULL
#define kFBNotifyVSync 5
#define kIOReturnSuccess 0
#define kIOUserNotifyOptionCanDrop 1
using io_user_reference_t=uint64_t;using OSAsyncReference64=uint64_t[8];
static uint32_t gWaffleHardwareVSync=1,gWaffleVSyncDivider=2;
static uint64_t gWaffleVSyncPeriod=8000000,gWaffleVSyncMap=1,stamp=1000000000,ticks=1000001000,armed;
static unsigned sends,locks;static bool ready=true;static uint64_t sent[6];
static bool waffleVSyncReady(){return ready;}
static uint32_t refreshHz(){return 60;}
static uint64_t mach_absolute_time(){return ticks;}
static void nanoseconds_to_absolutetime(uint64_t n,uint64_t *p){*p=n;}
static void absolutetime_to_nanoseconds(uint64_t n,uint64_t *p){*p=n;}
static void IOLockLock(int *){assert(!locks);locks++;}
static void IOLockUnlock(int *){assert(locks==1);locks--;}
static void thread_call_enter_delayed(int,uint64_t t){armed=t;}
static void redwood_tl(const char *,...){}
static bool waffleDisplayRead(void *,uint32_t offset,uint32_t *v){assert(offset==0x36214 || offset==0x36218);*v=offset==0x36218?stamp>>32:stamp;return true;}
static void setAsyncReference64(uint64_t *,void *,uint64_t,uint64_t,int){}
static void sendAsyncResult64WithOptions(uint64_t *,int,uint64_t *a,int n,int){assert(!locks && n==6);memcpy(sent,a,sizeof(sent));sends++;}
class IOMobileFramebufferUserClient{public:
 int lock=0,*fLock=&lock,fVSyncCall=1,fTask=0;void *fPorts[8]={nullptr,nullptr,nullptr,nullptr,nullptr,(void *)1};uint64_t fCallbacks[8]={0,0,0,0,0,1},fRefcons[8]={};
 uint64_t fVSyncTime=0,fVSyncCount=0;bool fClosed=false,fVSyncRunning=true,fHardwareVSyncDisabled=false;uint32_t fHardwareEvents=0;
 waffle_vsync_phase fHardwarePhase={};void armVSync();void vsync();};
'''+body+r'''
int main(){
 IOMobileFramebufferUserClient c;c.vsync();assert(!sends && armed==ticks+500000);
 stamp+=8000000;ticks=stamp+1000;c.vsync();assert(!sends);
 stamp+=8000000;ticks=stamp+1000;c.vsync();assert(sends==1 && sent[0]==uint32_t(stamp) && sent[1]==stamp>>32 && sent[4]==1 && c.fHardwareEvents==1);
 ticks+=10000;c.vsync();assert(sends==1);
 ticks=stamp+32000001;c.vsync();assert(sends==2 && c.fHardwareVSyncDisabled && sent[0]==uint32_t(ticks) && armed==ticks+NSEC_PER_SEC/60);
 c.fClosed=true;armed=0;c.vsync();assert(sends==2 && !c.fVSyncRunning && !armed);
 // Reproduce a healthy panel continuing while CoreAnimation unsubscribes.
 IOMobileFramebufferUserClient paused;stamp=ticks+100000000;ticks=stamp+1000;
 paused.vsync();assert(paused.fHardwarePhase.initialized && !paused.fHardwareVSyncDisabled);
 paused.fCallbacks[5]=0;paused.vsync();assert(!paused.fVSyncRunning);
 stamp+=10*gWaffleVSyncPeriod;ticks=stamp+1000;paused.fCallbacks[5]=1;paused.fVSyncRunning=true;
 unsigned before=sends;paused.vsync();assert(paused.fHardwareVSyncDisabled && sends==before+1);
 // Healthy fresh timestamp after a subscription gap incorrectly becomes permanent fallback.
 gWaffleHardwareVSync=0;IOMobileFramebufferUserClient legacy;legacy.fVSyncTime=ticks+123;legacy.vsync();assert(sends==4 && sent[0]==uint32_t(ticks+123));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('REPRODUCED healthy TE after disabled subscription gap forces fallback. PASS actual armVSync/vsync: no duplicate notifications, TE timestamp preserved, divide-by2,500us poll, bounded stale fallback, closed client no reschedule, default software behavior preserved. Hardware mocked.')
