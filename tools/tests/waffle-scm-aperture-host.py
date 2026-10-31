#!/usr/bin/env python3
"""Actual CP aperture helper: compare pinned native descriptor and SCM64 ABI."""
from pathlib import Path
import subprocess,tempfile,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=source[source.index('static bool scm_gpu_aperture('):source.index('bool waffle_scm_assign_pages(')]
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(p):"memory");','clean(p);').replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
v=ROOT/'work/waffle/gpu/vendor/kernel-drivers-firmware-qcom_scm.c'
native=v.read_text();native=native.replace('EXPORT_SYMBOL(qcom_scm_kgsl_set_smmu_aperture);','').replace('EXPORT_SYMBOL(qcom_scm_kgsl_set_smmu_lpac_aperture);','');native=native[native.index('int qcom_scm_kgsl_set_smmu_aperture('):native.index('int qcom_scm_kgsl_init_regs(')]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_scm.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384u
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define VM_WIMG_WCOMB 6
#define kernel_map 7
#define QCOM_SCM_SVC_MP 0x0c
#define QCOM_SCM_MP_CP_SMMU_APERTURE_ID 0x1b
#define QCOM_SCM_CP_APERTURE_REG 0
#define QCOM_SCM_CP_LPAC_APERTURE_REG 1
#define ARM_SMCCC_OWNER_SIP 2
#define QCOM_SCM_ARGS(n) (n)
struct qcom_scm_desc {unsigned svc,cmd,owner,arginfo;uint64_t args[10];};
static struct qcom_scm_desc expected;
static struct {void *dev;} scm_object,*__scm=&scm_object;
static int qcom_scm_call(void *dev,const struct qcom_scm_desc *desc,void *res) {
 (void)dev;assert(!res);expected=*desc;return 0;
}
static _Alignas(16384) uint8_t arena[16384];
static unsigned mode,allocs,frees,unmaps,calls,delays,barriers;
static void say(const char *fmt,...) {(void)fmt;}
static void clean(uintptr_t p) {assert(p>=(uintptr_t)arena && p<(uintptr_t)arena+sizeof(arena));}
static void barrier(void) {++barriers;}
static int kmem_alloc(int map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag) {
 assert(map==7 && size==16384 && flags==7 && tag==5);
 if(mode==2)return 1;
 ++allocs;*out=(uintptr_t)arena;memset(arena,0,sizeof(arena));return 0;
}
static void kmem_free(int map,uintptr_t p,unsigned size) {
 assert(map==7 && p==(uintptr_t)arena && size==16384);++frees;
}
static uint64_t kvtophys(uintptr_t p) {
 uint64_t pa=0x1230000+(p-(uintptr_t)arena);
 if(mode==3)pa++;
 if(mode==4 && p!=(uintptr_t)arena)pa++;
 return pa;
}
static uintptr_t ml_io_map_unmappable(uint64_t pa,unsigned size,unsigned attr) {
 assert(pa==0x1230000 && size==16384 && attr==6);return mode==5?0:(uintptr_t)arena;
}
static void ml_io_unmap(uintptr_t p,unsigned size) {
 assert(p==(uintptr_t)arena && size==16384);++unmaps;
}
static int32_t scm_one(uint32_t function,uint64_t argument,uint64_t *answer) {
 assert(function==0x42000601 && argument==0x02000c1b);
 *answer=mode==1?0:1;return 0;
}
static int32_t scm_raw(uint32_t function,uint32_t arginfo,const uint64_t args[4],uint64_t *answer) {
 assert(allocs==1 && !frees && !unmaps && barriers==2);
 assert(function==(0x40000000u|(expected.owner<<24)|(expected.svc<<8)|expected.cmd));
 assert(arginfo==expected.arginfo && args[3]==0x1230000);
 for(unsigned i=0;i<3;++i) assert(args[i]==expected.args[i]);
 uint64_t ext[7];memcpy(ext,arena,sizeof(ext));
 for(unsigned i=0;i<7;++i)assert(ext[i]==expected.args[i+3]);
 ++calls;*answer=123;
 if(mode==6)return -1;
 if(mode==7 && calls==1)return -12;
 if(mode==8)return -12;
 return 0;
}
static void delay_for_interval(unsigned t,unsigned unit) {assert(t==30000 && unit==1000);++delays;}
#define NSEC_PER_USEC 1000
'''
tests=r'''
int main(void) {
 for(unsigned lpac=0;lpac<2;++lpac) {
 if(lpac) assert(qcom_scm_kgsl_set_smmu_lpac_aperture(1)==0);
 else assert(qcom_scm_kgsl_set_smmu_aperture(0)==0);
 for(mode=0;mode<=8;++mode) {
  allocs=frees=unmaps=calls=delays=barriers=0;
  bool ok=lpac?waffle_scm_lpac_aperture():waffle_scm_gpu_aperture();
  assert(ok==(mode==0 || mode==7));
  assert(frees==allocs);
  if(mode==0)assert(calls==1 && unmaps==1 && !delays);
  if(mode==1 || mode==2)assert(!calls && !allocs);
  if(mode==3 || mode==4 || mode==5)assert(!calls && !unmaps && allocs==1);
  if(mode==6)assert(calls==1 && unmaps==1);
  if(mode==7)assert(calls==2 && delays==1 && unmaps==1);
  if(mode==8)assert(calls==21 && delays==20 && unmaps==1);
 }
 }
 puts("Actual CP and LPAC aperture SCM helper matches native descriptor/SCM64 extended args; unsupported, allocation/alias/PA failure, busy bound and cleanup passed");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(harness+native+code+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
