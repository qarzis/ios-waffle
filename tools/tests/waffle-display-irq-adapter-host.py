#!/usr/bin/env python3
"""Execute actual observer/adapter to catch context, allowlist and off-mode errors."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];source=(r/'kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_text();code=source[source.index('struct WaffleDisplayCompletionRecord'):source.index('static void waffleDisplayCompactLog(')]
code=code.replace('__asm__ volatile("dsb sy" ::: "memory");','')
h=r'''
#include <cassert>
#include <cstdint>
#include "waffle_display_irq_probe.h"
using vm_offset_t=uintptr_t;
static unsigned gWaffleDisplayIRQProbe=1,gWaffleDisplayCompletionAudit=1,gWaffleDisplayPresent=1;
static uint32_t mem[0x84000/4];static uint64_t ticks;
static uint64_t mach_absolute_time(){return ++ticks;}
static bool waffleDisplayRead(void *p,uint32_t off,uint32_t *v){assert(p==mem && !(off&3) && off<sizeof(mem));*v=mem[off/4];if(off==0x1014 && mem[0x1018/4]==0x100)*v&=~0x100u;return true;}
'''
t=r'''
int main(){
 WaffleDisplayFlipContext c{};WaffleDisplayCompletionRecord records[128]{};c.dpu=(uintptr_t)mem;c.owner=&c;c.audit=records;c.auditSequence=1;
 mem[0]=0xa0000000;mem[0x3625c/4]=0xf0000;mem[0x360a4/4]=9;mem[0x5014/4]=mem[0x7014/4]=WAFFLE_DISPLAY_FRONT;mem[0x160f4/4]=2;mem[0x362c0/4]=1;mem[0x1014/4]=0x101;
 c.auditStage=2;waffleDisplayCompletionObserve(&c,2);
 mem[0x5014/4]=mem[0x7014/4]=WAFFLE_DISPLAY_TEST;mem[0x16018/4]=3;waffleDisplayCompletionObserve(&c,3);
 c.auditStage=1;mem[0x360a4/4]=10;mem[0x16018/4]=0;waffleDisplayCompletionObserve(&c,1);
 assert(records[2].probe.action==1 && records[2].probe.wrote && c.probeWrites==1 && c.probeState.armed);
 mem[0x1018/4]=0;waffleDisplayCompletionObserve(&c,1);assert(records[3].probe.action==2 && c.probeWrites==1);
 gWaffleDisplayIRQProbe=0;unsigned count=c.auditCount;waffleDisplayCompletionObserve(&c,1);assert(c.auditCount==count+1 && !records[count].probe.action && c.probeWrites==1);
 assert(!waffleDisplayIRQProbeWrite(&c,0x1018,0x100));gWaffleDisplayIRQProbe=1;
 assert(!waffleDisplayIRQProbeWrite(&c,0x1010,0x100));assert(!waffleDisplayIRQProbeWrite(&c,0x1018,0x200));
 mem[0x1010/4]=1;assert(!waffleDisplayIRQProbeWrite(&c,0x1018,0x100));mem[0x1010/4]=0;
 mem[0x3625c/4]=0x10000;assert(!waffleDisplayIRQProbeWrite(&c,0x1018,0x100));mem[0x3625c/4]=0;
 c.quiescing=true;count=c.auditCount;waffleDisplayCompletionObserve(&c,1);assert(c.auditCount==count && !waffleDisplayIRQProbeWrite(&c,0x1018,0x100));
 c.quiescing=false;c.probeWrites=8;assert(!waffleDisplayIRQProbeWrite(&c,0x1018,0x100));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(h+code+t)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('PASS actual IRQ observer callbacks: correct contexts, masked clear/fresh flag, default off, route/mask/write allowlist/8-write/quiesce refusal; MMIO modeled.')
