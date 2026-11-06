#!/usr/bin/env python3
"""Compile actual selector survey read adapter and check isolated-mode gates."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2]
s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text()
body=s[s.index('static bool\nwaffle_haptic_fifo_status_bus_read'):s.index('static bool\nwaffle_haptic_bus_write')]
code=r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "waffle_haptic_fifo_status.h"
struct peripheral {uint16_t id;bool found;};
struct waffle_haptic_bus_context {struct peripheral peripheral[3];};
static bool waffle_arb,haptic_active,haptic_fifo_status_active;
static unsigned level,haptic_test,calls;
static const char *spmi_read(const struct peripheral *p,uint8_t a,uint8_t *v,unsigned n){
 assert(n==1&&p->found&&waffle_haptic_fifo_status_read_allowed(p->id,a));calls++;*v=0;return NULL;
}
'''+body+r'''
int main(void){
 struct waffle_haptic_bus_context c={{{0x7f0,true},{0x7f1,true},{0x7f2,true}}};uint8_t v;
 for(unsigned bits=0;bits<32;bits++){
  waffle_arb=bits&1;level=bits&2?1:3;haptic_test=bits&4?1:2;
  haptic_active=bits&8;haptic_fifo_status_active=bits&16;calls=0;
  assert(waffle_haptic_fifo_status_bus_read(&c,0x7f0,0x70,&v)==(bits==31));assert(calls==(bits==31));
 }
 for(unsigned p=0;p<3;p++)for(unsigned a=0;a<256;a++){
  calls=0;uint16_t id=0x7f0+p;
  assert(waffle_haptic_fifo_status_bus_read(&c,id,a,&v)==waffle_haptic_fifo_status_read_allowed(id,a));
 }
 c.peripheral[0].found=false;calls=0;assert(!waffle_haptic_fifo_status_bus_read(&c,0x7f0,9,&v)&&!calls);
 puts("PASS actual FIFO status adapter: five isolated mode gates, exact read allowlist, missing channel refusal; mock SPMI only.");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
