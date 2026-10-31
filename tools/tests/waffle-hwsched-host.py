#!/usr/bin/env python3
"""Actual START capture: bounded decode, no fabricated allocation ACK or CP access."""
from pathlib import Path
import json
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool hfi_start_capture('):s.index('static bool gpu_firmware_probe(')]
code=code.replace('__asm__ volatile("dsb sy":::"memory");','barrier();')
fixture=json.loads((ROOT/'tools/tests/fixtures/waffle-hfi-start-allocations.json').read_text())['packets']
assert len(fixture)==8 and all(len(p)==11 for p in fixture)
captured='static const uint32_t captured[8][11]={'+','.join('{'+','.join(hex(w)+'u' for w in p)+'}' for p in fixture)+'};\n'
harness=r'''
#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "waffle_hfi.h"
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
#define WAFFLE_HWSCHED_POOL_ADDRESS 0x61000000u
#define WAFFLE_HWSCHED_POOL_SIZE 0x02000000u
struct waffle_gmu_region {unsigned address,size;bool gpu_only,readonly;};
struct waffle_gmu_plan {struct waffle_gmu_region arena;uint64_t protected_address;unsigned protected_size;bool split_gpu_va,compact_gpu_va;bool (*pool_permissions)(void *,uint64_t,uint32_t,uint32_t);void *pool_permissions_context;};
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *p,unsigned addr,unsigned size) {
    assert(addr==WAFFLE_HWSCHED_POOL_ADDRESS && size==(p->compact_gpu_va?WAFFLE_GPU_COMPACT_POOL_BYTES:WAFFLE_HWSCHED_POOL_SIZE));return &p->arena;
}
#define NSEC_PER_USEC 1000
static uint32_t shared[4096];
static unsigned mode,waits,kicks;
static bool global_va,compact_va,native_secure_va;
static unsigned permission_calls;static bool permission_fail;static jmp_buf bailout;
static void stop_unsafe(const char *why){(void)why;longjmp(bailout,1);}
static bool permissions(void *ctx,uint64_t va,uint32_t size,uint32_t flags){
 assert(ctx==(void *)1 && va==waffle_gpu_compact_alias(WAFFLE_HWSCHED_POOL_ADDRESS)+(permission_calls?4096u:0u));
 assert(size==(permission_calls?32768u:4096u) && flags==0x33b && kicks==permission_calls+1);permission_calls++;return !permission_fail;
}
static void barrier(void) {}
static void say(const char *fmt,...) {(void)fmt;}
static void delay_for_interval(unsigned delay,unsigned unit) {assert(delay==100&&unit==1000);waits++;}
static void wr(vm_offset_t base,unsigned offset,uint32_t value) {
    assert(base==123 && offset==WAFFLE_GMU_REG(0x1f994) && value==1);kicks++;
    unsigned old=shared[6+10];
    uint32_t *sent=shared+848/4+old;
    shared[6+10]=shared[6+11];
    if(kicks==1)assert(sent[0]==((13u<<20)|(1u<<8)|10));
    else {
        assert((sent[0]&0xfffff)==((1u<<16)|(11u<<8)|20));
        assert(sent[2]==(mode==6 && kicks==3?(native_secure_va?0u:0xa0000000u):(compact_va?0x500000u:0x61000000u)+(kicks==3?4096u:0u)));
        assert(sent[3]==(mode==6 && kicks==3?(native_secure_va?1u:0u):(global_va?0x1ff80u:0u)) && sent[6]==sent[7] && sent[8]==(mode==6 && kicks==3?0u:0x61000000u+(kicks==3?4096u:0u)));
        assert(sent[1]==(20|(11u<<8)));
    }
    if (!mode)return;
    uint32_t reply[]={20|(11u<<8),1,0,0,0x33b,2,0,7,0,4096,12};
    if(mode==2)reply[0]=20|(255u<<8);
    if(mode>=3 && kicks==2){reply[5]=1;reply[7]=8;reply[9]=32768;}
    if(mode==4 && kicks==2){reply[4]|=1u<<12;reply[5]=5;}
    if(mode==6 && kicks==2){reply[4]=0x1007;reply[5]=5;reply[9]=0x37d000;}
    if((mode==3 || mode==6) && kicks==3){reply[0]=10|(1u<<16)|(3u<<8);reply[1]=(13u<<20)|(1u<<8)|10;reply[2]=0;}
    unsigned cursor=shared[18+10];
    memcpy(shared+(848+4096)/4+cursor,reply,sizeof(reply));
    shared[18+11]=cursor+(((reply[0]>>8)&255)==3?4:12);
}
'''
harness += 'static inline uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *plan,uint64_t address)\n{\n    return plan->compact_gpu_va ? waffle_gpu_compact_alias(address) : waffle_gpu_global_alias(address);\n}\n'
tests=r'''
static void reset(unsigned m) {
    memset(shared,0,sizeof(shared));mode=m;waits=kicks=0;global_va=compact_va=native_secure_va=false;
    shared[6]=shared[18]=1;shared[6+3]=shared[18+3]=1024;
}
int main(void) {
    struct waffle_hfi_mem_request r={0};
    uint32_t p[]={20|(11u<<8),1,0,0,0x33b,2,0,7,0,4096,12};
    assert(waffle_hfi_mem_request_decode(p,11,&r));
    assert(r.size==4096 && r.gmu_handle==7 && r.alignment==12);
    p[0]=20|(10u<<8);p[1]=0;assert(waffle_hfi_mem_request_decode(p,10,&r)&&r.alignment==0);
    for(unsigned n=0;n<10;++n)assert(!waffle_hfi_mem_request_decode(p,n,&r));
    p[0]=20|(11u<<8);p[1]=2;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    p[1]=1;p[10]=32;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    p[10]=32u<<8;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    p[10]=0;p[9]=0;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    p[9]=4096;p[5]=26;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    p[5]=2;p[4]=0x80000000;assert(!waffle_hfi_mem_request_decode(p,11,&r));
    reset(1);assert(hfi_start_capture(123,(uintptr_t)shared,NULL,25));assert(kicks==1 && !waits && shared[18+10]==12);
    reset(0);assert(!hfi_start_capture(123,(uintptr_t)shared,NULL,25));assert(kicks==1 && waits==10000);
    reset(2);assert(!hfi_start_capture(123,(uintptr_t)shared,NULL,25));assert(kicks==1 && !waits);
    reset(0);shared[6+11]=1024;assert(!hfi_start_capture(123,(uintptr_t)shared,NULL,25));assert(!kicks);
    struct waffle_hfi_pool live_pool={.base=0x61000000,.size=0x2000000};
    for(unsigned i=0;i<8;++i) {
        struct waffle_hfi_mem_request observed,allocated;
        assert(waffle_hfi_mem_request_decode(captured[i],11,&observed));
        assert(waffle_hfi_pool_reserve(&live_pool,&observed,&allocated)==(i==7?-2:0));
    }
    assert(live_pool.count==7 && live_pool.used==3739648);
    struct waffle_hfi_pool secure_pool={.base=0xa0000000,.size=0x400000};
    struct waffle_hfi_mem_request secure_req,secure_answer;
    assert(waffle_hfi_mem_request_decode(captured[7],11,&secure_req));
    assert(waffle_hfi_pool_reserve_secure(&secure_pool,&secure_req,&secure_answer)==0);
    assert(secure_answer.gpu_address==0xa0000000 && !secure_answer.gmu_address && secure_answer.flags==0x1007);
    secure_req.flags|=8;assert(waffle_hfi_pool_reserve_secure(&secure_pool,&secure_req,&secure_answer)==-2);
    secure_req.flags=0x1007;secure_req.gmu_handle++;
    assert(waffle_hfi_pool_reserve_secure(&secure_pool,&secure_req,&secure_answer)==-4);
    struct waffle_hfi_pool native_secure={.base=0x100000000ULL,.size=0x400000};
    struct waffle_hfi_mem_request native_req={.flags=0x1007,.kind=5,.gmu_handle=5,.size=0x37d000,.alignment=0},native_reply;
    assert(!waffle_hfi_pool_reserve_secure(&native_secure,&native_req,&native_reply));
    assert(native_reply.gpu_address==0x100000000ULL && native_reply.gmu_address==0 && native_reply.host_handle==5);
    assert(!waffle_hfi_pool_reserve_secure(&native_secure,&native_req,&native_reply) && native_secure.count==1);
    native_secure.base=UINT64_MAX-4095;native_secure.count=native_secure.used=0;
    assert(waffle_hfi_pool_reserve_secure(&native_secure,&native_req,&native_reply)==-1);
    native_secure.base=(1ULL<<39)-4096;
    assert(waffle_hfi_pool_reserve_secure(&native_secure,&native_req,&native_reply)==-1);
    native_secure.base=0x100000000ULL;
    assert(waffle_hfi_pool_reserve(&native_secure,&native_req,&native_reply)==-2);
    struct waffle_hfi_pool pool={.base=0x61001000,.size=0x20000};
    struct waffle_hfi_mem_request req={.flags=0x33f,.kind=2,.gmu_handle=2,.size=4096,.alignment=16},answer;
    assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==0 && answer.gmu_address==0x61010000 && pool.used==0x10000);
    assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==0 && pool.count==1 && pool.used==0x10000);
    req.size=8192;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-3 && pool.count==1);
    req.kind=5;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-2);
    req.kind=2;req.flags|=1u<<7;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-2);
    req.flags=0x33f;req.gmu_handle=3;req.size=0xffffffff;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-4);
    req.size=4096;req.alignment=0;pool.count=32;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-4);
    pool.count=33;assert(waffle_hfi_pool_reserve(&pool,&req,&answer)==-1);
    struct waffle_gmu_plan plan={.arena={WAFFLE_HWSCHED_POOL_ADDRESS,WAFFLE_HWSCHED_POOL_SIZE,false,false},.protected_address=0xa0000000,.protected_size=0x400000};
    reset(3);assert(hfi_start_capture(123,(uintptr_t)shared,&plan,26));assert(kicks==3);
    reset(6);assert(hfi_start_capture(123,(uintptr_t)shared,&plan,30));assert(kicks==3);
    reset(4);assert(!hfi_start_capture(123,(uintptr_t)shared,&plan,26));assert(kicks==2);
    reset(3);global_va=plan.split_gpu_va=true;
    assert(hfi_start_capture(123,(uintptr_t)shared,&plan,40) && kicks==3);
    reset(6);global_va=true;
    assert(hfi_start_capture(123,(uintptr_t)shared,&plan,40) && kicks==3);
    reset(3);global_va=compact_va=plan.split_gpu_va=plan.compact_gpu_va=true;
    plan.arena.size=WAFFLE_GPU_COMPACT_POOL_BYTES;
    assert(hfi_start_capture(123,(uintptr_t)shared,&plan,54) && kicks==3);
    reset(6);global_va=compact_va=native_secure_va=plan.split_gpu_va=plan.compact_gpu_va=true;
    plan.protected_address=0x100000000ULL;
    assert(hfi_start_capture(123,(uintptr_t)shared,&plan,56) && kicks==3);
    reset(3);global_va=compact_va=true;permission_calls=0;
    plan.pool_permissions=permissions;plan.pool_permissions_context=(void *)1;
    assert(hfi_start_capture(123,(uintptr_t)shared,&plan,72) && permission_calls==2 && kicks==3);
    reset(3);global_va=compact_va=true;permission_fail=true;permission_calls=0;
    if(!setjmp(bailout)){hfi_start_capture(123,(uintptr_t)shared,&plan,72);assert(0);}
    assert(permission_calls==1 && kicks==1); /* No allocation ACK after failure. */
    puts("HWSCHED START decode/pool/duplicate/overflow/secure-refusal/ACK checks passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+code+captured+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
