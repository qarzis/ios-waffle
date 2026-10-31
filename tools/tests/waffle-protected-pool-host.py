#!/usr/bin/env python3
"""Actual persistent pool: scattered pages, native32-segment batches and rollback."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_smmu.c').read_text()
decl=s[s.index('#define PROTECTED_POOL_ADDRESS'):s.index('static struct protected_gpu_pool *protected_pool_prepare(')]
code=s[s.index('/* Persistent protected arena'):]
code=code.replace('__asm__ volatile("dc cvac, %0"::"r"(a):"memory");','clean_page(a);')
code=code.replace('__asm__ volatile("dc civac, %0"::"r"(a):"memory");','clean_page(a);')
harness=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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
#define kernel_map 7
#define bzero(p,n) memset(p,0,n)
struct table_pool {unsigned count;uintptr_t memory[32];uint64_t phys[32];};
struct gpu_context {uintptr_t cb;bool changed;};
static void *objects[16],*data;
static unsigned objects_count,freed,mode,shared,active,lock_calls,reclaim_calls,detached,blocked,maps;
static bool owned[256];
static uint64_t selected_base;
static jmp_buf caught;
static int kmem_alloc(int map,uintptr_t *out,unsigned size,unsigned flags,unsigned tag) {
    assert(map==7 && flags==7 && tag==5 && (size==16384 || size==0x400000));
    if(mode==9 && size==0x400000)return 1;
    void *p=aligned_alloc(16384,size);assert(p);memset(p,0,size);
    objects[objects_count++]=p;*out=(uintptr_t)p;if(size==0x400000)data=p;return 0;
}
static uintptr_t kvtophys(uintptr_t p) {
    uintptr_t offset=p-(uintptr_t)data;assert(data && offset<0x400000);
    return 0x8d1000000ULL+(offset/16384)*32768+offset%16384;
}
static uint64_t *new_table(struct table_pool *pool) {
    assert(!pool->count);
    for(unsigned i=0;i<4;++i){assert(!kmem_alloc(7,&pool->memory[i],16384,7,5));pool->phys[i]=0x8e0000000ULL+i*16384;}
    pool->count=4;return (uint64_t*)pool->memory[0];
}
static bool map_page(struct table_pool *pool,uint64_t va,uint64_t pa,bool readonly) {
    assert(pool->count==4 && va>=selected_base && va<selected_base+0x400000 && !readonly);
    assert(pa==kvtophys((uintptr_t)data+va-selected_base));maps++;return true;
}
static void clean_page(uintptr_t p) {(void)p;assert(!shared);}
static void barrier(void) {}
bool waffle_scm_assign_pages(const uint64_t *phys,unsigned count,unsigned request) {
    assert(count && count<=32);
    if(request==WAFFLE_SCM_SHARE_TABLE){assert(!shared && count==4);if(mode==1)return false;shared=1;return true;}
    if(request==WAFFLE_SCM_RECLAIM_TABLE){assert(shared && !active && count==4);for(unsigned i=0;i<256;++i)assert(!owned[i]);shared=0;return true;}
    assert(shared);
    if(request==WAFFLE_SCM_LOCK_DATA){lock_calls++;if(mode==2 && lock_calls==3)return false;}
    else {assert(request==WAFFLE_SCM_RECLAIM_DATA && !active);reclaim_calls++;if(mode==6)return false;}
    for(unsigned i=0;i<count;++i) {
        assert(phys[i]>=0x8d1000000ULL && !((phys[i]-0x8d1000000ULL)%32768));
        unsigned index=(phys[i]-0x8d1000000ULL)/32768;assert(index<256);
        if(request==WAFFLE_SCM_LOCK_DATA){assert(!owned[index]);owned[index]=true;}
        else {assert(owned[index]);owned[index]=false;}
        assert(!mprotect((uint8_t*)data+index*16384,16384,owned[index]?PROT_NONE:PROT_READ|PROT_WRITE));
    }
    return true;
}
static bool gpu_context_begin_at(struct gpu_context *g,uintptr_t smmu,unsigned page,unsigned pages,unsigned contexts,unsigned matches,uint64_t root,unsigned bank,unsigned slot,unsigned sid) {
    assert(smmu==9 && page==4096 && pages==32 && contexts==22 && matches==24 && root==0x8e0000000ULL);
    assert(shared && bank==2 && slot==2 && sid==2);for(unsigned i=0;i<256;++i)assert(owned[i]);
    g->changed=true;g->cb=10;active=1;return mode!=3;
}
static bool gpu_context_end(struct gpu_context *g) {
    if(g->changed){assert(active);g->changed=false;active=0;detached++;}return mode!=4;
}
static bool translate_page(uintptr_t qtb,uintptr_t cb,uint64_t va,uint64_t pa,unsigned sid) {
    assert(qtb==8 && cb==10 && sid==2 && active && shared);
    assert(va==selected_base || va==selected_base+0x3ff000);
    assert(pa==kvtophys((uintptr_t)data+va-selected_base));return mode!=5;
}
static void kmem_free(int map,uintptr_t p,unsigned size) {
    assert(map==7 && !active && !shared && (size==16384 || size==0x400000));
    for(unsigned i=0;i<256;++i)assert(!owned[i]);
    for(unsigned i=0;i<objects_count;++i)if(objects[i]==(void*)p){free(objects[i]);objects[i]=NULL;freed++;return;}
    assert(!"unknown free");
}
static void log_line(const char *fmt,...) {(void)fmt;}
static void secure_context_stop(const char *why) {(void)why;assert(!freed);blocked++;longjmp(caught,1);}
'''
tests=r'''
static void reset(unsigned m) {
    if(data)assert(!mprotect(data,0x400000,PROT_READ|PROT_WRITE));
    for(unsigned i=0;i<objects_count;++i)free(objects[i]);
    memset(objects,0,sizeof(objects));memset(owned,0,sizeof(owned));data=NULL;
    objects_count=freed=shared=active=lock_calls=reclaim_calls=detached=blocked=maps=0;mode=m;
}
static struct protected_gpu_pool *prepare(void){return protected_pool_prepare(9,4096,32,22,24,8,selected_base);}
int main(void) {
    for(unsigned profile=0;profile<2;profile++) {
    selected_base=profile?0x100000000ULL:0xa0000000ULL;
    struct protected_gpu_pool *p;
    reset(0);p=prepare();assert(p && p->owned==256 && active && lock_calls==8 && maps==1024);
    protected_pool_release(p);assert(reclaim_calls==8 && detached==1 && freed==6 && !shared);data=NULL;
    reset(1);assert(!prepare() && freed==6);data=NULL;
    reset(2);assert(!prepare() && lock_calls==3 && reclaim_calls==2 && freed==6);data=NULL;
    reset(3);assert(!prepare() && detached==1 && reclaim_calls==8 && freed==6);data=NULL;
    reset(5);assert(!prepare() && detached==1 && freed==6);data=NULL;
    reset(9);assert(!prepare() && freed==1);data=NULL;
    reset(4);if(!setjmp(caught)){p=prepare();protected_pool_release(p);assert(!"TLB failure must retain pages");}assert(blocked==1 && !freed);
    reset(6);if(!setjmp(caught)){p=prepare();protected_pool_release(p);assert(!"unconfirmed reclaim must retain pages");}assert(blocked==1 && !freed);
    reset(0);
    }
    puts("Persistent protected pool scatter/batch/partial-rollback/TLB/CPU-inaccessible retention passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+decl+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
