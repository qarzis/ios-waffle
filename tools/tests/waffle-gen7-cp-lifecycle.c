#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_gen7_cp.h"
struct model {
    struct waffle_gen7_config_state *state;
    bool prepared,prepare_ok,ack,cp_live,thread_only;
    unsigned exchanges,waits,polls,idle_after;
};
static uint32_t read_register(void *context,uint32_t index)
{
    struct model *m=context;
    if (index==0x808) return m->cp_live;
    assert(index==0x23b0c && m->state->phase==WAFFLE_GEN7_SUBMITTED);
    ++m->polls;
    return 0x40000000u|(m->polls<=m->idle_after?1u<<23:0);
}
static bool prepare(void *context)
{
    struct model *m=context;
    assert(m->state->phase==WAFFLE_GEN7_READY && !m->exchanges);
    m->prepared=true;
    return m->prepare_ok;
}
static bool exchange(void *context,const uint32_t *packet,unsigned words,bool zero_ack)
{
    struct model *m=context;
    assert(m->prepared && m->state->phase==WAFFLE_GEN7_SUBMITTED);
    assert(words==(m->thread_only?3u:11u) && !zero_ack && packet[0]==((34u<<20)|(words<<8)|131u));
    uint32_t expected[11];
    assert(waffle_hfi_cp_init_packet(expected,11,34,0x80070000)==11);
    if (m->thread_only) expected[0]=(34u<<20)|(3u<<8)|131u;
    assert(!memcmp(packet,expected,words*sizeof(uint32_t)));
    ++m->exchanges;
    return m->ack;
}
static void delay_us(void *context,unsigned usec)
{
    struct model *m=context;
    assert(m->state->phase==WAFFLE_GEN7_SUBMITTED && usec==100);
    ++m->waits;
}
static void reset(struct model *m,struct waffle_gen7_config_state *state,unsigned idle_after)
{
    *state=(struct waffle_gen7_config_state){.phase=WAFFLE_GEN7_READY};
    *m=(struct model){.state=state,.prepare_ok=true,.ack=true,.idle_after=idle_after};
}
int main(void)
{
    struct waffle_gen7_config_state state={0};
    struct model m={0};
    const struct waffle_gen7_io registers={.context=&m,.read=read_register};
    const struct waffle_gen7_cp_io io={&registers,prepare,exchange,delay_us};
    struct waffle_gen7_cp_result result;
    /* ACK is followed by native BIT23 idle polling, including the last allowed
     * read at200ms. State never becomes releasable based on CP idle alone. */
    unsigned cases[]={0,1,1999,2000,2001};
    for (unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        reset(&m,&state,cases[i]);
        int rc=waffle_gen7_cp_submit(&io,&state,34,0x80070000,&result);
        assert(rc==(cases[i]<=2000?0:-3));
        assert(result.acknowledged && m.exchanges==1 && state.phase==WAFFLE_GEN7_SUBMITTED);
        assert(result.polls==m.polls && m.polls==m.waits+1 && m.waits<=2000);
        assert(m.waits==(cases[i]<=2000?cases[i]:2000));
        assert(!waffle_gen7_config_submitting(&state));
        assert(waffle_gen7_cp_submit(&io,&state,34,0x80070000,&result)==-1);
        assert(m.exchanges==1);
    }
    reset(&m,&state,0);m.ack=false;
    assert(waffle_gen7_cp_submit(&io,&state,34,0x80070000,&result)==-2);
    assert(!result.acknowledged && !m.polls && !m.waits && m.exchanges==1);
    assert(state.phase==WAFFLE_GEN7_SUBMITTED); /* Includes missing/rejected ACK. */
    reset(&m,&state,0);m.prepare_ok=false;
    assert(waffle_gen7_cp_submit(&io,&state,34,0x80070000,&result)==-1);
    assert(state.phase==WAFFLE_GEN7_READY && m.prepared && !m.exchanges && !m.polls);
    reset(&m,&state,0);m.cp_live=true;
    assert(waffle_gen7_cp_submit(&io,&state,34,0x80070000,&result)==-4);
    assert(state.phase==WAFFLE_GEN7_RETAINED && !m.prepared && !m.exchanges);
    reset(&m,&state,0);
    assert(waffle_gen7_cp_submit(&io,&state,0,0x80070000,&result)==-1);
    assert(waffle_gen7_cp_submit(&io,&state,34,0x80070001,&result)==-1);
    assert(waffle_gen7_cp_submit(NULL,&state,34,0x80070000,&result)==-1);
    assert(waffle_gen7_cp_submit(&io,NULL,34,0x80070000,&result)==-1);
    assert(waffle_gen7_cp_submit(&io,&state,34,0x80070000,NULL)==-1);
    assert(!m.prepared && !m.exchanges && state.phase==WAFFLE_GEN7_READY);
    reset(&m,&state,0);m.thread_only=true;
    assert(!waffle_gen7_cp_thread_submit(&io,&state,34,&result));
    assert(state.phase==WAFFLE_GEN7_SUBMITTED && m.exchanges==1 && result.acknowledged);
    reset(&m,&state,0);m.thread_only=true;m.ack=false;
    assert(waffle_gen7_cp_thread_submit(&io,&state,34,&result)==-2);
    assert(state.phase==WAFFLE_GEN7_SUBMITTED && m.exchanges==1 && !result.acknowledged);
    reset(&m,&state,2001);m.thread_only=true;
    assert(waffle_gen7_cp_thread_submit(&io,&state,34,&result)==-3 && m.waits==2000);
    reset(&m,&state,0);
    assert(waffle_gen7_cp_submit_kind(&io,&state,34,0x80070000,&result,99)==-1);
    assert(!m.exchanges && !m.prepared && state.phase==WAFFLE_GEN7_READY);
    puts("Gen7 CP lifecycle: native RAW packet/ACK policy, publication ordering, idle boundaries, timeout/rejection retention and preflight passed");
}
