#!/usr/bin/env python3
"""Actual page probe: SCM ABI and inaccessible CPU page until confirmed reclaim."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('bool waffle_scm_assign_pages('):s.index('static bool secure_gpu_init(')]
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(p):"memory");','clean(p);')
code=code.replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
harness=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <sys/mman.h>
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
#define bzero(p,n) memset(p,0,n)
static uint8_t *arena;
static unsigned mode,allocations,frees,unmaps,calls,owner,blocked;
static jmp_buf caught;
static void say(const char *fmt,...) {(void)fmt;}
static void barrier(void) {}
static void clean(uintptr_t p) {assert(p>=(uintptr_t)arena && p<(uintptr_t)arena+32768 && (!owner || p>=(uintptr_t)arena+16384));}
static int kmem_alloc(int map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag) {
    assert(map==7 && size==16384 && flags==7 && tag==5);
    if((mode==3 && !allocations)||(mode==4 && allocations==1))return 1;
    assert(allocations<2);*out=(uintptr_t)arena+16384*allocations++;
    memset((void*)*out,0,16384);return 0;
}
static void kmem_free(int map,uintptr_t p,unsigned size) {
    assert((!owner || p==(uintptr_t)arena+16384) && map==7 && size==16384 && p>=(uintptr_t)arena && p<(uintptr_t)arena+32768);frees++;
}
static uintptr_t kvtophys(uintptr_t p) {
    assert(p>=(uintptr_t)arena && p<(uintptr_t)arena+32768);
    return 0x8d0000000ULL+(p-(uintptr_t)arena);
}
static uintptr_t ml_io_map_unmappable(uintptr_t pa,unsigned size,unsigned attr) {
    assert(pa==0x8d0004000ULL && size==16384 && attr==6);return (uintptr_t)arena+16384;
}
static void ml_io_unmap(uintptr_t alias,unsigned size) {assert(alias==(uintptr_t)arena+16384 && size==16384);unmaps++;}
static int32_t scm_one(uint32_t fn,uint64_t arg,uint64_t *answer) {
    assert(fn==0x42000601 && arg==0x02000c16);*answer=mode==8?0:1;return mode==9?-1:0;
}
static uint64_t get64(unsigned offset) {uint64_t v;memcpy(&v,arena+16384+offset,8);return v;}
static uint32_t get32(unsigned offset) {uint32_t v;memcpy(&v,arena+16384+offset,4);return v;}
static int32_t scm_raw(uint32_t fn,uint32_t info,const uint64_t args[4],uint64_t *answer) {
    assert(fn==0x42000c16 && info==0x1117);
    assert(args[0]==0x8d0004000ULL && args[1]==16 && args[2]==0x8d0005000ULL && args[3]==0x8d0007000ULL);
    assert(get64(0)==0x8d0000000ULL && get64(8)==16384);
    assert(get64(12288)==(mode==5 && calls==1?8u:4u) && get64(12296)==0x8d0006000ULL && get64(12304)==(mode==5 && calls==0?48u:24u));
    assert(get64(12312)==0 && get64(12320)==0 && get64(12328)==0 && get64(12336)==0);
    assert(get64(8200)==0 && get64(8208)==0);calls++;
    if(calls==1) {
        assert(get32(4096)==3 && get32(8192)==(mode==5?3u:10u) && get32(8196)==6 && !owner);
        if(mode==5){assert(get32(8216)==10 && get32(8220)==4);owner=2;*answer=0;return 0;}
        owner=1;assert(!mprotect(arena,16384,PROT_NONE));
        *answer=mode==1?1:0;return 0;
    }
    assert(calls==2 && owner && get32(4096)==(mode==5?3u:10u) && get32(8192)==3 && get32(8196)==7);
    if(mode==5)assert(get32(4100)==10);
    if(mode==2){*answer=0;return -1;}
    owner=0;assert(!mprotect(arena,16384,PROT_READ|PROT_WRITE));*answer=0;return 0;
}
static void stop_unsafe(const char *why) {
    (void)why;assert(owner);blocked++;longjmp(caught,1);
}
'''
tests=r'''
static void reset(unsigned m) {
    assert(!mprotect(arena,16384,PROT_READ|PROT_WRITE));
    memset(arena,0,32768);mode=m;allocations=frees=unmaps=calls=owner=blocked=0;
}
int main(void) {
    uint8_t *raw=mmap(NULL,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(raw!=MAP_FAILED);arena=(uint8_t*)(((uintptr_t)raw+16383)&~(uintptr_t)16383);
    uint64_t pages[257],regs[4];for(unsigned i=0;i<257;++i)pages[i]=0x8e0000000ULL+16384*i;
    reset(0);assert(waffle_scm_assign_encode(arena+16384,16384,0x8d0004000ULL,pages,256,false,regs));
    assert(regs[1]==4096);
    assert(!waffle_scm_assign_encode(arena+16384,16384,0x8d0004000ULL,pages,257,false,regs));
    pages[1]=pages[0];assert(!waffle_scm_assign_encode(arena+16384,16384,0x8d0004000ULL,pages,2,false,regs));
    pages[0]=0x8d0004000ULL;assert(!waffle_scm_assign_encode(arena+16384,16384,0x8d0004000ULL,pages,1,false,regs));
    pages[0]=0x1000000000ULL;assert(!waffle_scm_assign_encode(arena+16384,16384,0x8d0004000ULL,pages,1,false,regs));
    reset(0);assert(secure_page_probe(false));assert(calls==2 && frees==2 && unmaps==1 && !owner);
    reset(5);assert(secure_page_probe(true));assert(calls==2 && frees==2 && unmaps==1 && !owner);
    reset(1);if(!setjmp(caught)){secure_page_probe(false);assert(!"must retain uncertain pages");}assert(blocked==1 && owner && !frees);
    reset(2);if(!setjmp(caught)){secure_page_probe(false);assert(!"must retain unreclaimed pages");}assert(blocked==1 && owner && !frees);
    reset(0);allocations=1;pages[0]=0x8d0000000ULL;
    assert(waffle_scm_assign_pages(pages,1,WAFFLE_SCM_LOCK_DATA));assert(owner && frees==1);
    allocations=1;assert(waffle_scm_assign_pages(pages,1,WAFFLE_SCM_RECLAIM_DATA));assert(!owner && frees==2);
    reset(5);allocations=1;
    assert(waffle_scm_assign_pages(pages,1,WAFFLE_SCM_SHARE_TABLE));assert(owner==2);
    allocations=1;assert(waffle_scm_assign_pages(pages,1,WAFFLE_SCM_RECLAIM_TABLE));assert(!owner);
    reset(0);assert(!waffle_scm_assign_pages(pages,0,WAFFLE_SCM_LOCK_DATA) && !allocations);
    assert(!waffle_scm_assign_pages(pages,33,WAFFLE_SCM_LOCK_DATA) && !allocations);
    reset(3);assert(!secure_page_probe(false) && !allocations && !calls);
    reset(4);assert(!secure_page_probe(false) && allocations==1 && frees==1 && !calls);
    reset(8);assert(!secure_page_probe(false) && !allocations);
    reset(9);assert(!secure_page_probe(false) && !allocations);
    puts("SCM native ABI/segment bounds/CPU-inaccessible ownership/failure retention checks passed");
    reset(0);assert(!munmap(raw,65536));
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
