#!/usr/bin/env python3
"""Actual firmware base transaction: keep CP halted, restore after refusals."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool gpu_firmware_probe('):s.index('static uint32_t packet7(')]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
typedef uintptr_t vm_offset_t;
#define WAFFLE_GPU_SQE_ADDRESS 0x80010000u
#define WAFFLE_GPU_AQE_ADDRESS 0x80030000u
struct waffle_gmu_region {bool gpu_only;};
struct waffle_gmu_plan {unsigned missing;struct waffle_gmu_region sqe,aqe;};
static uint32_t regs[0xc00];
static unsigned writes,basewrites,refuse_base;
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,uint32_t addr,unsigned size) {
    assert(size==4);if(p->missing)return NULL;
    assert(addr==WAFFLE_GPU_SQE_ADDRESS || addr==WAFFLE_GPU_AQE_ADDRESS);
    return addr==WAFFLE_GPU_SQE_ADDRESS?&p->sqe:&p->aqe;
}
static uint32_t rd(vm_offset_t base,unsigned off) {assert(base==(uintptr_t)regs && off<sizeof(regs));return regs[off/4];}
static void wr(vm_offset_t base,unsigned off,uint32_t value) {
    assert(base==(uintptr_t)regs && off<sizeof(regs));writes++;
    assert(off!=0x808*4); /* No enable/halt writes during register-only test. */
    assert(regs[0x808]==0);basewrites++;
    if(off==0x830*4 && value==WAFFLE_GPU_SQE_ADDRESS && refuse_base) {refuse_base=0;return;}
    regs[off/4]=value;
}
static void say(const char *fmt,...) {(void)fmt;}
static void stop_unsafe(const char *why) {(void)why;assert(!"unexpected CP enable");}
'''
tests=r'''
static struct waffle_gmu_plan plan;
static void reset(void) {
    memset(regs,0,sizeof(regs));memset(&plan,0,sizeof(plan));
    plan.sqe.gpu_only=plan.aqe.gpu_only=true;
    writes=basewrites=refuse_base=0;
}
static void restored(void) {for(unsigned i=0;i<sizeof(regs)/4;i++)assert(regs[i]==0);}
int main(void) {
    reset();plan.missing=1;assert(!gpu_firmware_probe((uintptr_t)regs,&plan) && !writes);
    reset();regs[0x808]=1;assert(!gpu_firmware_probe((uintptr_t)regs,&plan) && !writes);
    reset();regs[0x808]=2;assert(!gpu_firmware_probe((uintptr_t)regs,&plan) && !writes);
    reset();assert(gpu_firmware_probe((uintptr_t)regs,&plan));assert(basewrites==8);restored();
    reset();refuse_base=1;assert(!gpu_firmware_probe((uintptr_t)regs,&plan));restored();
    puts("Ucode CP-control-write denial/base-refusal/restore checks passed");return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
