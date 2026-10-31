#!/usr/bin/env python3
"""Actual CP probe: packets, refuse enable on failed setup, retain buffers on timeout."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static uint32_t packet7('):s.index('static bool gpu_power_probe(')]
code=code.replace('__asm__ volatile("dc cvac, %0"::"r"(p):"memory");','cache_clean(p);').replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
typedef uintptr_t vm_offset_t;
#define WAFFLE_GPU_RING_ADDRESS 0x80050000u
#define WAFFLE_GPU_SCRATCH_ADDRESS 0x80060000u
#define WAFFLE_GPU_PWRUP_ADDRESS 0x80070000u
#define WAFFLE_GPU_SQE_ADDRESS 0x80010000u
#define WAFFLE_GPU_AQE_ADDRESS 0x80030000u
#define PAGE_SIZE 16384
#define VM_WIMG_WCOMB 6
#define NSEC_PER_USEC 1000
struct waffle_gmu_region {vm_offset_t memory;};
struct waffle_gmu_plan {struct waffle_gmu_region ring,scratch,power;};
static uint32_t regs[0xc00],ringdata[8192],scratchdata[4096],powerdata[4096];
static unsigned mode,enabled,halted,unmapped,refuse,waits;
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,uint32_t addr,unsigned size) {
    (void)size;
    if(addr==WAFFLE_GPU_RING_ADDRESS)return &p->ring;
    if(addr==WAFFLE_GPU_SCRATCH_ADDRESS)return &p->scratch;
    assert(addr==WAFFLE_GPU_PWRUP_ADDRESS);return &p->power;
}
static uintptr_t kvtophys(uintptr_t va) {return va;}
static vm_offset_t ml_io_map_unmappable(uintptr_t pa,size_t size,unsigned attr) {
    assert(pa==(uintptr_t)scratchdata && size==PAGE_SIZE && attr==6);return pa;
}
static void ml_io_unmap(uintptr_t va,size_t size) {assert(va==(uintptr_t)scratchdata && size==PAGE_SIZE);unmapped++;}
static void cache_clean(uintptr_t va) {assert(va>=(uintptr_t)ringdata && va<(uintptr_t)ringdata+40);}
static void barrier(void) {}
static void delay_for_interval(unsigned t,unsigned unit) {assert(t==100 && unit==1000);waits++;}
static void say(const char *fmt,...) {(void)fmt;}
static void stop_unsafe(const char *why) {(void)why;assert(!"unsafe CP setup");}
static uint32_t rd(uintptr_t gpu,unsigned off) {assert(gpu==(uintptr_t)regs && off<sizeof(regs));return regs[off/4];}
static void wr(uintptr_t gpu,unsigned off,uint32_t value) {
    assert(gpu==(uintptr_t)regs && off<sizeof(regs));
    if(off==0x844*4 && refuse)return;
    if(off==0x808*4 && value==1) {
        assert(regs[0x830]==WAFFLE_GPU_SQE_ADDRESS && regs[0xb70]==WAFFLE_GPU_AQE_ADDRESS);
        assert(regs[0x800]==WAFFLE_GPU_RING_ADDRESS && regs[0x804]==WAFFLE_GPU_SCRATCH_ADDRESS);
        enabled++;
    }
    if(off==0x808*4 && value==3) {assert(enabled);halted++;}
    regs[off/4]=value;
    if(off==0x807*4 && value==10 && mode) {
        assert(enabled);scratchdata[0]=10;regs[0x806]=mode==2?9:10;
    }
}
'''
tests=r'''
static struct waffle_gmu_plan plan;
static void reset(void) {
    memset(regs,0,sizeof(regs));memset(ringdata,0,sizeof(ringdata));memset(scratchdata,0,sizeof(scratchdata));
    plan.ring.memory=(uintptr_t)ringdata;plan.scratch.memory=(uintptr_t)scratchdata;plan.power.memory=(uintptr_t)powerdata;
    enabled=halted=unmapped=refuse=waits=mode=0;
}
int main(void) {
    reset();assert(gpu_cp_probe((uintptr_t)regs,&plan,22));
    assert(!enabled && !halted && !waits && unmapped==1);
    for(unsigned i=0;i<0xc00;++i)assert(regs[i]==0);
    reset();refuse=1;assert(!gpu_cp_probe((uintptr_t)regs,&plan,22));
    assert(!enabled && !halted && unmapped==1);
    for(unsigned i=0;i<0xc00;++i)assert(regs[i]==0);
    reset();assert(gpu_cp_probe((uintptr_t)regs,&plan,23));
    assert(enabled==1 && halted==1 && unmapped==1 && waits==1);
    assert(regs[0x807]==0 && regs[0x806]==0 && scratchdata[0]==0);
    reset();regs[0x807]=1;assert(!gpu_cp_probe((uintptr_t)regs,&plan,23));
    assert(!enabled && !unmapped);
    reset();mode=1;assert(gpu_cp_probe((uintptr_t)regs,&plan,21));
    assert(enabled==1 && halted==1 && unmapped==1);
    assert(ringdata[0]==0x70970001 && ringdata[2]==0x70c80007);
    assert(ringdata[3]==0x94b && ringdata[7]==WAFFLE_GPU_PWRUP_ADDRESS && ringdata[9]==(1u<<31));
    reset();refuse=1;assert(!gpu_cp_probe((uintptr_t)regs,&plan,21));assert(!enabled && unmapped==1);
    reset();assert(!gpu_cp_probe((uintptr_t)regs,&plan,21));assert(enabled==1 && halted==1 && waits==10000);
    reset();mode=2;assert(!gpu_cp_probe((uintptr_t)regs,&plan,21));assert(enabled==1 && halted==1);
    reset();regs[0x808]=1;assert(!gpu_cp_probe((uintptr_t)regs,&plan,21));assert(!enabled && !unmapped);
    puts("CP packet/setup-denial/timeout/DMA-register-consistency checks passed");return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
