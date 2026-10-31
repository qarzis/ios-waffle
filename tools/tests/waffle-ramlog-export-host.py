#!/usr/bin/env python3
"""Exercise the production physical-page exporter without MMIO or USB."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
source = (root / "kernel/files/bsd/dev/waffle_gmu.c").read_text()
function = source[source.index("static bool gen7_restore_snapshot("):source.index("static bool gen7_live_exchange(")]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 0x4000
#define WAFFLE_GMU_LOG_ADDRESS 0x60004000
#define WAFFLE_GMU_HFI_ADDRESS 0x60014000
struct waffle_gmu_region { unsigned address,size; vm_offset_t memory; };
struct waffle_gmu_plan { unsigned count; struct waffle_gmu_region regions[3]; };
static unsigned mode;
static char output[32768];
static void say(const char *fmt,...) {
    va_list ap; va_start(ap,fmt);
    unsigned used=strlen(output);
    vsnprintf(output+used,sizeof(output)-used,fmt,ap); va_end(ap);
}
static uint64_t kvtophys(uintptr_t p) {
    uint64_t offset=p&0xfffffff;
    uint64_t pa=(p<0x20000000?0x8c1000000ULL:0x8c2000000ULL)+(offset/0x4000)*0x8000+(offset&0x3fff);
    if(mode==1)pa++;
    if(mode==2)pa=0xc300000+(offset&0x3fff);
    if(mode==3 && (p&0x3fff)==0x3fff)pa++;
    return pa;
}
'''
tests = r'''
int main(void) {
    uint32_t words[154];
    for(unsigned i=0;i<154;i++) words[i]=0xa5000000+i;
    struct waffle_gmu_region snapshot={0,sizeof(words),(uintptr_t)words};
    assert(gen7_restore_snapshot(&snapshot,60));
    assert(strstr(output,"RESTORE_SNAPSHOT probe=60 word[0]=a5000000"));
    assert(strstr(output,"RESTORE_SNAPSHOT probe=60 word[153]=a5000099"));
    assert(strstr(output,"RESTORE_SNAPSHOT complete probe=60 words=154; RAW not sent"));
    assert(!strstr(output,"word[154]="));
    output[0]=0;snapshot.size=615;assert(!gen7_restore_snapshot(&snapshot,60) && !output[0]);
    snapshot.size=616;snapshot.memory=0;assert(!gen7_restore_snapshot(&snapshot,60) && !output[0]);
    assert(!gen7_restore_snapshot(0,60) && !output[0]);

    struct waffle_gmu_plan p={.count=2,.regions={
        {WAFFLE_GMU_LOG_ADDRESS,0x10000,0x10000000},
        {WAFFLE_GMU_HFI_ADDRESS,0x12000,0x20000000}}};
    assert(gen7_ramlog_manifest(&p,58));
    assert(strstr(output,"RAM_LOG GMU_LOG 3 pa=8c1018000 bytes=4000"));
    assert(strstr(output,"RAM_LOG HFI 0 pa=8c2000000 bytes=4000"));
    assert(strstr(output,"RAM_LOG_MANIFEST complete probe=58 pages=5"));
    for(mode=1;mode<=3;mode++) {
        output[0]=0; assert(!gen7_ramlog_manifest(&p,58));
        assert(!strstr(output,"RAM_LOG_MANIFEST complete"));
    }
    mode=0;p.count=1;output[0]=0;assert(!gen7_ramlog_manifest(&p,58));
    p.count=3;p.regions[2]=p.regions[0];output[0]=0;assert(!gen7_ramlog_manifest(&p,58));
    p.count=2;p.regions[0].size=0x8000;assert(!gen7_ramlog_manifest(&p,58));
    assert(!gen7_ramlog_manifest(0,58));
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p / "test.c").write_text(harness + function + tests)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    p / "test.c", "-o", p / "test"], check=True)
    subprocess.run([p / "test"], check=True)
print("Actual RAM-log exporter: scattered pages, physical continuity, range and completeness checks passed")
