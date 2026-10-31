#!/usr/bin/env python3
"""Exercise actual RSC/PDC transaction source with busy/refused-write mocks."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code = source[source.index('struct power_sequence {'):source.index('static const struct { uint32_t index, value; } gmu_boot_setup[]')]
harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include "waffle_gpu.h"
typedef uintptr_t vm_offset_t;
#define bzero(p,n) memset(p,0,n)
static uint32_t rsc[WAFFLE_RSCC_SIZE/4], pdc[WAFFLE_GPU_PDC_SIZE/4];
static uint32_t saved_rsc[WAFFLE_RSCC_SIZE/4],saved_pdc[WAFFLE_GPU_PDC_SIZE/4];
static unsigned writes, refuse;
static vm_offset_t ml_io_map(uintptr_t address,size_t size) {
    if (address == WAFFLE_RSCC_BASE) { assert(size == sizeof(rsc)); return (uintptr_t)rsc; }
    assert(address == WAFFLE_GPU_PDC_BASE && size == sizeof(pdc)); return (uintptr_t)pdc;
}
static uint32_t rd(vm_offset_t base,unsigned offset) {
    assert(offset < sizeof(rsc));return *(uint32_t *)(base+offset);
}
static void wr(vm_offset_t base,unsigned offset,uint32_t value) {
    assert(offset < sizeof(rsc)); writes++;
    if (base==(uintptr_t)rsc) assert(offset!=0xd*4 && offset!=0xf*4 && offset!=0x11*4);
    if (base==(uintptr_t)rsc && offset==0x154*4 && refuse) { refuse=0;return; }
    if (base==(uintptr_t)rsc && offset==4*4) {
        value = (rsc[4]&~(1u<<24)) | (value&(1u<<24));
    }
    *(uint32_t *)(base+offset)=value;
}
static void say(const char *fmt,...) { (void)fmt; }
static void stop_unsafe(const char *why) { (void)why;assert(!"unsafe restore"); }
'''
tests = r'''
static void reset(void) {
    for(unsigned i=0;i<sizeof(rsc)/4;i++) rsc[i]=i^0xa5a5;
    for(unsigned i=0;i<sizeof(pdc)/4;i++) pdc[i]=i^0x5a5a;
    rsc[0xd]=0x82204514;rsc[0xf]=0x82204510;rsc[0x11]=0x82204520;
    rsc[0x101]=0; writes=refuse=0;
    memcpy(saved_rsc,rsc,sizeof(rsc));memcpy(saved_pdc,pdc,sizeof(pdc));
}
static void unchanged(void) {
    assert(!memcmp(saved_rsc,rsc,sizeof(rsc)));assert(!memcmp(saved_pdc,pdc,sizeof(pdc)));
}
int main(void) {
    struct power_sequence seq;
    reset();rsc[0x101]=1;
    assert(!power_sequence_prepare(&seq) && !writes && !seq.changed);
    reset();rsc[4]|=1u<<16;assert(!power_sequence_prepare(&seq) && !writes);
    reset();rsc[0xd]=0;assert(!power_sequence_prepare(&seq) && !writes);
    reset();assert(power_sequence_prepare(&seq));
    assert(rsc[0x154]==0xeaaae5a0 && rsc[0x180]==saved_rsc[0x180]);
    assert(rsc[0x12]==0x80000021 && pdc[0x1140]==0x80000001);
    power_sequence_restore(&seq);assert(!seq.changed);unchanged();
    reset();refuse=1;assert(!power_sequence_prepare(&seq));
    power_sequence_restore(&seq);unchanged();
    reset();assert(power_sequence_prepare(&seq));
    rsc[4]|=1u<<16;rsc[0x101]=1;seq.native_sleep=true;
    unsigned before = writes;power_sequence_restore(&seq);
    assert(writes==before && !seq.changed && rsc[0x154]==0xeaaae5a0);
    assert(pdc[0x1140]==0x80000001);
    puts("Power sequencer busy/refused-write/rollback/native-sleep checks passed");return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.c').write_text(harness+code+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
                    '-I',str(ROOT/'kernel/files/bsd/sys'),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
