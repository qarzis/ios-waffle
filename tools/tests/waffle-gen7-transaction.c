#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_gen7_config.h"
enum { SIZE=0x27c00, COUNT=sizeof(waffle_gen7_disabled_setup)/sizeof(waffle_gen7_disabled_setup[0]) };
static uint32_t registers[SIZE],before[SIZE];
static unsigned writes,fail_at,restore_fail,failed_once;
static int exercise_mode;
static bool gx_off;
static unsigned reads;
static int exercise(void *context)
{
    (void)context;
    if (exercise_mode==98) { registers[0x808]=1;return -2; }
    if (exercise_mode==99) { registers[0x808]=1;return 0; }
    return exercise_mode;
}
static uint32_t readable_mask(uint32_t index)
{
    return index==0x50b ? 0x002f7fffu : index==0xe0d ? 0xfffff000u : 0xffffffffu;
}
static uint32_t read_register(void *context,uint32_t index)
{
    (void)context;assert(index<SIZE && waffle_gen7_index_allowed(index));
    assert(!gx_off || index>=0x1a000u);
    ++reads;
    if (!failed_once && writes && writes==fail_at && index==waffle_gen7_disabled_setup[writes-1].index) {
        failed_once=1;
        uint32_t mask=waffle_gen7_disabled_setup[writes-1].readback_mask;
        return registers[index]^(mask&-mask);
    }
    return registers[index];
}
static void write_register(void *context,uint32_t index,uint32_t value)
{
    (void)context;assert(index<SIZE && waffle_gen7_index_allowed(index));
    assert(!gx_off || index>=0x1a000u);
    assert(index!=0x808 && index!=0x806 && index!=0x807);
    ++writes;
    if (restore_fail && failed_once && writes>fail_at && index==waffle_gen7_disabled_setup[fail_at-1].index) return;
    registers[index]=value&readable_mask(index);
}
static void reset(unsigned failure,bool bad_restore)
{
    for (unsigned i=0;i<SIZE;++i) registers[i]=0x13579bdfu^(i*0x10001u);
    registers[0x808]=registers[0x806]=registers[0x807]=0;
    registers[0x50b]&=0x002f7fff;
    registers[0xe0d]&=0xfffff000;
    memcpy(before,registers,sizeof(before));
    writes=failed_once=reads=0;fail_at=failure;restore_fail=bad_restore;gx_off=false;
}
int main(void)
{
    struct waffle_gen7_io io={NULL,read_register,write_register,NULL,NULL};
    uint32_t native_image[154],native_index=0;
    struct waffle_gen7_config_state native_state={.native_trusted_window=true};
    reset(0,false);
    assert(!waffle_gen7_config_begin(&io,&native_state,native_image,154,&native_index));
    assert(registers[0xf800]==0xf0000000 && registers[0xf802]==0xfffff000);
    assert(!waffle_gen7_config_finish(&io,&native_state,&native_index));
    assert(!memcmp(registers,before,sizeof(before)));
    for(unsigned failure=1;failure<=COUNT;failure++) {
        reset(failure,false);
        struct waffle_gen7_config_state failure_state={.native_trusted_window=true};
        assert(waffle_gen7_config_begin(&io,&failure_state,native_image,154,&native_index)==-2);
        assert(!waffle_gen7_config_finish(&io,&failure_state,&native_index));
        assert(!memcmp(registers,before,sizeof(before)));
    }
    uint32_t image[155],index=0;
    reset(0,false);image[154]=0x12345678;
    assert(!waffle_gen7_config_probe(&io,image,154,&index));
    assert(!memcmp(registers,before,sizeof(before)) && writes==2*COUNT);
    assert(!image[0] && !image[1] && !image[2] && image[3]==0x113a && image[154]==0x12345678);
    for (unsigned i=0;i<75;++i) {
        uint32_t reg=i<58?waffle_gen7_ifpc_restore[i]:waffle_gen7_preemption_restore[i-58];
        uint32_t expected=before[reg];
        for (unsigned j=0;j<COUNT;++j) {
            const struct waffle_gen7_write *r=&waffle_gen7_disabled_setup[j];
            if (r->index==reg) expected=(expected&~r->mask)|(r->value&r->mask);
        }
        assert(image[4+2*i]==reg && image[5+2*i]==(expected&readable_mask(reg)));
    }
    for (unsigned i=1;i<=COUNT;++i) {
        reset(i,false);
        assert(waffle_gen7_config_probe(&io,image,154,&index)==-2);
        assert(index==waffle_gen7_disabled_setup[i-1].index && writes==2*i);
        assert(!memcmp(registers,before,sizeof(before)));
    }
    reset(1,true);
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-3);
    reset(0,false);
    assert(waffle_gen7_config_probe(&io,image,153,&index)==-1 && !writes);
    registers[0x808]=1;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-1 && !writes);
    registers[0x808]=0;registers[0x807]=1;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-1 && !writes);
    io.exercise=exercise;
    reset(0,false);exercise_mode=0;
    assert(!waffle_gen7_config_probe(&io,image,154,&index) && writes==2*COUNT);
    reset(0,false);exercise_mode=-2;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-4 && writes==2*COUNT);
    assert(!memcmp(registers,before,sizeof(before)));
    reset(0,false);exercise_mode=-3;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-3 && writes==COUNT);
    reset(0,false);exercise_mode=99;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-3 && index==0x808 && writes==COUNT);
    reset(0,false);exercise_mode=98;
    assert(waffle_gen7_config_probe(&io,image,154,&index)==-3 && index==0x808 && writes==COUNT);
    io.exercise=NULL;
    struct waffle_gen7_config_state state={0};
    reset(0,false);
    assert(!waffle_gen7_config_begin(&io,&state,image,154,&index));
    assert(state.phase==WAFFLE_GEN7_READY && writes==COUNT);
    assert(!waffle_gen7_config_submitting(NULL));
    assert(!waffle_gen7_config_stopped(&state,63));
    unsigned old_reads=reads,old_writes=writes;
    assert(waffle_gen7_config_begin(&io,&state,image,154,&index)==-1);
    assert(reads==old_reads && writes==old_writes);
    assert(waffle_gen7_config_submitting(&state));
    assert(!waffle_gen7_config_submitting(&state));
    /* Timeout/rejected ACK must not allow rollback or resource reclamation. */
    assert(waffle_gen7_config_finish(&io,&state,&index)==-3);
    assert(reads==old_reads && writes==old_writes && state.phase==WAFFLE_GEN7_SUBMITTED);
    for (unsigned flags=0;flags<63;++flags) {
        assert(!waffle_gen7_config_stopped(&state,flags));
        assert(state.phase==WAFFLE_GEN7_SUBMITTED);
    }
    assert(!waffle_gen7_config_stopped(&state,127));
    assert(waffle_gen7_config_stopped(&state,63));
    gx_off=true; /* Any access to GX MMIO now aborts the test. */
    assert(!waffle_gen7_config_finish(&io,&state,&index));
    assert(state.phase==WAFFLE_GEN7_RELEASED);
    unsigned ao_count=0;
    for (unsigned i=0;i<COUNT;++i) {
        const struct waffle_gen7_write *r=&waffle_gen7_disabled_setup[i];
        if (r->index>=0x1a000) {
            ++ao_count;
            assert(registers[r->index]==before[r->index]);
        }
    }
    assert(ao_count>0 && writes==old_writes+ao_count);
    old_reads=reads;old_writes=writes;
    assert(waffle_gen7_config_finish(&io,&state,&index)==-3);
    assert(waffle_gen7_config_begin(&io,&state,image,154,&index)==-1);
    assert(reads==old_reads && writes==old_writes);
    /* Restore errors in AO after collapse retain the snapshot/resources. */
    state=(struct waffle_gen7_config_state){0};reset(0,false);
    assert(!waffle_gen7_config_begin(&io,&state,image,154,&index));
    assert(waffle_gen7_config_submitting(&state));
    assert(waffle_gen7_config_stopped(&state,63));
    gx_off=true;
    for (unsigned i=0;i<COUNT;++i) if (waffle_gen7_disabled_setup[i].index>=0x1a000) {
        fail_at=i+1;restore_fail=failed_once=1;break;
    }
    assert(waffle_gen7_config_finish(&io,&state,&index)==-3);
    assert(state.phase==WAFFLE_GEN7_RETAINED);
    old_reads=reads;old_writes=writes;
    assert(waffle_gen7_config_finish(&io,&state,&index)==-3);
    assert(!waffle_gen7_config_submitting(&state));
    assert(!waffle_gen7_config_stopped(&state,63));
    assert(reads==old_reads && writes==old_writes);
    /* Partial setup failure may be unwound before any submission. */
    for (unsigned i=1;i<=COUNT;++i) {
        state=(struct waffle_gen7_config_state){0};reset(i,false);
        assert(waffle_gen7_config_begin(&io,&state,image,154,&index)==-2);
        assert(state.phase==WAFFLE_GEN7_CONFIGURING);
        assert(!waffle_gen7_config_submitting(&state));
        assert(!waffle_gen7_config_finish(&io,&state,&index));
        assert(state.phase==WAFFLE_GEN7_RELEASED && !memcmp(registers,before,sizeof(before)));
    }
    puts("Gen7: 92 failure rollbacks, 616-byte list, failed-exercise CP guard, split submission/collapse lifecycle, all63 missing-evidence cases and zero GX MMIO after collapse passed");
    return 0;
}
