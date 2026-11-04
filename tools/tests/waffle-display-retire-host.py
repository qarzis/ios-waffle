#!/usr/bin/env python3
"""Exercise actual bounded submission wait with completion/wakeup races."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_text()
start = source.index('bool\nIOMobileFramebuffer::waitForPresentation(')
opening = source.index('{', start)
end, depth = opening + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
method = source[start:end]
start = source.index('void\nIOMobileFramebuffer::retireSource(')
opening = source.index('{', start)
end, depth = opening + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
retire = source[start:end]
code = r'''
#include <cassert>
#include <cstdint>
#include <cstdarg>
using AbsoluteTime=uint64_t;
constexpr int SWAP_HELD_MS=700,kMillisecondScale=1,THREAD_UNINT=0,THREAD_TIMED_OUT=1;
static bool locked;
static unsigned sleeps, warnings, wakes;
static uint64_t completion[4];
static int results[4];
struct IOMobileFramebuffer {
 int *fSwapLock=nullptr; uint64_t fSwapCompleted=0;
 bool waitForPresentation(uint64_t);
 void retireSource(uint64_t);
};
static void clock_interval_to_deadline(int ms,int,AbsoluteTime *d){assert(ms==700);*d=12345;}
static void IOLockLock(int*){assert(!locked);locked=true;}
static void IOLockUnlock(int*){assert(locked);locked=false;}
static void IOLockWakeup(int*,void*,bool one){assert(locked && !one);wakes++;}
static int IOLockSleepDeadline(int*,void *event,AbsoluteTime deadline,int){
 assert(locked && deadline==12345 && sleeps<4);
 unsigned i=sleeps++;*static_cast<uint64_t*>(event)=completion[i];return results[i];
}
static void redwood_tl(const char*,...){assert(!locked);warnings++;}
''' + method + retire + r'''
static void reset(){locked=false;sleeps=warnings=wakes=0;for(unsigned i=0;i<4;i++){completion[i]=0;results[i]=0;}}
int main(){
 IOMobileFramebuffer f;
 reset();f.fSwapCompleted=5;assert(f.waitForPresentation(5)&&sleeps==0&&!locked);
 reset();f.fSwapCompleted=0;completion[0]=5;assert(f.waitForPresentation(5)&&sleeps==1&&!locked);
 // Spurious wake and completion of an earlier submission cannot retire this one.
 reset();f.fSwapCompleted=0;completion[0]=0;completion[1]=4;completion[2]=5;
 assert(f.waitForPresentation(5)&&sleeps==3&&!locked);
 // Completion wins over an expiring deadline if published under the same lock.
 reset();f.fSwapCompleted=0;completion[0]=5;results[0]=THREAD_TIMED_OUT;
 assert(f.waitForPresentation(5)&&warnings==0&&!locked);
 reset();f.fSwapCompleted=0;completion[0]=4;results[0]=THREAD_TIMED_OUT;
 assert(!f.waitForPresentation(5)&&warnings==1&&!locked);
 // A late completion remains observable by subsequent waits.
 f.fSwapCompleted=5;assert(f.waitForPresentation(5)&&!locked);
 reset();f.fSwapCompleted=0;completion[0]=UINT64_MAX;
 assert(f.waitForPresentation(UINT64_MAX)&&!locked);
 reset();f.fSwapCompleted=0;f.retireSource(0);assert(wakes==0 && !locked);
 f.retireSource(5);assert(f.fSwapCompleted==5 && wakes==1 && !locked);
 // Conservative post-show retirement cannot move back or wake twice.
 f.retireSource(5);f.retireSource(4);assert(f.fSwapCompleted==5 && wakes==1 && !locked);
 f.retireSource(6);assert(f.fSwapCompleted==6 && wakes==2 && !locked);
}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / 'retire.cpp'
    binary = Path(directory) / 'retire'
    cpp.write_text(code)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('PASS actual submission wait: already retired, wakeup, spurious/earlier completion, timeout race, late completion and uint64 boundary; locks/scheduler mocked')
