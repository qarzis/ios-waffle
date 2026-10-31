#!/usr/bin/env python3
"""Exercise the production exchange gate: no RAW if page export fails."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/waffle_gmu.c').read_text()
function = source[source.index('static bool gen7_live_exchange('):source.index('static bool gpu_gen7_live_start(', source.index('static bool gen7_live_exchange('))]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#define NSEC_PER_USEC 1000
#define WAFFLE_GMU_REG(x) (x)
struct waffle_gmu_plan { int unused; };
struct power { uintptr_t memory; };
struct gen7_config_io { unsigned probe; uintptr_t gpu,gmu,hfi_alias; struct power *power; struct waffle_gmu_plan *plan; };
static unsigned exports,delays,sends;
static bool allowed;
static void say(const char *fmt,...) {(void)fmt;}
static uint32_t rd(uintptr_t address,unsigned offset) {(void)address;(void)offset;return 0;}
static bool gen7_ramlog_manifest(const struct waffle_gmu_plan *plan,unsigned probe) {
    assert(plan && probe==59 && !sends);exports++;return allowed;
}
static void delay_for_interval(unsigned duration,unsigned units) {
    assert(duration==5000000 && units==NSEC_PER_USEC && !sends);delays++;
}
static bool hfi_exchange_watch(uintptr_t gmu,uintptr_t alias,const uint32_t *packet,unsigned words,
    const char *name,bool zero_ack,struct waffle_gmu_plan *plan) {
    (void)gmu;(void)alias;(void)name;(void)zero_ack;
    assert(packet && words==11 && plan);sends++;return true;
}
'''
tests = r'''
int main(void) {
    uint32_t restore[16]={0},packet[11]={0};
    struct power power={.memory=(uintptr_t)restore};
    struct waffle_gmu_plan plan={0};
    struct gen7_config_io io={.probe=59,.power=&power,.plan=&plan};
    assert(!gen7_live_exchange(&io,packet,11,true));
    assert(exports==1 && !sends && !delays);
    exports=0;allowed=true;
    assert(gen7_live_exchange(&io,packet,11,true));
    assert(exports==1 && delays==1 && sends==1);
    exports=delays=sends=0;allowed=false;io.probe=57;
    assert(gen7_live_exchange(&io,packet,11,true));
    assert(!exports && delays==1 && sends==1);
    for(unsigned probe=64;probe<=66;probe+=2) {
    exports=delays=sends=0;io.probe=probe;
    assert(gen7_live_exchange(&io,packet,11,true));
    assert(!exports && delays==1 && sends==1);
    }
    for(unsigned edge=68;edge<=70;edge+=2){
    exports=delays=sends=0;io.probe=edge;
    assert(gen7_live_exchange(&io,packet,11,true));
    assert(!exports && !delays && sends==1);
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p / 'test.c').write_text(harness + function + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    p / 'test.c', '-o', p / 'test'], check=True)
    subprocess.run([p / 'test'], check=True)
print('Production RAW59 gate: export failure refuses publication; complete export precedes hold and RAW;57 unchanged')
