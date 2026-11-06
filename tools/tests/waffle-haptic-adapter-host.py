#!/usr/bin/env python3
"""Actual torch observer adapter gates PMIC reads to Waffle mode1."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text();code=s[s.index('struct waffle_haptic_bus_context'):s.index('/* Dedicated opt-in transaction;')]
h=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
#include "waffle_haptic_readonly.h"
struct peripheral {uint16_t id;bool found;};static bool waffle_arb;static unsigned level,calls,haptic_test;
static const char *spmi_read(const struct peripheral *p,uint8_t reg,uint8_t *v,uint32_t count){assert(count==1&&waffle_haptic_read_allowed(p->id,reg));calls++;if(!p->found)return "missing";*v=reg==1&&p->id!=0x7f2?4:0;return NULL;}
'''
t=r'''
int main(void){struct waffle_haptic_bus_context c={.peripheral={{0x7f0,true},{0x7f1,true},{0x7f2,true}}};struct waffle_haptic_read_io io={&c,waffle_haptic_bus_read};struct waffle_haptic_snapshot state;for(unsigned platform=0;platform<2;platform++)for(level=0;level<4;level++){waffle_arb=platform;calls=0;assert(waffle_haptic_capture(&io,&state)==(platform&&level==1));assert(calls==(platform&&level==1?31u:0u));}waffle_arb=true;level=1;calls=0;uint8_t v;assert(!waffle_haptic_bus_read(&c,0x7f0,0x49,&v)&&!calls);assert(!waffle_haptic_bus_read(&c,0x7f1,0x20,&v)&&!calls);assert(!waffle_haptic_bus_read(&c,0x1ee,0x46,&v)&&!calls);c.peripheral[1].found=false;assert(!waffle_haptic_capture(&io,&state)&&!state.complete);puts("PASS actual haptic observer adapter: Waffle readonly mode1 only, flash/FIFO/write-path addresses refused, missing channel incomplete; host only");}
'''
with tempfile.TemporaryDirectory() as tdir:
 p=Path(tdir);(p/'test.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
