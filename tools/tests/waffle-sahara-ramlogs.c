/* SPDX-License-Identifier: BSD-3-Clause */
#include <assert.h>
#include "../waffle-sahara-ramlogs.h"
static unsigned calls, fail_at, resets, saves, state, short_reads, bad_hello, bad_table;
static unsigned char payload[65536];
static unsigned length, position;
static struct waffle_ramlog_entry entries[5];
static void set_payload(const void *data, unsigned bytes)
{
    memcpy(payload, data, bytes); length = bytes; position = 0;
}
static int read_data(void *ctx, void *out, unsigned bytes)
{
    (void)ctx;
    if (++calls == fail_at) return -1;
    if (position == length) return -1;
    unsigned n = length - position;
    if (n > bytes) n = bytes;
    if (short_reads && n > short_reads) n = short_reads;
    memcpy(out, payload + position, n); position += n;
    return (int)n;
}
static int write_data(void *ctx, const void *data, unsigned bytes)
{
    (void)ctx;
    const uint32_t *p = data;
    assert(p[0] == 2 || p[0] == 17 || p[0] == 7);
    if (p[0] == 7) resets++;
    if (++calls == fail_at) return -1;
    if (p[0] == 2) {
        assert(bytes == 48 && p[1] == 48 && p[2] == 2 && p[3] == 1 && p[4] == 0 && p[5] == 2);
        uint32_t table[] = {16,24,0x81b41008,0,bad_table?65537:64,0};
        set_payload(table,24); state=1;
    } else if (p[0] == 17) {
        uint64_t address=(uint64_t)p[2]|(uint64_t)p[3]<<32;
        assert(bytes == 24 && p[1] == 24 && p[5] == 0);
        if (state == 1) assert(address == 0x81b41008 && p[4] == 64);
        else {
            assert(state >= 2 && state <= 6 && address == entries[state-2].address && p[4] == 0x4000);
        }
        memset(payload,0xa5,p[4]); length=p[4]; position=0; state++;
    } else {
        assert(bytes == 8 && p[1] == 8);
        uint32_t ack[]={8,8}; set_payload(ack,8);
    }
    return (int)bytes;
}
static int save_data(void *ctx, unsigned slot, const void *data, unsigned bytes)
{
    (void)ctx;
    assert(slot==saves && bytes==0x4000 && ((const unsigned char *)data)[0]==0xa5);
    if (++calls == fail_at) return 0;
    saves++; return 1;
}
static void reset(unsigned failure, unsigned partial)
{
    calls=resets=saves=state=0; fail_at=failure; short_reads=partial;
    uint32_t hello[]={1,48,2,1,1024,bad_hello?0:2,0,0,0,0,0,0};
    set_payload(hello,48);
    for(unsigned i=0;i<5;i++) entries[i]=(struct waffle_ramlog_entry){0x8c1000000ULL+i*0x4000,i};
}
int main(void)
{
    const struct waffle_sahara_log_io io={0,read_data,write_data,save_data};
    struct waffle_sahara_log_result result;
    reset(0,0); assert(waffle_sahara_logs(&io,entries,&result));
    assert(result.pages==5 && result.reset_sent && result.reset_ack && saves==5 && resets==1);
    assert(result.stage==WAFFLE_LOG_COMPLETE);
    unsigned total=calls;
    for(unsigned failure=1;failure<=total;failure++) {
        reset(failure,0); waffle_sahara_logs(&io,entries,&result);
        assert(resets==1 && result.pages<=5);
        if(failure<total-1) assert(result.pages<5 || !result.reset_sent);
        const unsigned stages[]={WAFFLE_LOG_HELLO,WAFFLE_LOG_HELLO_REPLY,
            WAFFLE_LOG_DEBUG_HEADER,WAFFLE_LOG_TABLE_REQUEST,WAFFLE_LOG_TABLE_READ};
        unsigned expected=failure<=5?stages[failure-1]:failure<=20?
            WAFFLE_LOG_PAGE_REQUEST+(failure-6)%3:WAFFLE_LOG_COMPLETE;
        assert(result.stage==expected);
    }
    reset(0,512); assert(waffle_sahara_logs(&io,entries,&result)); assert(result.pages==5);
    reset(0,8); assert(!waffle_sahara_logs(&io,entries,&result)); assert(resets==1);
    assert(result.stage==WAFFLE_LOG_PAGE_READ);
    bad_hello=1;reset(0,0);assert(!waffle_sahara_logs(&io,entries,&result));assert(state==0 && resets==1);bad_hello=0;
    bad_table=1;reset(0,0);assert(!waffle_sahara_logs(&io,entries,&result));assert(state==1 && resets==1);bad_table=0;
    reset(0,0);entries[0].address=0xc300000;
    assert(!waffle_sahara_logs(&io,entries,&result) && !calls);
    assert(result.stage==WAFFLE_LOG_VALIDATE);
    assert(!strcmp(waffle_sahara_log_stage_name(WAFFLE_LOG_PAGE_READ),"page_read"));
    assert(!strcmp(waffle_sahara_log_stage_name(100),"invalid"));
    return 0;
}
