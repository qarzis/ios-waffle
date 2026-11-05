#!/usr/bin/env python3
"""Compile actual service spawn block; ensure torch returns rather than serving inline."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text();start=s.index(' if(ok && haptic_test==2) {');end=s.index('\n}\nstatic void\nshow_registers',start);block=s[start:end]
assert 'waffle_haptic_service(&c)' not in s
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
typedef int thread_t;
#define KERN_SUCCESS 0
struct waffle_haptic_bus_context {unsigned identity;};static struct waffle_haptic_bus_context haptic_pulse_context;
static unsigned haptic_test,spawns,releases,failed;static bool reject;
static void waffle_haptic_service_thread(void){}
static int kernel_thread_start(void (*entry)(void),void *arg,thread_t *t){assert(entry==waffle_haptic_service_thread&&!arg);spawns++;*t=1;return reject?1:0;}
static void thread_deallocate(thread_t t){assert(t==1);releases++;}
static void say(const char *fmt){(void)fmt;failed++;}
static void launch(bool ok){struct waffle_haptic_bus_context c={1234};
'''+block+r'''
}
int main(void){for(unsigned mode=0;mode<3;mode++)for(unsigned good=0;good<2;good++)for(unsigned bad=0;bad<2;bad++){spawns=releases=failed=0;haptic_test=mode;reject=bad;launch(good);bool requested=mode==2&&good;assert(spawns==requested);assert(releases==(requested&&!bad));assert(failed==(requested&&bad));if(requested)assert(haptic_pulse_context.identity==1234);}puts("PASS actual haptic spawn block: context retained, dedicated mode only, worker failure handled, no blocking service call in torch initialization.");}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
