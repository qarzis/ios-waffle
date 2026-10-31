#!/usr/bin/env python3
"""Actual RAW debug-queue handling: packet bounds, firmware errors and CM3 IRQ."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool hfi_raw_fault_packet('):s.index('/* Read-only property query,')]
code=code.replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#include "waffle_hfi.h"
typedef uintptr_t vm_offset_t;
static uint32_t memory[4096],irq;
static unsigned barriers,logs;
static jmp_buf stopped;
static uint32_t rd(vm_offset_t base,unsigned offset) {
 assert(base==1 && offset==WAFFLE_GMU_REG(0x1f992));return irq;
}
static void barrier(void) {++barriers;}
static void say(const char *fmt,...) {(void)fmt;++logs;}
static void stop_unsafe(const char *reason) {(void)reason;longjmp(stopped,1);}
'''
tests=r'''
static void reset(void) {
 memset(memory,0,sizeof(memory));memory[30]=1;memory[33]=1024;irq=logs=barriers=0;
}
static void packet(unsigned id,unsigned count) {
 uint32_t *q=memory+30,*ring=memory+848/4+2*1024;
 ring[0]=(count<<8)|id;ring[1]=0x12340056;ring[2]=0xabcdef01;ring[3]=0x87654321;
 q[10]=0;q[11]=(count+3)&~3u;
}
int main(void) {
 unsigned budget=16;
 reset();hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(budget==16 && !logs && !barriers);
 reset();packet(101,4);budget=1;
 hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);
 assert(!budget && logs==1 && barriers==2 && memory[40]==4);
 reset();packet(101,4);budget=0;
 hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(!logs && memory[40]==4);
 reset();packet(100,2);budget=0;
 if (!setjmp(stopped)) {hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(0);}
 assert(logs>=2 && memory[40]==4 && barriers==2);
 reset();packet(150,5);
 if (!setjmp(stopped)) {hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(0);}
 assert(logs==5 && memory[40]==8);
 reset();irq=1u<<15;
 if (!setjmp(stopped)) {hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(0);}
 assert(logs==1 && !barriers);
 reset();memory[30]=0;
 if (!setjmp(stopped)) {hfi_raw_diagnostic(1,(uintptr_t)memory,&budget);assert(0);}
 reset();uint32_t single=(1u<<8)|100;
 assert(hfi_raw_fault_packet(&single,1,"test"));
 assert(!hfi_raw_fault_packet(NULL,0,"test"));
 single|=1u<<16;assert(!hfi_raw_fault_packet(&single,1,"test"));
 uint32_t many[255]={0};many[0]=(255u<<8)|150;logs=0;
 assert(hfi_raw_fault_packet(many,255,"test") && logs==17);
 puts("Actual RAW fault monitor: DBG/CM3 faults, fatal retention, queue publication, log bounds and no guessed context layout passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
