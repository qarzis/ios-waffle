#!/usr/bin/env python3
"""Exercise actual LLCC snapshot: bounded offsets, zero writes, temporary maps."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_adreno.c').read_text()
function=s[s.index('static void probe_llcc_snapshot('):s.index('static void probe_aop_qmp(')]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#define VM_WIMG_IO 0x1234
static uint32_t memory[3][0x4000/4],before[3][0x4000/4];
static unsigned maps,unmaps,fail_at,reads,active;
static char output[4096];
static void gpu_log(const char *fmt,...) {
    va_list ap;va_start(ap,fmt);unsigned used=strlen(output);
    vsnprintf(output+used,sizeof(output)-used,fmt,ap);va_end(ap);
    if(strstr(fmt,"snapshot complete")) assert(!active);
}
static uintptr_t ml_io_map_unmappable(uintptr_t pa,unsigned bytes,unsigned flags) {
    const uintptr_t expected[]={0x25034000,0x25808000,0x25820000};
    assert(maps<3 && pa==expected[maps] && !(pa&0x3fff) && bytes==0x4000 && flags==VM_WIMG_IO);
    unsigned slot=maps++;
    if(fail_at==maps) return 0;
    active++;return (uintptr_t)memory[slot];
}
static void ml_io_unmap(uintptr_t address,unsigned bytes) {
    assert(active && bytes==0x4000 && address==(uintptr_t)memory[active-1]);active--;unmaps++;
}
static uint32_t read_reg(uintptr_t base,unsigned off) {
    const unsigned status[]={0x1000,0x1004,0x3000,0x3004};
    const unsigned attrs[]={0x1048,0x104c,0x1124,0x1058,0x105c,0x112c};
    unsigned page=base==(uintptr_t)memory[0]?0:base==(uintptr_t)memory[1]?1:2;
    assert(base==(uintptr_t)memory[page] && active==3 && !(off&3) && off<0x4000);
    bool valid=page==0 && off==0xc;
    if(page==1)for(unsigned i=0;i<4;i++)if(off==status[i])valid=true;
    if(page==2)for(unsigned i=0;i<6;i++)if(off==attrs[i])valid=true;
    assert(valid);reads++;return memory[page][off/4];
}
'''
checks=r'''
int main(void) {
    memset(memory,0xa5,sizeof(memory));memory[0][0xc/4]=0x80000000;
    memcpy(before,memory,sizeof(memory));
    for(fail_at=0;fail_at<=3;fail_at++) {
        maps=unmaps=reads=active=0;output[0]=0;
        probe_llcc_snapshot();
        assert(!memcmp(memory,before,sizeof(memory)) && !active);
        if(!fail_at) {
            assert(maps==3 && unmaps==3 && reads==11);
            assert(strstr(output,"banks=8") && strstr(output,"LLCC61 sid=9 ") && strstr(output,"LLCC61 sid=11 "));
            assert(strstr(output,"snapshot complete; no LLCC or GPU writes"));
        } else {
            assert(maps==fail_at && unmaps==fail_at-1 && !reads);
            assert(!strstr(output,"snapshot complete"));
        }
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'test.c').write_text(code+function+checks)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',p/'test.c','-o',p/'test'],check=True)
    subprocess.run([p/'test'],check=True)
print('Actual LLCC snapshot: 11 whitelisted reads, zero writes, all3 mapping failures cleaned up; ASan/UBSan passed')
