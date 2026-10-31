#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_gen7_boot.h"
enum { SIZE=0x27c00 };
static uint32_t regs[SIZE],initial[SIZE],image[155];
static struct waffle_gen7_boot_state boot;
static unsigned reads,writes,exchanges,delays;
static uint32_t fail_index;
static bool global_va;
static bool fail_pending,failed,gx_off,clock_timeout,prepare_ok,ack_ok,cp_timeout,restore_bad,thread_only;
static uint32_t mask(uint32_t index)
{
    return index==0x50b?0x002f7fff:index==0xe0d?0xfffff000:0xffffffff;
}
static uint32_t read_reg(void *context,uint32_t index)
{
    (void)context;assert(index<SIZE && (!gx_off || index>=0x1a000));++reads;
    assert(index!=WAFFLE_GEN7_RBBM_CGC_GLOBAL_LOAD_CMD);
    if (fail_pending && index==fail_index) { fail_pending=false;failed=true;uint32_t bits=mask(index);
        for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i) if (waffle_gen7_disabled_setup[i].index==index) bits=waffle_gen7_disabled_setup[i].readback_mask;
        return regs[index]^(bits&-bits); }
    if (index==WAFFLE_GEN7_RBBM_CGC_P2S_STATUS) return clock_timeout?0:3;
    if (index==0x23b0c) return cp_timeout?1u<<23:0;
    return regs[index];
}
static void write_reg(void *context,uint32_t index,uint32_t value)
{
    (void)context;assert(index<SIZE && (!gx_off || index>=0x1a000));++writes;
    assert(index!=0x808 && index!=0x806 && index!=0x807 && index!=0x38);
    if (restore_bad && gx_off && index==waffle_gen7_ao_hwcg[0].index) return;
    regs[index]=value&mask(index);
    if (index==fail_index && !failed) fail_pending=true;
}
static bool prepare(void *context)
{
    (void)context;
    assert(boot.config.phase==WAFFLE_GEN7_READY && !exchanges);
    assert(regs[0x830]==0x80010000 && regs[0x831]==(global_va?0x1ff80u:0u) && regs[0xb70]==0x80030000 && regs[0xb71]==(global_va?0x1ff80u:0u));
    assert(boot.clocks.phase==WAFFLE_GEN7_HWCG_ACTIVE && boot.clock_status==3);
    assert(!regs[WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL] && image[3]==0x113a);
    return prepare_ok;
}
static bool exchange(void *context,const uint32_t *packet,unsigned words,bool zero_ack)
{
    (void)context;assert(boot.config.phase==WAFFLE_GEN7_SUBMITTED && words==(thread_only?3u:11u) && !zero_ack);
    assert(packet[0]==((34u<<20)|(words<<8)|131u));
    if (!thread_only) assert(packet[9]==(global_va?0x1ff80u:0u) && packet[8]==0x80070000);
    else assert(packet[1]==0x70970001 && packet[2]==(1u<<27));
    ++exchanges;regs[0x808]=1;return ack_ok;
}
static void delay_us(void *context,unsigned usec) { (void)context;assert(usec==1 || usec==100);++delays; }
static const struct waffle_gen7_io registers={NULL,read_reg,write_reg,NULL,NULL};
static const struct waffle_gen7_cp_io io={&registers,prepare,exchange,delay_us};
static void reset(void)
{
    memset(&boot,0,sizeof(boot));
    for (unsigned i=0;i<SIZE;++i) regs[i]=(0x13579bdf^(i*0x10001))&mask(i);
    regs[0x808]=regs[0x806]=regs[0x807]=regs[0x38]=regs[WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL]=0;
    memcpy(initial,regs,sizeof(regs));
    global_va=false;
    reads=writes=exchanges=delays=0;fail_index=0xffffffff;
    fail_pending=failed=gx_off=clock_timeout=cp_timeout=restore_bad=thread_only=false;
    prepare_ok=ack_ok=true;image[154]=0x5a5a5a5a;
}
static int start(void)
{
    int result=waffle_gen7_boot_start(&io,&boot,image,154,0x80010000,0x80030000,0x80070000,34);
    assert(image[154]==0x5a5a5a5a);return result;
}
static void cancelled(void)
{
    assert(!waffle_gen7_boot_finish(&registers,&boot));
    assert(boot.config.phase==WAFFLE_GEN7_RELEASED && !exchanges);
    for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i) {
        uint32_t index=waffle_gen7_disabled_setup[i].index;assert(regs[index]==initial[index]);
    }
    for (unsigned i=0;i<3;++i) assert(regs[waffle_gen7_ao_hwcg[i].index]==initial[waffle_gen7_ao_hwcg[i].index]);
    for (unsigned i=0;i<4;++i) assert(regs[waffle_gen7_ucode_indices[i]]==initial[waffle_gen7_ucode_indices[i]]);
}
static void collapsed(void)
{
    unsigned old_reads=reads,old_writes=writes;
    assert(waffle_gen7_boot_finish(&registers,&boot)==-3);
    assert(reads==old_reads && writes==old_writes);
    assert(waffle_gen7_config_stopped(&boot.config,63));gx_off=true;
    assert(waffle_gen7_boot_finish(&registers,&boot)==(restore_bad?-3:0));
    assert(boot.config.phase==(restore_bad?WAFFLE_GEN7_RETAINED:WAFFLE_GEN7_RELEASED));
    old_reads=reads;old_writes=writes;
    assert(waffle_gen7_boot_finish(&registers,&boot)==-3);
    assert(reads==old_reads && writes==old_writes);
}
int main(void)
{
    reset();
    assert(!waffle_gen7_boot_prepare(&io,&boot,image,154,0x80010000,0x80030000,0x80070000,34));
    assert(!exchanges && boot.config.phase==WAFFLE_GEN7_READY);
    assert(waffle_gen7_config_submitting(&boot.config));collapsed();
    reset();assert(!start() && exchanges==1 && boot.config.phase==WAFFLE_GEN7_SUBMITTED);collapsed();
    reset();global_va=true;
    assert(!waffle_gen7_boot_start(&io,&boot,image,154,waffle_gpu_global_alias(0x80010000),
        waffle_gpu_global_alias(0x80030000),waffle_gpu_global_alias(0x80070000),34));
    assert(exchanges==1);collapsed();
    reset();ack_ok=false;assert(start()==-5 && boot.detail==-2 && exchanges==1);collapsed();
    reset();cp_timeout=true;assert(start()==-5 && boot.detail==-3 && boot.cp.polls==2001);collapsed();
    reset();assert(!start());restore_bad=true;collapsed();
    reset();prepare_ok=false;assert(start()==-5 && boot.detail==-1);cancelled();
    reset();clock_timeout=true;assert(start()==-3 && boot.detail==-2);cancelled();
    for (unsigned i=0;i<WAFFLE_GEN7_SETUP_COUNT;++i) {
        reset();fail_index=waffle_gen7_disabled_setup[i].index;
        assert(start()==-2 && boot.detail==-2);cancelled();
    }
    for (unsigned i=0;i<3;++i) {
        reset();fail_index=waffle_gen7_ao_hwcg[i].index;
        assert(start()==-3 && boot.detail==-2);cancelled();
    }
    for (unsigned i=0;i<4;++i) {
        reset();fail_index=waffle_gen7_ucode_indices[i];assert(start()==-4);cancelled();
    }
    reset();regs[0x38]=1;assert(start()==-1 && !writes && !exchanges);
    reset();assert(waffle_gen7_boot_start(&io,&boot,image,154,0,0x80030000,0x80070000,34)==-1 && !reads);
    reset();assert(waffle_gen7_boot_start(&io,&boot,image,153,0x80010000,0x80030000,0x80070000,34)==-1 && !reads);
    reset();thread_only=true;
    assert(!waffle_gen7_boot_thread_start(&io,&boot,image,154,0x80010000,0x80030000,0x80070000,34));
    assert(exchanges==1 && boot.cp.acknowledged);collapsed();
    reset();thread_only=true;ack_ok=false;
    assert(waffle_gen7_boot_thread_start(&io,&boot,image,154,0x80010000,0x80030000,0x80070000,34)==-5);
    assert(exchanges==1 && boot.config.phase==WAFFLE_GEN7_SUBMITTED);collapsed();
    puts("Gen7 boot integration: 99 setup/base/clock failures, prepare/ACK/idle errors, paired cleanup and zero GX access after collapse passed");
}
