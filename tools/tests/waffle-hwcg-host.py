#!/usr/bin/env python3
"""Actual Gen7 HWCG on/off sequence and rollback checks against native source."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
VENDOR=ROOT/'work/waffle/gpu/vendor'
native=(VENDOR/'adreno_gen7.c').read_text()
native=re.search(r'static void gen7_hwcg_set\(.*?\n\}',native,re.S)[0]
table=re.search(r'static const [^;]+\bgen7_2_0_ao_hwcg_regs\[\]\s*=\s*\{.*?\n\};',
                (VENDOR/'adreno-gpulist.h').read_text(),re.S)[0]
harness=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_gen7_hwcg.h"
#include "gen7_reg.h"
#define BIT(n) (1u<<(n))
#define RBBM_CLOCK_CNTL_ON 0x8aa8aa82u
typedef uint32_t u32;
struct event { uint32_t index,value; } events[64],native_events[64];
static uint32_t values[0x27c00],initial[0x27c00];
static unsigned event_count,polls,ack_after,drop_ao,ao_dropped,bad_restore,bad_global,load_reads;
static unsigned mismatch_count;
static bool restoring,gx_off;
static uint32_t read_reg(void *context,uint32_t index) {
 (void)context;assert(waffle_gen7_index_allowed(index));
 assert(!gx_off || index>=0x1a000);
 if (index==GEN7_RBBM_CGC_P2S_STATUS) { polls++;return polls>=ack_after?1:0; }
 if (index==GEN7_RBBM_CGC_GLOBAL_LOAD_CMD) { load_reads++;return 0xdeafbead; }
 return values[index];
}
static void write_reg(void *context,uint32_t index,uint32_t value) {
 (void)context;assert(event_count<64 && waffle_gen7_index_allowed(index));
 assert(!gx_off || index>=0x1a000);
 assert(index!=0x808 && index!=0x806 && index!=0x807);
 events[event_count++]=(struct event){index,value};
 for (unsigned i=0;i<3;i++) if (index==waffle_gen7_ao_hwcg[i].index) {
  if (drop_ao==i+1 && !ao_dropped) { ao_dropped=1;return; }
  if (bad_restore && i==0 && restoring && value==initial[index]) return;
 }
 if (index==GEN7_RBBM_CGC_GLOBAL_LOAD_CMD && !value) {
  restoring=true;
 }
 if (bad_global && restoring && index==GEN7_RBBM_CLOCK_CNTL_GLOBAL && !value) return;
 if (index!=GEN7_RBBM_CGC_P2S_TRIG_CMD) values[index]=value;
}
static void delay_us(void *context,unsigned usec) {
 (void)context;assert(usec==1 && event_count<64);
 events[event_count++]=(struct event){0xffffffff,usec};
}
static void mismatch(void *context,uint32_t index,uint32_t expected,uint32_t actual,bool undo) {
 (void)context;(void)undo;assert(waffle_gen7_index_allowed(index) && expected!=actual);mismatch_count++;
}
static void reset(unsigned ack) {
 memset(values,0,sizeof(values));event_count=polls=drop_ao=ao_dropped=bad_restore=bad_global=mismatch_count=load_reads=0;
 values[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=1;ack_after=ack;restoring=gx_off=false;
 memcpy(initial,values,sizeof(initial));
}
struct kgsl_device { void *dev; } native_device;
struct kgsl_regmap_list { u32 offset,val; };
struct adreno_gen7_core { const struct kgsl_regmap_list *ao_hwcg,*hwcg;int ao_hwcg_count,hwcg_count; };
struct adreno_device { bool hwcg_enabled; };
#define KGSL_DEVICE(a) (&native_device)
static void kgsl_regwrite(struct kgsl_device *d,u32 reg,u32 val) { (void)d;write_reg(0,reg,val); }
static void gmu_core_regwrite(struct kgsl_device *d,u32 reg,u32 val) { (void)d;write_reg(0,reg,val); }
static void kgsl_regread(struct kgsl_device *d,u32 reg,u32 *val) { (void)d;*val=read_reg(0,reg); }
static void udelay(unsigned usec) { delay_us(0,usec); }
#define dev_err(...) ((void)0)
static void kgsl_device_snapshot(struct kgsl_device *d,void *a,void *b,bool c) { (void)d;(void)a;(void)b;(void)c; }
'''
harness+=table+'''
static const struct adreno_gen7_core core={gen7_2_0_ao_hwcg_regs,0,3,0};
static const struct adreno_gen7_core *to_gen7_core(struct adreno_device *a) { (void)a;return &core; }
'''+native
tests=r'''
static void success_or_timeout(unsigned ack) {
 struct adreno_device adreno={true};
 reset(ack);gen7_hwcg_set(&adreno,true);gen7_hwcg_set(&adreno,false);
 unsigned native_count=event_count;memcpy(native_events,events,sizeof(events));
 reset(ack);
 struct waffle_gen7_io io={NULL,read_reg,write_reg,mismatch,NULL};
 uint32_t status,index;
 assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==(ack<=3?0:-2));
 assert(polls==(ack<=3?ack:3));
 assert(event_count==native_count+4);
 assert(!memcmp(events,native_events,native_count*sizeof(events[0])));
 assert(!memcmp(values,initial,sizeof(values)));
 assert(!load_reads);
 assert(index==(ack<=3?0:GEN7_RBBM_CGC_P2S_STATUS));
}
int main(void) {
 success_or_timeout(1);success_or_timeout(3);success_or_timeout(4);
 struct waffle_gen7_io io={NULL,read_reg,write_reg,mismatch,NULL};
 uint32_t status,index;
 for (unsigned i=1;i<=3;i++) {
  reset(1);drop_ao=i;
  assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==-2);
  assert(!memcmp(values,initial,sizeof(values)) && mismatch_count==1 && !polls);
 }
 reset(1);bad_restore=1;
 values[waffle_gen7_ao_hwcg[0].index]=initial[waffle_gen7_ao_hwcg[0].index]=7;
 assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==-3);
 reset(1);values[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=initial[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=0;
 assert(!waffle_gen7_hwcg_probe(&io,delay_us,&status,&index) && !load_reads);
 assert(!memcmp(values,initial,sizeof(values)));
 reset(1);values[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=initial[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=0;bad_global=1;
 assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==-3);
 reset(1);values[0x808]=1;
 assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==-1 && !event_count);
 reset(1);values[GEN7_RBBM_CLOCK_CNTL_GLOBAL]=7;
 assert(waffle_gen7_hwcg_probe(&io,delay_us,&status,&index)==-1 && !event_count);
 /* Leave clocks programmed through command submission, restore only AO after
  * GX collapse. The harness aborts on ANY GX access once gx_off is set. */
 reset(1);
 struct waffle_gen7_hwcg_state live={0};
 struct waffle_gen7_config_state config={.phase=WAFFLE_GEN7_READY};
 assert(!waffle_gen7_hwcg_begin(&io,&live,delay_us,&status,&index));
 assert(live.phase==WAFFLE_GEN7_HWCG_ACTIVE && live.loaded);
 for (unsigned i=0;i<3;i++) assert(values[waffle_gen7_ao_hwcg[i].index]==waffle_gen7_ao_hwcg[i].value);
 assert(!values[GEN7_RBBM_CLOCK_CNTL_GLOBAL]);
 assert(waffle_gen7_config_submitting(&config));
 unsigned old_events=event_count,old_polls=polls;
 assert(waffle_gen7_hwcg_finish(&io,&live,&config,&index)==-3);
 assert(event_count==old_events && polls==old_polls && live.phase==WAFFLE_GEN7_HWCG_ACTIVE);
 assert(waffle_gen7_config_stopped(&config,63));gx_off=true;
 assert(!waffle_gen7_hwcg_finish(&io,&live,&config,&index));
 assert(live.phase==WAFFLE_GEN7_HWCG_RELEASED && event_count==old_events+3);
 for (unsigned i=0;i<3;i++) assert(values[waffle_gen7_ao_hwcg[i].index]==initial[waffle_gen7_ao_hwcg[i].index]);
 assert(!load_reads && polls==old_polls);
 old_events=event_count;
 assert(waffle_gen7_hwcg_finish(&io,&live,&config,&index)==-3 && event_count==old_events);
 /* Native AO restoration failure after collapse retains the snapshot. */
 reset(1);live=(struct waffle_gen7_hwcg_state){0};config.phase=WAFFLE_GEN7_READY;
 values[waffle_gen7_ao_hwcg[0].index]=initial[waffle_gen7_ao_hwcg[0].index]=7;
 assert(!waffle_gen7_hwcg_begin(&io,&live,delay_us,&status,&index));
 assert(waffle_gen7_config_submitting(&config));assert(waffle_gen7_config_stopped(&config,63));
 gx_off=restoring=true;bad_restore=1;
 assert(waffle_gen7_hwcg_finish(&io,&live,&config,&index)==-3);
 assert(live.phase==WAFFLE_GEN7_HWCG_RETAINED && mismatch_count==1);
 old_events=event_count;
 assert(waffle_gen7_hwcg_finish(&io,&live,&config,&index)==-3 && event_count==old_events);
 puts("HWCG native on/off trace, live clock lifetime, AO-only collapse restore, timeout, retention and zero LOAD reads passed");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),'-I',str(VENDOR),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
