#!/usr/bin/env python3
"""Actual protected-context transaction: detach/TLB before ownership reclaim/free."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
code=s[s.rindex('static bool gpu_secure_context_probe('):s.index('/* Persistent protected arena')]
code=code.replace('__asm__ volatile("dc cvac, %0"::"r"(p):"memory");','clean_page(p);')
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(p):"memory");','clean_page(p);')
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "waffle_gpu.h"
#include "waffle_scm.h"
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
struct table_pool {unsigned count;uintptr_t memory[32];uint64_t phys[32];};
struct gpu_context {uintptr_t cb;bool changed;};
static uint8_t allocations[4][16384] __attribute__((aligned(16384)));
static unsigned mode,state,freed,detached,translates,blocked,allocated;
static jmp_buf caught;
static uintptr_t ml_io_map(uintptr_t pa,unsigned size) {
    if(pa==WAFFLE_GMU_BASE){assert(size==WAFFLE_GMU_SIZE);return 1;}
    assert(pa==WAFFLE_GPUCC_BASE && size==WAFFLE_GPUCC_SIZE);return 2;
}
static uint32_t r32(uintptr_t base,unsigned off) {
    if(base==1){assert(off==WAFFLE_GMU_SYSRESET);return mode==5?0:1;}
    assert(base==2 && off==WAFFLE_GPU_GX_GDSCR);return mode==7?1u<<31:0;
}
static int kmem_alloc(int map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag) {
    assert(map==7 && size==16384 && flags==7 && tag==5);*out=(uintptr_t)allocations[0];allocated++;return 0;
}
static uintptr_t kvtophys(uintptr_t p) {
    assert(p==(uintptr_t)allocations[0]);return 0x8d0000000ULL;
}
static uint64_t *new_table(struct table_pool *p) {
    assert(!p->count);p->count=1;p->memory[0]=(uintptr_t)allocations[1];p->phys[0]=0x8e0000000ULL;
    return (uint64_t*)p->memory[0];
}
static bool map_page(struct table_pool *p,uint64_t va,uint64_t pa,bool readonly) {
    assert(va>=0x90000000ULL && va<0x90004000ULL && pa==0x8d0000000ULL+va-0x90000000ULL && !readonly);
    for(unsigned i=1;i<3;++i){p->memory[i]=(uintptr_t)allocations[i+1];p->phys[i]=0x8e0000000ULL+i*16384;}
    p->count=3;return true;
}
static void clean_page(uintptr_t p) {(void)p;assert(!state);}
static void barrier(void) {}
bool waffle_scm_assign_pages(const uint64_t *p,unsigned count,unsigned request) {
    if(request==WAFFLE_SCM_SHARE_TABLE){assert(!state && count==3 && p[0]==0x8e0000000ULL);if(mode==1)return false;state=1;}
    else if(request==WAFFLE_SCM_LOCK_DATA){assert(state==1 && count==1 && p[0]==0x8d0000000ULL);if(mode==2)return false;state=2;}
    else if(request==WAFFLE_SCM_RECLAIM_DATA){assert(state==2 && detached && count==1);if(mode==6)return false;state=3;}
    else {assert(request==WAFFLE_SCM_RECLAIM_TABLE && (state==1 || state==3) && count==3);state=4;}
    return true;
}
static bool gpu_context_begin_at(struct gpu_context *g,uintptr_t smmu,unsigned page,unsigned pages,unsigned contexts,unsigned matches,uint64_t root,unsigned bank,unsigned slot,unsigned sid) {
    assert(state==2 && smmu==9 && page==4096 && pages==32 && contexts==22 && matches==24);
    assert(root==0x8e0000000ULL && bank==2 && slot==2 && sid==2);g->cb=10;g->changed=true;return mode!=3;
}
static bool gpu_context_end(struct gpu_context *g) {
    if(g->changed){assert(state==2);g->changed=false;detached++;}return mode!=4;
}
static bool translate_page(uintptr_t qtb,uintptr_t cb,uint64_t va,uint64_t pa,unsigned sid) {
    assert(qtb==8 && cb==10 && state==2 && sid==2 && !detached);
    assert(va==0x90000000ULL || va==0x90003000ULL);assert(pa==0x8d0000000ULL+va-0x90000000ULL);translates++;return mode!=8;
}
static void kmem_free(int map,uintptr_t p,unsigned size) {(void)p;assert(map==7 && size==16384 && (state==0 || state==4));freed++;}
static void log_line(const char *fmt,...) {(void)fmt;}
static void secure_context_stop(const char *why) {(void)why;assert(!freed);blocked++;longjmp(caught,1);}
'''
tests=r'''
static void reset(unsigned m){mode=m;state=freed=detached=translates=blocked=allocated=0;}
static bool run(void){return gpu_secure_context_probe(9,4096,32,22,24,8);}
int main(void) {
    reset(0);assert(run());assert(state==4 && detached==1 && translates==2 && freed==4);
    reset(1);assert(!run());assert(!state && freed==4);
    reset(2);assert(!run());assert(state==4 && !detached && freed==4);
    reset(3);assert(!run());assert(state==4 && detached==1 && !translates && freed==4);
    reset(4);if(!setjmp(caught)){run();assert(!"must preserve pages after TLB timeout");}assert(blocked==1 && state==2 && !freed);
    reset(6);if(!setjmp(caught)){run();assert(!"must preserve unreclaimed pages");}assert(blocked==1 && state==2 && !freed);
    reset(5);assert(!run() && !allocated);
    reset(7);assert(!run() && !allocated);
    reset(8);assert(!run() && freed==4 && detached==1);
    puts("Protected context GX/CM3 guards/private SID2/TLB-before-reclaim/failure retention passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
