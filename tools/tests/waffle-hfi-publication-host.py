#!/usr/bin/env python3
"""Compile actual HFI publication/exchange; reject callbacks before the kick."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static void hfi_publish_notify('):s.index('static bool hfi_exchange(vm_offset_t')]
code=code.replace('__asm__ volatile("dsb sy" ::: "memory");','barrier();')
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_hfi.h"
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
#define NSEC_PER_USEC 1000
struct waffle_gmu_plan {bool enabled,raw_stage_pause;};
static uint32_t table[4096];
static unsigned phases,kicks,barriers,diagnostics,samples,holds;
static bool is_raw,stage_only;
static uint32_t stage_write;
static void outside_publication(void) {if(stage_only)assert(table[17]==stage_write && !kicks);else assert(!table[17] || kicks==1);}
static void hfi_raw_checkpoint(const struct waffle_gmu_plan *plan,const char *name) {
 outside_publication();
 assert(plan && plan->enabled && name[0]==(char)('0'+phases) && name[1]=='-');
 if(phases<4) assert(table[17]==0 && !kicks);
 else assert(table[17]==4 && kicks==1);
 if(phases==3) assert(table[848/4]==((34u<<20)|(3u<<8)|131u));
 ++phases;
}
static void hfi_smmu_diagnostic(const struct waffle_gmu_plan *plan) {
 outside_publication();(void)plan;++samples;
}
static void hfi_raw_diagnostic(uintptr_t gmu,uintptr_t alias,unsigned *budget) {
 outside_publication();assert(gmu==1 && alias==(uintptr_t)table && *budget==16);++diagnostics;
}
static uint32_t rd(uintptr_t gmu,unsigned offset) {
 (void)gmu;(void)offset;assert(0 && "unexpected diagnostic MMIO read");return 0;
}
static void wr(uintptr_t gmu,unsigned offset,uint32_t value) {
 assert(gmu==1 && offset==WAFFLE_GMU_REG(0x1f994) && value==1);
 assert(table[17]==4 && barriers==2 && !kicks);
 assert(phases==(is_raw?4u:0u));++kicks;
}
static bool hfi_raw_fault_packet(const uint32_t *p,unsigned n,const char *queue) {
 outside_publication();(void)p;(void)n;(void)queue;return false;
}
static void stop_unsafe(const char *why) {(void)why;assert(0);}
static void say(const char *fmt,...) {outside_publication();(void)fmt;}
static void barrier(void) {
 if(stage_only){assert(table[17]==stage_write && !kicks);++barriers;return;}
 if(!barriers) assert(!table[17] && !kicks);
 if(barriers==1) assert(table[17]==4 && !kicks);
 ++barriers;
}
static void delay_for_interval(unsigned t,unsigned unit) {
 outside_publication();assert(unit==NSEC_PER_USEC);
 if(t==5000000){assert(is_raw && diagnostics==1 && samples==1);
 assert(phases==(holds?5u:4u) && kicks==holds);++holds;}
 else assert(t==100);
}
'''
tests=r'''
static void run(bool raw,bool valid_ack,bool zero_ack,bool pause,bool general) {
 memset(table,0,sizeof(table));
 phases=kicks=barriers=diagnostics=samples=holds=0;is_raw=raw;
 struct waffle_gmu_plan plan={.enabled=true,.raw_stage_pause=pause};
 table[6]=table[18]=1;table[9]=table[21]=1024;
 uint32_t packet[3];assert(waffle_hfi_cp_thread_packet(packet,3,34)==3);
 if(!raw) packet[0]=(packet[0]&~255u)|100u;
 uint32_t *msg=table+(848+4096)/4;
 msg[0]=(7u<<20)|(1u<<16)|(3u<<8)|(packet[0]&255u);
 msg[1]=packet[0];msg[2]=valid_ack?0:0xffffffff;
 table[29]=4;
 assert(hfi_exchange_watch(1,(uintptr_t)table,packet,3,general?"GENERAL_IB":"test",zero_ack,&plan)==valid_ack);
 assert(phases==(raw?6u:0u) && kicks==1 && diagnostics==(raw?2u:0u));
 assert(holds==((raw && pause)?2u:0u));
 assert(samples==(raw?2u:0u) && barriers==4 && table[28]==4);
}
int main(void) {
 for(unsigned raw=0;raw<2;++raw)
  for(unsigned valid=0;valid<2;++valid)
   for(unsigned zero=0;zero<2;++zero) for(unsigned pause=0;pause<2;++pause)
    for(unsigned general=0;general<2;++general)run(raw,valid,zero,pause,general);
 /* Disabled and full command queues must never publish or ring the doorbell. */
 for(unsigned full=0;full<2;++full) {
  memset(table,0,sizeof(table));phases=kicks=barriers=0;is_raw=false;
  table[6]=full;table[9]=1024;table[16]=4;
  uint32_t packet[3]={(34u<<20)|(3u<<8)|100u,0,0};
  assert(!hfi_exchange_watch(1,(uintptr_t)table,packet,3,"test",false,NULL));
  assert(!kicks && !barriers && !table[17]);
 }
 /* The real RAW staging control restores packet+padding, even on wrap.
  * All table fields and the complete ring remain byte-identical afterward. */
 stage_only=true;
 for(unsigned wrapped=0;wrapped<2;wrapped++) {
  memset(table,0,sizeof(table));phases=kicks=barriers=diagnostics=samples=0;
  stage_write=wrapped?1020:0;table[6]=1;table[9]=1024;table[16]=table[17]=stage_write;
  uint32_t *ring=table+848/4;
  for(unsigned i=0;i<1024;i++)ring[i]=0xabc00000+i;
  uint32_t before[4096];memcpy(before,table,sizeof(before));
  uint32_t packet[11];assert(waffle_hfi_cp_init_packet(packet,11,34,0x1ff8000470000ULL)==11);
  assert(hfi_raw_stage_control(1,(uintptr_t)table,packet,11,NULL));
  assert(!memcmp(before,table,sizeof(before)) && !kicks && barriers==2 && diagnostics==1 && samples==1);
  assert(!hfi_raw_stage_control(1,(uintptr_t)table,packet,10,NULL));
  table[6]=0;barriers=0;
  assert(!hfi_raw_stage_control(1,(uintptr_t)table,packet,11,NULL));
  assert(!kicks && !barriers);
  table[6]=1;table[16]=(stage_write+4)%1024;barriers=0;
  assert(!hfi_raw_stage_control(1,(uintptr_t)table,packet,11,NULL));
  assert(!kicks && !barriers && table[17]==stage_write);
 }
 puts("Actual HFI exchange: consecutive packet/index/barriers/doorbell; RAW/query ACK handling; disabled/full queues passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(harness+code+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
