#!/usr/bin/env python3
"""Exercise actual MiniIOSurface batch lease code with bounded sleep callbacks."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/iokit/Kernel/MiniIOSurface.cpp').read_text()
code=s[s.index('static MiniIOSurface *surfaceReadObject'):s.index('extern "C" bool\nwaffle_gpu_surface_release')]
h=r'''
#include <cassert>
#include <cstddef>
#include "waffle_surface_access.h"
#include "waffle_gpu_surface.h"
struct MiniIOSurface {uint32_t sid;bool client;waffle_surface_access access;};
static int mutex;static int *gSurfaceLock=&mutex;static bool held,timeout;static unsigned sleeps,wakes;
static constexpr unsigned kMillisecondScale=1,THREAD_UNINT=0,THREAD_TIMED_OUT=1;
static MiniIOSurface a{1,false,{}},b{2,false,{}};
static void IOLockLock(int *){assert(!held);held=true;}
static void IOLockUnlock(int *){assert(held);held=false;}
static void clock_interval_to_deadline(unsigned,unsigned,uint64_t *d){*d=250;}
static void IOLockWakeup(int *,void *,bool){assert(held);wakes++;}
static int IOLockSleepDeadline(int *,void *event,uint64_t,unsigned){
 assert(held && !a.access.gpu_readers && !b.access.gpu_readers);sleeps++;
 if(timeout)return THREAD_TIMED_OUT;
 auto *state=static_cast<waffle_surface_access *>(event);state->cpu_writers=0;state->waiting_writers=0;return 0;
}
static waffle_gpu_surface_backing *get(const void *p,uint32_t i){return static_cast<waffle_gpu_surface_backing *const *>(p)[i];}
'''
t=r'''
int main(){
 waffle_gpu_surface_backing x{},y{},z{};
 x.object=(uintptr_t)&a;x.surface=1;y.object=(uintptr_t)&b;y.surface=2;z=x;
 waffle_gpu_surface_backing *pair[]={&x,&y};
 assert(waffle_gpu_surface_reads_begin(2,get,pair,0));
 uint32_t readers=0,waiting=0;assert(waffle_gpu_surface_read_state(&x,&readers,&waiting) && readers==1 && !waiting);
 assert(x.gpu_reading && y.gpu_reading && a.access.gpu_readers==1 && b.access.gpu_readers==1);
 assert(!waffle_gpu_surface_reads_begin(2,get,pair,0));
 assert(waffle_gpu_surface_reads_end(2,get,pair) && wakes==2);
 assert(!waffle_gpu_surface_reads_end(2,get,pair));
 b.access.cpu_writers=1;assert(!waffle_gpu_surface_reads_begin(2,get,pair,0) && !a.access.gpu_readers);
 timeout=true;assert(!waffle_gpu_surface_reads_begin(2,get,pair,250) && !a.access.gpu_readers);
 timeout=false;assert(waffle_gpu_surface_reads_begin(2,get,pair,250) && sleeps==2);
 assert(waffle_gpu_surface_reads_end(2,get,pair));
 b.access.waiting_writers=1;assert(!waffle_gpu_surface_reads_begin(2,get,pair,0));b.access.waiting_writers=0;
 waffle_gpu_surface_backing *duplicate[]={&x,&x};assert(!waffle_gpu_surface_reads_begin(2,get,duplicate,0));
 waffle_gpu_surface_backing *shared[]={&x,&z};a.access.gpu_readers=UINT32_MAX-1;
 assert(!waffle_gpu_surface_reads_begin(2,get,shared,0) && !x.gpu_reading && !z.gpu_reading && a.access.gpu_readers==UINT32_MAX-1);
 a.access.gpu_readers=0;assert(waffle_gpu_surface_reads_begin(2,get,shared,0) && a.access.gpu_readers==2);
 assert(!waffle_gpu_surface_reads_end(2,get,duplicate) && a.access.gpu_readers==2);
 assert(waffle_gpu_surface_reads_end(2,get,shared) && !a.access.gpu_readers);
 assert(!waffle_gpu_surface_reads_begin(0,get,pair,0));assert(!waffle_gpu_surface_reads_begin(2,get,pair,251));
 assert(waffle_gpu_surface_reads_begin(1,get,pair,0));assert(waffle_gpu_surface_read_end_one(&x));assert(!held);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(h+code+t)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual batch leases: atomic acquisition, waiting without partial holds, duplicate/overflow rollback, shared backing, release.')
