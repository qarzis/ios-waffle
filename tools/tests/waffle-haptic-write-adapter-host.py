#!/usr/bin/env python3
"""Compile actual H04 SPMI writer and verify gate/owner/transaction boundaries."""
from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text()
body=s[s.index('static bool\nwaffle_haptic_bus_write'):s.index('static void\nwaffle_haptic_quiesce')]
quiesce=s[s.index('static void\nwaffle_haptic_quiesce'):s.index('static uint64_t\nwaffle_haptic_now_us')]
assert 'waffle_haptic_quiesce();' in s[s.index('macan_torch_quiesce(void)'):]
program=r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "waffle_haptic_pulse.h"
typedef unsigned long vm_offset_t;
struct peripheral {uint16_t id,channel;bool found,writable;vm_offset_t write;};
struct waffle_haptic_bus_context {struct peripheral peripheral[3];};
static bool waffle_arb,haptic_active,locked,bad_owner,bad_map,bad_read,denied;
static uint32_t level,haptic_test,arb_map=0x1000,arb_cnfg=0x2000;
static unsigned writes;static uint8_t byte;
#define ARB_CHANNEL(n) (4*(n))
#define ARB_OWNER(n) (4*(n))
#define ARB_SYSTEM 0
#define CHANNEL_WDATA0 0x10
#define CHANNEL_COMMAND 0
#define COMMAND_WRITE 0
static uint32_t arb_ppid(uint32_t v){return (v>>8)&0xfff;}
static void lock(void){assert(!locked);locked=true;}
static void unlock(void){assert(locked);locked=false;}
static uint32_t rd(vm_offset_t a){assert(locked);if(a>=0x2000)return bad_owner?3:0;return (bad_map?0x7f2:0x7f0)<<8;}
static void wr(vm_offset_t a,uint32_t v){assert(locked);writes++;if((a&255)==0x10)byte=v;}
static const char *wait_done(vm_offset_t a){assert(locked&&a==0x300);return denied?"denied":NULL;}
static const char *spmi_read(const struct peripheral *p,uint8_t a,uint8_t *v,uint32_t n){assert(!locked&&p->id==0x7f0&&n==1);(void)a;*v=bad_read?byte^1:byte;return NULL;}
'''+body+r'''
static bool leaving;static struct waffle_haptic_bus_context haptic_pulse_context;
static int say(const char *format,...){(void)format;return 0;}
'''+quiesce+r'''
int main(void){struct waffle_haptic_bus_context c={.peripheral={{0x7f0,1,true,true,0x300},{0x7f1,2,true,true,0x400},{0x7f2,3,true,false,0}}};
 for(unsigned mask=0;mask<16;mask++){waffle_arb=mask&1;level=mask&2?1:3;haptic_test=mask&4?1:0;haptic_active=mask&8;writes=0;bool ok=waffle_haptic_bus_write(&c,0x7f0,0x4c,1);assert(ok==(mask==15));assert(writes==(mask==15?2u:0u));}
 waffle_arb=haptic_active=true;level=haptic_test=1;
 writes=0;assert(!waffle_haptic_bus_write(&c,0x7f2,0x46,0)&&!writes);assert(!waffle_haptic_bus_write(&c,0x7f0,0x48,0)&&!writes);assert(!waffle_haptic_bus_write(&c,0x1ee,0x46,0)&&!writes);
 bad_owner=true;assert(!waffle_haptic_bus_write(&c,0x7f0,0x4c,1)&&!writes);bad_owner=false;bad_map=true;assert(!waffle_haptic_bus_write(&c,0x7f0,0x4c,1)&&!writes);bad_map=false;
 denied=true;assert(!waffle_haptic_bus_write(&c,0x7f0,0x4c,1));denied=false;bad_read=true;assert(!waffle_haptic_bus_write(&c,0x7f0,0x4c,1));assert(!locked);
 bad_read=false;writes=0;level=3;haptic_test=2;assert(waffle_haptic_bus_write(&c,0x7f0,0x4c,1)&&writes==2);level=1;haptic_test=1;
 writes=0;haptic_pulse_context=c;waffle_haptic_quiesce();assert(leaving&&!haptic_active&&writes==4);writes=0;waffle_haptic_quiesce();assert(!writes);
 haptic_active=true;haptic_test=2;leaving=false;waffle_haptic_quiesce();assert(leaving&&!haptic_active&&writes==4);
 puts("PASS actual haptic writer: four opt-in gates, CFG/PTN allowlist, firmware HBST/flash refused, owner+PPID checked under bus lock, denied/readback mismatch reject. Host MMIO only.");}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(program);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
