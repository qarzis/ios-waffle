#!/usr/bin/env python3
"""Actual OOB probe: deny GPU reads without powered clocks; always release."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool gpu_power_probe('):s.index('/* Pinned OnePlus qcom_scm-smc.c')]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
#define GMU 0x1000u
#define CC 0x2000u
#define GPU 0x3000u
struct waffle_gmu_plan {int placeholder;};
struct gen7_live_probe;
static bool gpu_gen7_live_start(struct gen7_live_probe *live,vm_offset_t gpu,vm_offset_t gmu,vm_offset_t hfi,struct waffle_gmu_plan *plan,unsigned probe) {(void)live;(void)gpu;(void)gmu;(void)hfi;(void)plan;(void)probe;return true;}
static bool gpu_cp_probe(vm_offset_t gpu,struct waffle_gmu_plan *plan,unsigned probe) {(void)gpu;(void)plan;(void)probe;return true;}
static bool gpu_firmware_probe(vm_offset_t gpu,struct waffle_gmu_plan *plan) {(void)gpu;(void)plan;return true;}
static bool gpu_gen7_configuration_probe(vm_offset_t gpu,vm_offset_t gmu,struct waffle_gmu_plan *plan,unsigned probe) {(void)gpu;(void)gmu;(void)plan;(void)probe;return true;}
static unsigned status,gdsc,acknowledged,mapfail,mapped,reads,released,requested;
static uint32_t rd(vm_offset_t base,unsigned offset) {
    if (base==GMU) {assert(offset==WAFFLE_GMU_REG(0x1f8d0));return status;}
    if (base==CC) {assert(offset==WAFFLE_GPU_GX_GDSCR);return gdsc;}
    assert(base==GPU && !(status&3) && (gdsc&(1u<<31)));
    assert(offset==0x210*4 || offset==0x825*4 || offset==0x808*4);reads++;return 0;
}
static void wr(vm_offset_t base,unsigned offset,uint32_t value) {
    assert(base==GMU);
    if (offset==WAFFLE_GMU_REG(0x1f994)) {
        if (value==(1u<<30)) requested++;
        else {assert(value==(1u<<31));released++;}
    } else {assert(offset==WAFFLE_GMU_REG(0x1f991) && value==(1u<<31));}
}
static bool wait_for(vm_offset_t base,unsigned offset,uint32_t mask,uint32_t value,unsigned loops) {
    assert(base==GMU && offset==WAFFLE_GMU_REG(0x1f992));
    assert(mask==(1u<<31) && value==mask && loops==1000);return acknowledged;
}
static vm_offset_t ml_io_map(uintptr_t base,size_t size) {
    assert(base==WAFFLE_GPU_BASE && size==WAFFLE_GPU_SIZE);mapped++;return mapfail ? 0 : GPU;
}
static void say(const char *fmt,...) {(void)fmt;}
'''
tests=r'''
static void test(unsigned power,unsigned clock,unsigned ack,unsigned fail,bool expected) {
    status=power;gdsc=clock;acknowledged=ack;mapfail=fail;
    mapped=reads=released=requested=0;
    assert(gpu_power_probe(GMU,CC,NULL,19,0,NULL)==expected);
    assert(requested==1 && released==1);
    if (expected) assert(mapped==1 && reads==3);
    else assert(!reads);
    if (!ack || power || !clock) assert(!mapped);
}
int main(void) {
    test(0,1u<<31,1,0,true);
    test(3,0,0,0,false);
    test(0,1u<<31,0,0,false);
    test(2,1u<<31,1,0,false);
    test(1,1u<<31,1,0,false);
    test(0,0,1,0,false);
    test(0,1u<<31,1,1,false);
    puts("GX power/clock/ACK denial and OOB release checks passed");return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
