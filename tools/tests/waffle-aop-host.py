#!/usr/bin/env python3
"""Check QMP mailbox bounds and link classification without MMIO writes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <sys/waffle_aop.h>
static uint32_t ram[256], before[256];
static unsigned writes, kicks, waits, fail_wait, sending, suppress_ack;
static uint32_t received[16], received_size;
static unsigned combined, on_seen, off_seen, fail_on, fail_off;
static uint32_t rd(void *c, uint32_t off) {
    (void)c; assert(!(off & 3) && off < sizeof(ram)); return ram[off/4];
}
static void wr(void *c, uint32_t off, uint32_t value) {
    (void)c; assert(off == 0x2c || off == 0x18 || (sending && off >= 0x128 && off < 0x16c));
    writes++; ram[off/4] = value;
}
static void kick(void *c) {
    (void)c; kicks++;
    if (combined) {
        ram[0x30/4]=ram[0x2c/4];
        if (ram[0x128/4]) {
            bool on = !memcmp(&ram[0x12c/4],"{class: gpu, res: acd, val: 1}",31);
            if(on) on_seen++; else off_seen++;
            if (!(on ? fail_on : fail_off)) ram[0x128/4]=0;
        }
        return;
    }
    if (sending) {
        received_size=ram[0x128/4];
        memcpy(received,&ram[0x12c/4],received_size);
        if (!suppress_ack) ram[0x128/4]=0;
    } else ram[0x30/4] = ram[0x2c/4];
}
static bool wait_for(void *c, uint32_t off, uint32_t value) {
    waits++; return waits != fail_wait && rd(c,off) == value;
}
static void reset(void) {
    combined=on_seen=off_seen=fail_on=fail_off=0;
    memset(ram,0,sizeof(ram)); writes=kicks=waits=fail_wait=sending=suppress_ack=0;
    ram[0]=WAFFLE_AOP_QMP_MAGIC; ram[1]=1;
    ram[0x34/4]=728; ram[0x38/4]=0x128;
    const unsigned up[]={0x0c,0x10,0x14,0x18,0x24,0x28};
    for(unsigned i=0;i<sizeof(up)/sizeof(up[0]);i++) ram[up[i]/4]=WAFFLE_AOP_QMP_UP;
    ram[0x2c/4]=ram[0x30/4]=WAFFLE_AOP_QMP_DOWN;
    memcpy(before,ram,sizeof(ram));
}
static void roundtrip_test(void) {
    struct waffle_aop_qmp_io io={0,rd,wr,kick,wait_for};
    reset(); assert(waffle_aop_qmp_channel_roundtrip(&io)==WAFFLE_AOP_QMP_OK);
    assert(writes==3 && kicks==3 && waits==3 && !memcmp(before,ram,sizeof(ram)));
    for(unsigned failure=1;failure<=3;failure++) {
        reset(); fail_wait=failure;
        assert(waffle_aop_qmp_channel_roundtrip(&io)==
            (failure==3 ? WAFFLE_AOP_QMP_RESTORE_FAILED : WAFFLE_AOP_QMP_TIMEOUT));
        assert(!memcmp(before,ram,sizeof(ram)));
    }
    const unsigned guarded[]={0,4,0x0c,0x10,0x14,0x18,0x24,0x28,0x2c,0x30,0x34,0x38,0x128};
    for(unsigned i=0;i<sizeof(guarded)/sizeof(guarded[0]);i++) {
        reset(); ram[guarded[i]/4]=0xdeadbeef;
        memcpy(before,ram,sizeof(ram));
        assert(waffle_aop_qmp_channel_roundtrip(&io)==WAFFLE_AOP_QMP_REFUSED);
        assert(!writes && !kicks && !waits && !memcmp(before,ram,sizeof(ram)));
    }
}
static void send_test(void) {
    struct waffle_aop_qmp_io io={0,rd,wr,kick,wait_for};
    uint32_t packet[16];
    const char *expected[]={"{class: gpu, res: acd, val: 0}","{class: gpu, res: acd, val: 1}"};
    for(unsigned enabled=0;enabled<2;enabled++) {
        unsigned bytes=waffle_aop_acd_packet(packet,16,enabled);
        assert(bytes==32 && !memcmp(packet,expected[enabled],strlen(expected[enabled])+1));
        assert(!waffle_aop_acd_packet(packet,7,enabled));
        reset(); sending=1; ram[0x2c/4]=ram[0x30/4]=WAFFLE_AOP_QMP_UP;
        assert(waffle_aop_qmp_send_acd(&io,enabled)==WAFFLE_AOP_QMP_OK);
        assert(received_size==32 && !memcmp(received,expected[enabled],strlen(expected[enabled])+1));
        assert(!ram[0x128/4]);
    }
    reset(); sending=1; ram[0x2c/4]=ram[0x30/4]=WAFFLE_AOP_QMP_UP;
    suppress_ack=1;
    assert(waffle_aop_qmp_send_acd(&io,true)==WAFFLE_AOP_QMP_TIMEOUT);
    assert(!ram[0x128/4]);
    reset(); assert(waffle_aop_qmp_send_acd(&io,true)==WAFFLE_AOP_QMP_REFUSED);
    assert(!writes && !kicks);
    reset(); sending=1; ram[0x2c/4]=ram[0x30/4]=WAFFLE_AOP_QMP_UP; ram[0x128/4]=32;
    assert(waffle_aop_qmp_send_acd(&io,true)==WAFFLE_AOP_QMP_REFUSED);
    assert(!writes && !kicks);
}
static void gpu_task(void *arg) {
    unsigned *called=arg;
    assert(on_seen==1 && off_seen==0 && ram[0x2c/4]==WAFFLE_AOP_QMP_UP && ram[0x30/4]==WAFFLE_AOP_QMP_UP);
    (*called)++;
}
int main(void) {
    send_test();
    struct waffle_aop_qmp_io tx={0,rd,wr,kick,wait_for};
    for(unsigned failures=0; failures<4; ++failures) {
        reset(); combined=sending=1; fail_on=failures&1; fail_off=failures&2;
        unsigned called=0;
        assert(waffle_aop_qmp_transaction_run(&tx,true,gpu_task,&called)==(fail_off ? WAFFLE_AOP_QMP_RESTORE_FAILED :
            fail_on ? WAFFLE_AOP_QMP_TIMEOUT : WAFFLE_AOP_QMP_OK));
        assert(called==!fail_on);
        assert(on_seen==1 && off_seen==1 && ram[0x2c/4]==WAFFLE_AOP_QMP_DOWN && ram[0x30/4]==WAFFLE_AOP_QMP_DOWN);
    }
    roundtrip_test();
    struct waffle_aop_qmp_snapshot s = {
        .magic = WAFFLE_AOP_QMP_MAGIC, .version = 1,
        .our_box = 0x100, .our_box_size = 0x100,
    };
    assert(waffle_aop_qmp_geometry_valid(&s));
    assert(!waffle_aop_qmp_channel_open(&s));
    s.our_link = s.our_link_ack = s.our_channel =
        s.their_channel = s.our_channel_ack = WAFFLE_AOP_QMP_UP;
    assert(waffle_aop_qmp_channel_open(&s));
    s.our_box = 0x3fc;
    assert(!waffle_aop_qmp_geometry_valid(&s));
    s.our_box = UINT32_MAX - 3;
    assert(!waffle_aop_qmp_geometry_valid(&s));
    s.our_box = 0x100; s.our_box_size = 67;
    assert(!waffle_aop_qmp_geometry_valid(&s));
    s.our_box_size = 0x100; s.version = 2;
    assert(!waffle_aop_qmp_geometry_valid(&s));
    s.version = 1; s.magic = 0;
    assert(!waffle_aop_qmp_geometry_valid(&s));
    assert(!waffle_aop_qmp_geometry_valid(0));
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "aop.c", Path(tmp) / "aop"
    src.write_text(source)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-g", "-I", root / "kernel/files/bsd",
                    src, "-o", exe], check=True)
    subprocess.run([exe], check=True)
print("AOP QMP bounds, channel roundtrip, timeout cleanup and 13 refusal cases passed")
