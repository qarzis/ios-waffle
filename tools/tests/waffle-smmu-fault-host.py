#!/usr/bin/env python3
"""Actual RAW SMMU sampler: fault VA/syndrome and retention, no clear/resume."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static void hfi_smmu_diagnostic('):s.index('static void hfi_publish_notify(')]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <stdarg.h>
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
struct waffle_gmu_plan {vm_offset_t fault_smmu;unsigned fault_page,fault_pages;};
static uint32_t regs[WAFFLE_GPU_SMMU_SIZE/4];
static unsigned reads,logs;
static char message[512];
static jmp_buf stopped;
static uint32_t rd(vm_offset_t base,unsigned off) {
 uintptr_t a=base+off-(uintptr_t)regs;assert(a<sizeof(regs));++reads;return *(uint32_t *)(base+off);
}
static void say(const char *fmt,...) {
 va_list ap;va_start(ap,fmt);vsnprintf(message,sizeof(message),fmt,ap);va_end(ap);++logs;
}
static void stop_unsafe(const char *why) {(void)why;longjmp(stopped,1);}
'''
tests=r'''
int main(void) {
 struct waffle_gmu_plan plan={(uintptr_t)regs,4096,32};
 hfi_smmu_diagnostic(NULL);assert(!reads);
 struct waffle_gmu_plan none={0};hfi_smmu_diagnostic(&none);assert(!reads);
 for(unsigned i=0;i<3;i++) regs[(0x20000+4096*i+0x58)/4]=0x400;
 hfi_smmu_diagnostic(&plan);assert(reads==3 && !logs);
 for(unsigned bank=0;bank<3;bank++) {
  unsigned cb=0x20000+4096*bank;
  regs[(cb+0x58)/4]=0x40000008;regs[(cb+0x60)/4]=0x80010000;regs[(cb+0x64)/4]=7;
  regs[(cb+0x68)/4]=0x12345678;regs[(cb+0x6c)/4]=0x123;regs[(0x1400+4*bank)/4]=bank;
  uint32_t before[WAFFLE_GPU_SMMU_SIZE/4];memcpy(before,regs,sizeof(regs));logs=0;
  if(!setjmp(stopped)) {hfi_smmu_diagnostic(&plan);assert(0);}
  assert(logs==1 && strstr(message,"FAR=780010000") && strstr(message,"12345678/00000123"));
  assert(!memcmp(regs,before,sizeof(regs))); /* No fault clear, resume or teardown. */
  regs[(cb+0x58)/4]=0x400;
 }
 reads=0;plan.fault_page=65536;
 if(!setjmp(stopped)) {hfi_smmu_diagnostic(&plan);assert(0);}assert(!reads);
 plan.fault_page=4096;plan.fault_pages=0xffffffff;
 if(!setjmp(stopped)) {hfi_smmu_diagnostic(&plan);assert(0);}assert(!reads);
 puts("Actual SMMU fault sampler: all3 banks, reserved FSR ignored, full64bitVA/syndrome, no writes, geometry guards passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(harness+code+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
