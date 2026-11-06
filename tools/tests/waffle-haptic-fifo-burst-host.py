#!/usr/bin/env python3
"""Compile actual FIFO adapter: four-byte command, owner under lock, no retry."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text()
body=s[s.index('static bool\nwaffle_haptic_fifo_buffer_bus_read'):s.index('static bool\nwaffle_haptic_fifo_status_bus_read')]
code=r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "waffle_haptic_fifo_buffer.h"
#include "waffle_haptic_fifo_play.h"
typedef unsigned long vm_offset_t;
struct peripheral {uint16_t id,channel;bool found,writable;vm_offset_t write;};
struct waffle_haptic_bus_context {struct peripheral peripheral[3];};
static bool waffle_arb,haptic_active,haptic_fifo_buffer_active,locked,bad_owner,bad_map,denied;
static bool haptic_fifo_play_active;
static unsigned level,haptic_test,writes,waits,reads;static uint32_t data,command;
static vm_offset_t arb_map=0x1000,arb_cnfg=0x2000;
#define ARB_CHANNEL(n) (4*(n))
#define ARB_OWNER(n) (4*(n))
#define ARB_SYSTEM 0
#define CHANNEL_WDATA0 0x10
#define CHANNEL_COMMAND 0
#define COMMAND_WRITE 0
static unsigned arb_ppid(uint32_t v){return (v>>8)&0xfff;}
static void lock(void){assert(!locked);locked=true;}
static void unlock(void){assert(locked);locked=false;}
static uint32_t rd(vm_offset_t a){assert(locked);return a>=arb_cnfg?(bad_owner?3:0):(bad_map?0x7f2:0x7f1)<<8;}
static void wr(vm_offset_t a,uint32_t v){assert(locked);writes++;if(a==0x410)data=v;else {assert(a==0x400);command=v;}}
static const char *wait_done(vm_offset_t a){assert(locked&&a==0x400);waits++;return denied?"denied":NULL;}
static const char *spmi_read(const struct peripheral *p,uint8_t a,uint8_t *v,unsigned n){assert(n==1&&p->found&&waffle_haptic_fifo_buffer_read_allowed(p->id,a));reads++;*v=0;return NULL;}
'''+body+r'''
int main(void){
 struct waffle_haptic_bus_context c={{{0x7f0,1,true,true,0x300},{0x7f1,2,true,true,0x400},{0x7f2,3,true,false,0}}};
 const uint8_t bytes[]={0x11,0x22,0x33,0x44};uint8_t v;
 for(unsigned bits=0;bits<32;bits++){
  waffle_arb=bits&1;level=bits&2?1:3;haptic_test=bits&4?1:2;haptic_active=bits&8;haptic_fifo_buffer_active=bits&16;
  writes=waits=reads=0;assert(waffle_haptic_fifo_bus_write4(&c,0x7f1,0x20,bytes)==(bits==31));assert(writes==(bits==31?2u:0u)&&waits==(bits==31));
  assert(waffle_haptic_fifo_buffer_bus_read(&c,0x7f0,0x4e,&v)==(bits==31));assert(reads==(bits==31));
 }
 assert(data==0x44332211&&command==0x203);
 haptic_fifo_play_active=true;writes=waits=0;assert(!waffle_haptic_fifo_bus_write4(&c,0x7f1,0x20,bytes)&&!writes&&!waits);haptic_fifo_play_active=false;
 for(unsigned p=0;p<3;p++)for(unsigned a=0;a<256;a++){
  writes=waits=0;assert(waffle_haptic_fifo_bus_write4(&c,0x7f0+p,a,bytes)==(p==1&&a==0x20));
 }
 writes=waits=0;bad_owner=true;assert(!waffle_haptic_fifo_bus_write4(&c,0x7f1,0x20,bytes)&&!writes&&!waits);bad_owner=false;
 bad_map=true;assert(!waffle_haptic_fifo_bus_write4(&c,0x7f1,0x20,bytes)&&!writes&&!waits);bad_map=false;
 denied=true;assert(!waffle_haptic_fifo_bus_write4(&c,0x7f1,0x20,bytes)&&writes==2&&waits==1);assert(!locked);
 puts("PASS actual FIFO adapter: five opt-in gates, little-endian4B/length3, owner under lock, exact data port, no data readback/retry; host MMIO only.");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
