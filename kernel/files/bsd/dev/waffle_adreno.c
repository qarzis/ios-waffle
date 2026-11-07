/* SM8650 / Adreno 750 bring-up. This first stage establishes register access;
 * it does not publish RedwoodGPU until memory, GMU and submission work.
 * Sources: OnePlus gpucc/gcc-pineapple.c, pineapple-v2-gpu.dtsi and gen7_reg.h.
 * See docs/waffle-gpu.md for revisions and the remaining hardware work.
 */
#include <kern/clock.h>
#include <vm/memory_types.h>
#include <vm/vm_kern.h>
#include <arm/memory_types.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <sys/waffle_gpu.h>
#include <sys/waffle_gpu_service.h>
#include <sys/waffle_smmu.h>
#include <sys/waffle_aop.h>
#include <sys/waffle_gpu_pll.h>
#include <sys/waffle_gmu_clock.h>
#include <sys/macan_dsp.h>

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern vm_offset_t ml_io_map_unmappable(vm_offset_t, vm_size_t, unsigned int);
extern void ml_io_unmap(vm_offset_t, vm_size_t);
extern void loader_log_putc(char);
extern void loader_return(void);
void waffle_adreno_init(void);
extern void waffle_smmu_probe(vm_offset_t, uint32_t, uint32_t, uint32_t, uint32_t, unsigned);

static void gpu_log(const char *fmt, ...) __printflike(1, 2);
static void gpu_log(const char *fmt, ...)
{
    char line[256]; va_list ap;
    va_start(ap, fmt); vsnprintf(line, sizeof(line), fmt, ap); va_end(ap);
    for (const char *p = line; *p; ++p) loader_log_putc(*p);
    printf("%s", line);
}
static uint32_t read_reg(vm_offset_t base, uint32_t offset)
{
    return *(volatile uint32_t *)(base + offset);
}
/* Read-only LLCC v5.0 baseline from stock/live pineapple DT. All offsets
 * match pinned llcc-qcom.c; no ACT_CTRL trigger or ACT_CLEAR is written. */
static void probe_llcc_snapshot(void)
{
    const vm_offset_t addresses[]={0x25034000u,0x25808000u,0x25820000u};
    vm_offset_t maps[3]={0};
    bool complete=false;
    for(unsigned i=0;i<3;i++) {
        maps[i]=ml_io_map_unmappable(addresses[i],0x4000,VM_WIMG_IO);
        if (!maps[i]) {
            gpu_log("waffle-gpu: LLCC61 map failed index=%u\n",i);
            goto cleanup;
        }
    }
    uint32_t common=read_reg(maps[0],0x0c);
    gpu_log("waffle-gpu: LLCC61 common_status0=%08x banks=%u\n",common,common>>28);
    for(unsigned i=0;i<2;i++) {
        unsigned sid=i?11:9;
        unsigned status=sid*0x1000-0x8000;
        gpu_log("waffle-gpu: LLCC61 sid=%u ctrl=%08x status=%08x attr0=%08x attr1=%08x attr2=%08x\n",
            sid,read_reg(maps[1],status),read_reg(maps[1],status+4),
            read_reg(maps[2],0x1000+sid*8),read_reg(maps[2],0x1004+sid*8),
            read_reg(maps[2],0x1100+sid*4));
    }
    complete=true;
cleanup:
    for(unsigned i=3;i>0;i--) if (maps[i-1]) ml_io_unmap(maps[i-1],0x4000);
    if (complete) gpu_log("waffle-gpu: LLCC61 read-only snapshot complete; no LLCC or GPU writes\n");
}
static void probe_aop_qmp(void)
{
    gpu_log("waffle-gpu: AOP QMP read-only preflight @%08x size=%x\n",
        WAFFLE_AOP_QMP_BASE, WAFFLE_AOP_QMP_SIZE);
    vm_offset_t base = ml_io_map_unmappable(WAFFLE_AOP_QMP_BASE,
        WAFFLE_AOP_QMP_MAP_SIZE, VM_WIMG_IO);
    if (!base) { gpu_log("waffle-gpu: AOP QMP map failed\n"); return; }
    struct waffle_aop_qmp_snapshot s = {
        .magic = read_reg(base, 0x00), .version = read_reg(base, 0x04),
        .their_link = read_reg(base, 0x0c), .their_link_ack = read_reg(base, 0x10),
        .their_channel = read_reg(base, 0x14), .their_channel_ack = read_reg(base, 0x18),
        .our_link = read_reg(base, 0x24), .our_link_ack = read_reg(base, 0x28),
        .our_channel = read_reg(base, 0x2c), .our_channel_ack = read_reg(base, 0x30),
        .our_box_size = read_reg(base, 0x34), .our_box = read_reg(base, 0x38),
    };
    gpu_log("waffle-gpu: AOP QMP magic=%08x version=%u box=%03x size=%u geometry=%u open=%u\n",
        s.magic, s.version, s.our_box, s.our_box_size,
        waffle_aop_qmp_geometry_valid(&s), waffle_aop_qmp_channel_open(&s));
    gpu_log("waffle-gpu: AOP QMP their link=%08x ack=%08x channel=%08x ack=%08x; ours link=%08x ack=%08x channel=%08x ack=%08x\n",
        s.their_link, s.their_link_ack, s.their_channel, s.their_channel_ack,
        s.our_link, s.our_link_ack, s.our_channel, s.our_channel_ack);
    ml_io_unmap(base, WAFFLE_AOP_QMP_MAP_SIZE);
    gpu_log("waffle-gpu: AOP QMP preflight complete; no mailbox or GPU writes\n");
}
static void write_reg(vm_offset_t base, uint32_t offset, uint32_t value)
{
    *(volatile uint32_t *)(base + offset) = value;
    __asm__ volatile("dsb sy" ::: "memory");
}
struct board_clock_owner;
struct board_power_owner {
    vm_offset_t allocation,gcc,cc;
    uint32_t saved_cfg;
    unsigned probe;
    bool cfg_changed,cx_acquired;
    struct board_clock_owner *child;
};
static struct board_power_owner *active_board_power;
static struct board_power_owner *probe_gpu_body(unsigned);
static bool board_power_exercise(struct board_power_owner *);
static bool board_power_end(struct board_power_owner *);
static void aop_gpu_task(void *arg)
{
    struct board_power_owner *s=probe_gpu_body(*(unsigned *)arg);
    if(s) {
        gpu_log("waffle-gpu: power component returned live to AOP caller\n");
        (void)board_power_exercise(s);
        (void)board_power_end(s);
    }
}
struct aop_channel_context { vm_offset_t qmp, ipcc; };
static uint32_t aop_channel_read(void *arg, uint32_t offset)
{
    struct aop_channel_context *c = arg;
    return read_reg(c->qmp, offset);
}
static void aop_channel_write(void *arg, uint32_t offset, uint32_t value)
{
    struct aop_channel_context *c = arg;
    write_reg(c->qmp, offset, value);
}
static void aop_channel_kick(void *arg)
{
    struct aop_channel_context *c = arg;
    write_reg(c->ipcc, 0x0c, 0); /* Stock DT: IPCC client AOP=0, signal=0. */
}
static bool aop_channel_wait(void *arg, uint32_t offset, uint32_t value)
{
    for (unsigned i = 0; i < 10000; ++i) {
        if (aop_channel_read(arg, offset) == value) return true;
        delay_for_interval(100, NSEC_PER_USEC);
    }
    return aop_channel_read(arg, offset) == value;
}
static void probe_aop_channel(unsigned probe)
{
    gpu_log("waffle-gpu: AOP channel%u begin acd=%u gpu_path=%u\n", probe, probe>=47, probe>=48);
    if (!lck_mtx_try_lock(&macan_aop_mailbox_lock)) {
        gpu_log("waffle-gpu: AOP channel46 shared mailbox busy\n"); return;
    }
    struct aop_channel_context c = {0};
    vm_offset_t ipcc_mapping = 0;
    c.qmp = ml_io_map_unmappable(WAFFLE_AOP_QMP_BASE, WAFFLE_AOP_QMP_MAP_SIZE, VM_WIMG_IO);
    ipcc_mapping = ml_io_map_unmappable(0x00404000, 0x4000, VM_WIMG_IO);
    if (ipcc_mapping) c.ipcc = ipcc_mapping + 0x2000;
    if (c.qmp && c.ipcc) {
        const struct waffle_aop_qmp_io io = {
            &c, aop_channel_read, aop_channel_write, aop_channel_kick, aop_channel_wait
        };
        enum waffle_aop_qmp_result result = waffle_aop_qmp_transaction_run(&io,probe>=47,probe>=48?aop_gpu_task:NULL,&probe);
        gpu_log("waffle-gpu: AOP channel%u result=%u channel=%08x ack=%08x link=%08x linkack=%08x\n",
            probe, result, read_reg(c.qmp,0x2c), read_reg(c.qmp,0x30),
            read_reg(c.qmp,0x24), read_reg(c.qmp,0x28));
    } else gpu_log("waffle-gpu: AOP channel46 map failed\n");
    if (ipcc_mapping) ml_io_unmap(ipcc_mapping,0x4000);
    if (c.qmp) ml_io_unmap(c.qmp,WAFFLE_AOP_QMP_MAP_SIZE);
    lck_mtx_unlock(&macan_aop_mailbox_lock);
    gpu_log("waffle-gpu: AOP channel%u cleanup complete\n", probe);
}
/* Heap top-level owner for the bounded session. The shared mutex is held
 * only for QMP transport, never across GMU boot, GPU execution or shutdown. */
struct aop_gpu_owner {
    vm_offset_t allocation,ipcc_mapping;
    struct aop_channel_context channel;
    struct waffle_aop_qmp_session transport;
    struct board_power_owner *child;
    bool locked,exercised,exercise_ok;
};
static struct aop_gpu_owner *active_aop_gpu;
static void aop_owner_stop(const char *reason)
{
    gpu_log("waffle-gpu: AOP_OWNER REBOOT REQUIRED: %s; retain owner and mappings\n",reason);
    loader_return();
    for(;;)delay_for_interval(1000,NSEC_PER_USEC);
}
static bool aop_owner_channel_valid(struct aop_gpu_owner *s)
{
    vm_offset_t q=s->channel.qmp;
    struct waffle_aop_qmp_snapshot v={
        .magic=read_reg(q,0),.version=read_reg(q,4),
        .our_box=read_reg(q,0x38),.our_box_size=read_reg(q,0x34),
        .our_link=read_reg(q,0x24),.our_link_ack=read_reg(q,0x28),
        .our_channel=read_reg(q,0x2c),.our_channel_ack=read_reg(q,0x30),
        .their_channel=read_reg(q,0x14),
    };
    return waffle_aop_qmp_channel_open(&v) &&
        v.our_box==s->transport.our_box && v.our_box_size==s->transport.our_box_size &&
        read_reg(q,0x0c)==WAFFLE_AOP_QMP_UP && read_reg(q,0x10)==WAFFLE_AOP_QMP_UP &&
        read_reg(q,0x18)==WAFFLE_AOP_QMP_UP && !read_reg(q,v.our_box);
}
static bool aop_gpu_owner_end(struct aop_gpu_owner *s)
{
    if(!s || active_aop_gpu!=s)return false;
    bool ok=false;
    if(s->child) {
        if(s->locked)aop_owner_stop("shared mutex held during child stop");
        ok=board_power_end(s->child) && s->exercise_ok;
        s->child=NULL;
    }
    if(!s->locked) {
        if(!lck_mtx_try_lock(&macan_aop_mailbox_lock))aop_owner_stop("shared transport busy at end");
        s->locked=true;
    }
    enum waffle_aop_qmp_result result=s->transport.result;
    if(s->transport.changed) {
        if(s->transport.opened && !aop_owner_channel_valid(s))
            aop_owner_stop("channel changed or foreign message pending");
        result=waffle_aop_qmp_session_end(&s->transport);
        if(!s->transport.restored || s->transport.changed)
            aop_owner_stop("ACD or channel restoration unconfirmed");
    }
    lck_mtx_unlock(&macan_aop_mailbox_lock);s->locked=false;
    if(s->ipcc_mapping)ml_io_unmap(s->ipcc_mapping,0x4000);
    if(s->channel.qmp)ml_io_unmap(s->channel.qmp,WAFFLE_AOP_QMP_MAP_SIZE);
    vm_offset_t allocation=s->allocation;
    active_aop_gpu=NULL;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    gpu_log("waffle-gpu: AOP_OWNER released after power child and channel restore result=%u transport=%u\n",
        ok && result==WAFFLE_AOP_QMP_OK,result);
    return ok && result==WAFFLE_AOP_QMP_OK;
}
static struct aop_gpu_owner *aop_gpu_owner_begin(unsigned probe)
{
    uint32_t requested=0;
    if(active_aop_gpu || probe!=94 ||
        !PE_parse_boot_argn("waffle_session",&requested,sizeof(requested)) || requested!=1)return NULL;
    vm_offset_t allocation=0;
    if(sizeof(struct aop_gpu_owner)>PAGE_SIZE || kmem_alloc(kernel_map,&allocation,PAGE_SIZE,
        KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)allocation;
    *s=(struct aop_gpu_owner){.allocation=allocation};active_aop_gpu=s;
    if(!lck_mtx_try_lock(&macan_aop_mailbox_lock)) {
        active_aop_gpu=NULL;kmem_free(kernel_map,allocation,PAGE_SIZE);return NULL;
    }
    s->locked=true;
    s->channel.qmp=ml_io_map_unmappable(WAFFLE_AOP_QMP_BASE,WAFFLE_AOP_QMP_MAP_SIZE,VM_WIMG_IO);
    s->ipcc_mapping=ml_io_map_unmappable(0x00404000,0x4000,VM_WIMG_IO);
    if(s->ipcc_mapping)s->channel.ipcc=s->ipcc_mapping+0x2000;
    if(!s->channel.qmp || !s->channel.ipcc)goto failed;
    const struct waffle_aop_qmp_io io={&s->channel,
        aop_channel_read,aop_channel_write,aop_channel_kick,aop_channel_wait};
    if(waffle_aop_qmp_session_begin(&io,&s->transport,true)!=WAFFLE_AOP_QMP_OK)goto failed;
    lck_mtx_unlock(&macan_aop_mailbox_lock);s->locked=false;
    s->child=probe_gpu_body(probe);
    if(!s->child)goto failed;
    gpu_log("waffle-gpu: AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1\n");
    return s;
failed:
    (void)aop_gpu_owner_end(s);
    return NULL;
}
static bool aop_gpu_owner_exercise(struct aop_gpu_owner *s)
{
    if(!s || active_aop_gpu!=s || !s->child || s->locked || s->exercised)return false;
    s->exercised=true;s->exercise_ok=board_power_exercise(s->child);
    return s->exercise_ok;
}
static void show(vm_offset_t base, uint32_t physical, const char *name, uint32_t off)
{
    /* Log BEFORE access as well: a synchronous external abort must be locatable. */
    gpu_log("waffle-gpu: read %s @%08x\n", name, physical + off);
    gpu_log("waffle-gpu: %s=%08x\n", name, read_reg(base, off));
}
static bool cx_is_on(vm_offset_t cc)
{
    return ((read_reg(cc, WAFFLE_GPU_CX_GDSCR) |
        read_reg(cc, WAFFLE_GPU_CX_HW_CTRL)) & (1u << 31)) != 0;
}
static bool wait_mask(vm_offset_t base, uint32_t off, uint32_t mask, uint32_t value)
{
    for (unsigned i = 0; i < 100; ++i) {
        if ((read_reg(base, off) & mask) == value) return true;
        delay_for_interval(100, NSEC_PER_USEC);
    }
    return false;
}
struct clock_change {
    vm_offset_t base;
    uint32_t offset, mask, saved;
    bool rcg;
};
static bool clock_change(struct clock_change *c, vm_offset_t base, uint32_t offset,
    uint32_t mask, uint32_t value, bool rcg)
{
    c->base = base; c->offset = offset; c->mask = 0; c->rcg = false;
    if (rcg && !wait_mask(base, offset - 4, 1, 0)) return false;
    c->mask = mask; c->rcg = rcg;
    c->saved = read_reg(base, offset);
    write_reg(base, offset, (c->saved & ~mask) | (value & mask));
    if (!rcg) return true;
    uint32_t cmd = offset - 4;
    write_reg(base, cmd, read_reg(base, cmd) | 1);
    return wait_mask(base, cmd, 1, 0);
}
static struct waffle_smmu_owner *probe_smmu(uint32_t probe)
{
    vm_offset_t smmu = ml_io_map(WAFFLE_GPU_SMMU_BASE, WAFFLE_GPU_SMMU_SIZE);
    if (!smmu) { gpu_log("waffle-gpu: SMMU map failed\n"); return NULL; }
    show(smmu, WAFFLE_GPU_SMMU_BASE, "SMMU_IDR0", 0x20);
    show(smmu, WAFFLE_GPU_SMMU_BASE, "SMMU_IDR1", 0x24);
    show(smmu, WAFFLE_GPU_SMMU_BASE, "SMMU_IDR2", 0x28);
    uint32_t idr0 = read_reg(smmu, 0x20), idr1 = read_reg(smmu, 0x24);
    uint32_t page = (idr1 >> 31) ? 0x10000 : 0x1000;
    uint32_t pages = 2u << ((idr1 >> 28) & 7), contexts = idr1 & 255;
    uint32_t matches = idr0 & 255, context_base = pages * page;
    if (context_base > WAFFLE_GPU_SMMU_SIZE / 2 || contexts < 2 || contexts > 128 ||
        matches < 6 || matches > 128 || contexts > (WAFFLE_GPU_SMMU_SIZE - context_base) / page) {
        gpu_log("waffle-gpu: SMMU layout outside DT range: page=%x pages=%u CB=%u SMR=%u; stop\n",
            page, pages, contexts, matches);
        return NULL;
    }
    gpu_log("waffle-gpu: SMMU layout page=%x pages=%u CB=%u SMR=%u; read only\n",
        page, pages, contexts, matches);
    show(smmu, WAFFLE_GPU_SMMU_BASE, "SMMU_SCR0", 0);
    show(smmu, WAFFLE_GPU_SMMU_BASE, "SMMU_SGFSR", 0x48);
    for (unsigned i = 0; i < 6; ++i) {
        show(smmu, WAFFLE_GPU_SMMU_BASE, "SMR", 0x800 + i * 4);
        show(smmu, WAFFLE_GPU_SMMU_BASE, "S2CR", 0xc00 + i * 4);
    }
    for (unsigned i = 0; i < 2; ++i) {
        uint32_t cb = context_base + page * i;
        show(smmu, WAFFLE_GPU_SMMU_BASE, "CB_SCTLR", cb);
        show(smmu, WAFFLE_GPU_SMMU_BASE, "CB_TTBR0_LO", cb + 0x20);
        show(smmu, WAFFLE_GPU_SMMU_BASE, "CB_TTBR0_HI", cb + 0x24);
        show(smmu, WAFFLE_GPU_SMMU_BASE, "CB_TCR", cb + 0x30);
        show(smmu, WAFFLE_GPU_SMMU_BASE, "CB_FSR", cb + 0x58);
    }
    gpu_log("waffle-gpu: SMMU inspection complete; no translation registers written\n");
    uint32_t session=0;
    if(probe==94 && PE_parse_boot_argn("waffle_session",&session,sizeof(session)) && session==1)
        return waffle_smmu_owner_begin(smmu,page,pages,contexts,matches,probe);
    if (probe >= 6) waffle_smmu_probe(smmu, page, pages, contexts, matches, probe);
    return NULL;
}
/* GMU_FREQ_MIN in kgsl_gmu_core.h is 200MHz. Pineapple GMU parent map
 * selects existing GPLL0 (600MHz) with SRC_SEL5; HID divider3 encodes5.
 * This bounded experiment does not configure or calibrate GPU PLL1. */
static uint32_t pll92_power;
struct pll92_context {vm_offset_t cc;};
static uint32_t pll92_read(void *arg,unsigned offset)
{
    return read_reg(((struct pll92_context *)arg)->cc,offset);
}
static bool pll92_write(void *arg,unsigned offset,uint32_t value)
{
    if ((offset!=0x1000 && offset!=0x1004 &&
        (offset<0x1010 || offset>0x1038)) || (offset&3)) return false;
    write_reg(((struct pll92_context *)arg)->cc,offset,value);
    return true;
}
static bool pll92_wait(void *arg,unsigned offset,uint32_t mask,uint32_t value,unsigned us)
{
    for(unsigned i=0;i<us;i++) {
        if((pll92_read(arg,offset)&mask)==value)return true;
        delay_for_interval(1,NSEC_PER_USEC);
    }
    return (pll92_read(arg,offset)&mask)==value;
}
static void pll92_barrier(void *arg) {(void)arg;__asm__ volatile("dsb sy" ::: "memory");}
static void pll92_delay(void *arg,unsigned us) {(void)arg;delay_for_interval(us,NSEC_PER_USEC);}
static bool pll92_power_held(void *arg,unsigned cx,unsigned mx)
{
    (void)arg;return pll92_power==256 && cx<=256 && mx<=256;
}
static bool pll92_unused(void *arg)
{
    vm_offset_t cc=((struct pll92_context *)arg)->cc;
    /* These are the only Pineapple RCG parent maps containing PLL1/SRC3.
     * FF's parent map0 has XO/GPLL0 only. No RCG is switched to PLL1 here. */
    return (read_reg(cc,WAFFLE_GPU_GMU_RCGR+4)&0x700)!=0x300 &&
        (read_reg(cc,WAFFLE_GPU_HUB_RCGR+4)&0x700)!=0x300;
}
static bool probe_pll1(vm_offset_t cc,vm_offset_t gmu)
{
    if (!(read_reg(gmu,WAFFLE_GMU_SYSRESET)&1)) {
        gpu_log("waffle-gpu: PLL92 refused: CM3 not held reset\n");return false;
    }
    struct pll92_context context={cc};
    const struct waffle_pll1_io io={&context,pll92_read,pll92_write,pll92_wait,
        pll92_barrier,pll92_delay,pll92_power_held,pll92_unused};
    struct waffle_pll1_state state={0};
    gpu_log("waffle-gpu: PLL92 before MODE=%08x L=%08x ALPHA=%08x; CM3 reset\n",
        read_reg(cc,0x1000),read_reg(cc,0x1010),read_reg(cc,0x1014));
    bool ok=waffle_pll1_begin(&io,&state);
    if(ok) {
        gpu_log("waffle-gpu: PLL92 1250MHz locked MODE=%08x L=%08x ALPHA=%08x\n",
            read_reg(cc,0x1000),read_reg(cc,0x1010),read_reg(cc,0x1014));
        ok=waffle_pll1_rate(&io,&state,520000000ul);
        if(ok)gpu_log("waffle-gpu: PLL92 520MHz locked MODE=%08x L=%08x ALPHA=%08x\n",
            read_reg(cc,0x1000),read_reg(cc,0x1010),read_reg(cc,0x1014));
    }
    bool restored=waffle_pll1_restore(&io,&state);
    gpu_log("waffle-gpu: PLL92 scalar restore=%u owned=%u MODE=%08x L=%08x ALPHA=%08x\n",
        restored,state.owned,read_reg(cc,0x1000),read_reg(cc,0x1010),read_reg(cc,0x1014));
    if(!restored) {
        gpu_log("waffle-gpu: PLL92 REBOOT REQUIRED; retain CX clocks and firmware votes\n");
        loader_return();
        for(;;)delay_for_interval(1000,NSEC_PER_USEC);
    }
    return ok && restored;
}
static struct pll92_context native_clock_context;
static vm_offset_t native_clock_gmu;
static unsigned native_clock_probe;
static struct waffle_gmu_clock_state native_clock_state;
static const struct waffle_pll1_io native_pll_io={&native_clock_context,
    pll92_read,pll92_write,pll92_wait,pll92_barrier,pll92_delay,pll92_power_held,pll92_unused};
static uint32_t native_clock_root(void *arg)
{
    return read_reg(((struct pll92_context *)arg)->cc,WAFFLE_GPU_GMU_RCGR+4);
}
static bool native_clock_set_root(void *arg,uint32_t value)
{
    struct clock_change change={0};
    vm_offset_t cc=((struct pll92_context *)arg)->cc;
    return clock_change(&change,cc,WAFFLE_GPU_GMU_RCGR+4,0x71f,value,true) &&
        (read_reg(cc,WAFFLE_GPU_GMU_RCGR+4)&0x71f)==value;
}
static bool native_clock_cm3_reset(void *arg)
{
    (void)arg;return (read_reg(native_clock_gmu,WAFFLE_GMU_SYSRESET)&1)!=0;
}
static bool native_clock_gx_off(void *arg)
{
    return !(read_reg(((struct pll92_context *)arg)->cc,WAFFLE_GPU_GX_GDSCR)&(1u<<31));
}
static const struct waffle_gmu_clock_io native_clock_io={&native_pll_io,
    &native_clock_context,native_clock_root,native_clock_set_root,native_clock_cm3_reset,native_clock_gx_off};
bool waffle_gpu_native_runtime_clock(unsigned probe)
{
    if((probe!=93 && probe!=94) || probe!=native_clock_probe || !waffle_gmu_clock_runtime(&native_clock_io,&native_clock_state))return false;
    gpu_log("waffle-gpu: NATIVE%u runtime GMU260 PLL520 CFG=%08x MODE=%08x L=%08x ALPHA=%08x\n",
        probe,native_clock_root(&native_clock_context),pll92_read(&native_clock_context,0x1000),
        pll92_read(&native_clock_context,0x1010),pll92_read(&native_clock_context,0x1014));
    return true;
}
static void native_clock_reboot_required(void)
{
    gpu_log("waffle-gpu: NATIVE%u REBOOT REQUIRED; retain PLL, CX clocks and firmware votes\n",native_clock_probe);
    loader_return();
    for(;;)delay_for_interval(1000,NSEC_PER_USEC);
}
static uint32_t gmu_clock_config(unsigned probe)
{
    return probe>=88 ? 0x505u : 1u;
}
struct board_clock_owner {
    vm_offset_t gcc,cc,allocation;
    unsigned probe,count;
    struct clock_change saved[16];
    struct waffle_smmu_owner *child;
    bool ok,pll_passed,exercised,released;
};
/* Native clock callbacks above have module lifetime. Serialize their use;
 * the active owner retains their journal and SMMU child until finish. */
static struct board_clock_owner *active_board_clocks;
static bool board_clock_begin(struct board_clock_owner *s)
{
    if(active_board_clocks)return false;
    active_board_clocks=s;
    vm_offset_t gcc=s->gcc,cc=s->cc;
    unsigned probe=s->probe,count=0;
    struct clock_change *saved=s->saved;
    bool ok=true,pll_passed=false;
    /* Use GPLL0's existing 600MHz parent for the documented 200MHz hub;
     * keep the GMU at XO (19.2MHz). No GPU PLL or rail programming here.
     * Every changed field is recorded before the write, including a failed RCG.
     */
    clock_change(&saved[count++], gcc, WAFFLE_GPU_PLL_VOTE,
        WAFFLE_GPU_PLL_MASK, WAFFLE_GPU_PLL_MASK, false);
    const uint32_t roots[] = { WAFFLE_GPU_CXO_AON, WAFFLE_GPU_DEMET };
    for (unsigned i = 0; i < sizeof(roots)/sizeof(roots[0]); ++i)
        clock_change(&saved[count++], cc, roots[i], 1, 1, false);
    if (!clock_change(&saved[count++], cc, WAFFLE_GPU_GMU_RCGR + 4,
            0x71f, gmu_clock_config(probe), true)) { gpu_log("waffle-gpu: GMU clock-source update timed out\n"); ok = false; }
    if (ok && !clock_change(&saved[count++], cc, WAFFLE_GPU_HUB_RCGR + 4,
            0x71f, 0x505, true)) { gpu_log("waffle-gpu: HUB clock-source update timed out\n"); ok = false; }
    const uint32_t branches[] = { WAFFLE_GPU_CXO, WAFFLE_GPU_HUB_AON,
        WAFFLE_GPU_HUB_CX_INT, WAFFLE_GPU_AHB, WAFFLE_GPU_CX_GMU };
    if (ok) {
        for (unsigned i = 0; i < sizeof(branches)/sizeof(branches[0]); ++i) {
            uint32_t off = branches[i];
            clock_change(&saved[count++], cc, off, 1, 1, false);
            if (!wait_mask(cc, off, 1u << 31, 0)) {
                gpu_log("waffle-gpu: clock @%08x stays halted (%08x)\n",
                    WAFFLE_GPUCC_BASE + off, read_reg(cc, off));
                ok = false;
                break;
            }
        }
    }
    if (ok && probe>=88 && (read_reg(cc,WAFFLE_GPU_GMU_RCGR+4)&0x71f)!=0x505) {
        gpu_log("waffle-gpu: GMU 200MHz clock readback refused; no GMU/SMMU access\n");
        ok=false;
    }
    if (ok) {
        uint32_t cfg=read_reg(cc,WAFFLE_GPU_GMU_RCGR+4);
        gpu_log("waffle-gpu: CX clocks ready; GMU %s, hub 200MHz requested; GMU_CFG=%08x valid=%u\n",
            probe>=88?"200MHz GPLL0":"XO",cfg,ok);
        vm_offset_t gmu = ml_io_map(WAFFLE_GMU_BASE, WAFFLE_GMU_SIZE);
        if (gmu) {
            show(gmu, WAFFLE_GMU_BASE, "CM3_SYSRESET", WAFFLE_GMU_SYSRESET);
            show(gmu, WAFFLE_GMU_BASE, "CM3_FW_INIT_RESULT", WAFFLE_GMU_FW_INIT);
            uint32_t before = read_reg(gmu, WAFFLE_GMU_COUNTER);
            delay_for_interval(1000, NSEC_PER_USEC);
            uint32_t after = read_reg(gmu, WAFFLE_GMU_COUNTER);
            gpu_log("waffle-gpu: CX AO counter %08x -> %08x delta=%u (1000us interval)\n",
                before, after, after - before);
            if(probe==92)pll_passed=probe_pll1(cc,gmu);
            if(probe==93 || probe==94) {
                native_clock_context.cc=cc;native_clock_gmu=gmu;native_clock_probe=probe;
                ok=waffle_gmu_clock_start(&native_clock_io,&native_clock_state);
                gpu_log("waffle-gpu: NATIVE%u startup GMU625 PLL1250 ready=%u CFG=%08x MODE=%08x L=%08x ALPHA=%08x\n",
                    probe,ok,native_clock_root(&native_clock_context),read_reg(cc,0x1000),read_reg(cc,0x1010),read_reg(cc,0x1014));
            }
        } else {gpu_log("waffle-gpu: GMU mapping failed\n");if(probe==93 || probe==94)ok=false;}
    }
    if (ok && probe >= 5 && probe!=92) {
        const uint32_t buses[] = { WAFFLE_GPU_MEMNOC, WAFFLE_GPU_DDR_AXI };
        for (unsigned i = 0; i < sizeof(buses)/sizeof(buses[0]); ++i) {
            clock_change(&saved[count++], gcc, buses[i], 3, 1, false);
            if (!wait_mask(gcc, buses[i], 1u << 31, 0)) {
                gpu_log("waffle-gpu: SMMU bus clock halted @%x\n", buses[i]);
                ok = false;
                break;
            }
        }
        if (ok) {
            clock_change(&saved[count++], cc, WAFFLE_GPU_SMMU_CLOCK, 1, 1, false);
            if (probe >= 6) {
                /* Vendor GCC declares SNOC_DVM as BRANCH_HALT_DELAY. */
                clock_change(&saved[count++], gcc, WAFFLE_GPU_SNOC, 1, 1, false);
                delay_for_interval(10, NSEC_PER_USEC);
            }
            if (wait_mask(cc, WAFFLE_GPU_SMMU_CLOCK, 1u << 31, 0)) {
                s->child=probe_smmu(probe);
                if(s->child)gpu_log("waffle-gpu: SMMU component returned live to clock owner\n");
            }
            else gpu_log("waffle-gpu: SMMU clock halted; no SMMU reads\n");
        }
    }
    s->count=count;s->ok=ok;s->pll_passed=pll_passed;
    return ok;
}
static bool board_clock_exercise(struct board_clock_owner *s)
{
    if(active_board_clocks!=s || s->exercised)return false;
    s->exercised=true;
    if(s->child)s->ok=waffle_smmu_owner_exercise(s->child) && s->ok;
    return s->ok;
}
static bool board_clock_finish(struct board_clock_owner *s)
{
    if(active_board_clocks!=s)return false;
    if(s->child) {
        bool stopped=waffle_smmu_owner_end(s->child);
        s->child=NULL;s->ok=stopped && s->ok;
        gpu_log("waffle-gpu: SMMU component ended before clock restore result=%u\n",s->ok);
    }
    unsigned probe=s->probe,count=s->count;
    struct clock_change *saved=s->saved;
    bool ok=s->ok,pll_passed=s->pll_passed,native_passed=false,clocks_restored=true;
    if((probe==93 || probe==94) && native_clock_context.cc) {
        native_passed=native_clock_state.runtime;
        if(!waffle_gmu_clock_finish(&native_clock_io,&native_clock_state))native_clock_reboot_required();
        gpu_log("waffle-gpu: NATIVE%u detached and PLL scalar restore=1 owned=%u CFG=%08x\n",
            probe,native_clock_state.pll.owned,native_clock_root(&native_clock_context));
    }
    while (count) {
        struct clock_change *c = &saved[--count];
        if (!c->mask) continue;
        uint32_t current = read_reg(c->base, c->offset);
        write_reg(c->base, c->offset, (current & ~c->mask) | (c->saved & c->mask));
        if (c->rcg) {
            uint32_t cmd = c->offset - 4;
            write_reg(c->base, cmd, read_reg(c->base, cmd) | 1);
            if (!wait_mask(c->base, cmd, 1, 0)) {
                clocks_restored=false;
                gpu_log("waffle-gpu: WARNING: clock-source restore timed out @%x\n", c->offset);
            }
        }
    }
    gpu_log("waffle-gpu: clock controls restored\n");
    if(probe==92)gpu_log("waffle-gpu: PLL92 control passed=%u; no GMU firmware or CP started\n",
        ok && pll_passed && clocks_restored);
    if(probe==93)gpu_log("waffle-gpu: NATIVE93 clock control passed=%u; no CP RAW sent\n",
        ok && native_passed && clocks_restored);
    if(probe==94)gpu_log("waffle-gpu: NATIVE94 clock control passed=%u; GMU stopped and PLL restored\n",
        ok && native_passed && clocks_restored);
    if(!clocks_restored)native_clock_reboot_required();
    s->count=0;s->released=true;active_board_clocks=NULL;
    return ok && clocks_restored && (probe==92?pll_passed:probe>=93?native_passed:true);
}
static struct board_clock_owner *probe_clocks(vm_offset_t gcc,vm_offset_t cc,uint32_t probe)
{
    if(active_board_clocks){gpu_log("waffle-gpu: clock owner already active; no writes\n");return NULL;}
    struct board_clock_owner fallback={0},*s=&fallback;
    vm_offset_t allocation=0;uint32_t requested=0;
    bool heap=probe==94 && PE_parse_boot_argn("waffle_session",&requested,sizeof(requested)) && requested==1;
    if(heap) {
        if(sizeof(*s)>PAGE_SIZE || kmem_alloc(kernel_map,&allocation,PAGE_SIZE,
            KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
        s=(struct board_clock_owner *)allocation;
    }
    *s=(struct board_clock_owner){.gcc=gcc,.cc=cc,.probe=probe,.allocation=allocation};
    (void)board_clock_begin(s);
    if(heap && s->child) {
        gpu_log("waffle-gpu: CLOCK_OWNER begin returned heap=1 child_live=1 journal=%u\n",s->count);
        return s;
    }
    (void)board_clock_exercise(s);
    (void)board_clock_finish(s);
    if(allocation) {
        if(!s->released)native_clock_reboot_required();
        kmem_free(kernel_map,allocation,PAGE_SIZE);
    }
    return NULL;
}
static void probe_clock_session(vm_offset_t gcc,vm_offset_t cc,uint32_t probe)
{
    struct board_clock_owner *s=probe_clocks(gcc,cc,probe);
    if(!s)return;
    gpu_log("waffle-gpu: clock component returned live to CX caller\n");
    (void)board_clock_exercise(s);
    bool ok=board_clock_finish(s);
    if(!s->released)native_clock_reboot_required();
    vm_offset_t allocation=s->allocation;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    gpu_log("waffle-gpu: CLOCK_OWNER released before CX restore result=%u\n",ok);
}
static void probe_cx(vm_offset_t gcc, vm_offset_t cc, uint32_t probe, struct board_power_owner *owner)
{
    /* SM8650 gpu_cx_gdsc: SW_COLLAPSE bit0, PWR_ON bit31, status also
     * in HW_CTRL. Retain firmware's CLK_DIS_WAIT/retention fields. Do not
     * touch GX, resets, clocks, GMU or any SMMU context in this stage.
     */
    uint32_t saved = read_reg(cc, WAFFLE_GPU_CX_GDSCR);
    if (cx_is_on(cc)) {
        gpu_log("waffle-gpu: CX already powered; no power-control writes\n");
        if (probe >= 4) {
            if(owner)owner->child=probe_clocks(gcc,cc,probe);
            else probe_clock_session(gcc,cc,probe);
        }
        return;
    }
    if (!(saved & 1)) {
        gpu_log("waffle-gpu: CX collapse already deasserted but not powered; no writes\n");
        return;
    }
    gpu_log("waffle-gpu: deassert CX collapse; prior=%08x\n", saved);
    if(owner)owner->cx_acquired=true;
    write_reg(cc, WAFFLE_GPU_CX_GDSCR, saved & ~1u);
    bool powered = false;
    for (unsigned i = 0; i < 500; ++i) {
        if (cx_is_on(cc)) { powered = true; break; }
        delay_for_interval(100, NSEC_PER_USEC);
    }
    gpu_log("waffle-gpu: CX power %s; GDSCR=%08x HW_CTRL=%08x\n",
        powered ? "ON" : "timeout after 50ms", read_reg(cc, WAFFLE_GPU_CX_GDSCR),
        read_reg(cc, WAFFLE_GPU_CX_HW_CTRL));
    if (powered && probe >= 4) {
        if(owner)owner->child=probe_clocks(gcc,cc,probe);
        else probe_clock_session(gcc,cc,probe);
    }
    if(owner)return; /* Parent retains the collapse request until child end. */
    uint32_t current = read_reg(cc, WAFFLE_GPU_CX_GDSCR);
    write_reg(cc, WAFFLE_GPU_CX_GDSCR, current | 1);
    /* The vendor DT specifies no-status-check-on-disable for this votable
     * domain. Give the hardware time, but do not insist another client's vote
     * disappeared: restore only our own collapse request.
     */
    delay_for_interval(100, NSEC_PER_USEC);
    gpu_log("waffle-gpu: restored CX collapse=%u; power status=%u\n",
        read_reg(cc, WAFFLE_GPU_CX_GDSCR) & 1, cx_is_on(cc));
}
static bool board_power_exercise(struct board_power_owner *s)
{
    return s && s->child && board_clock_exercise(s->child);
}
static bool board_power_end(struct board_power_owner *s)
{
    if(!s || active_board_power!=s)return false;
    bool ok=false;
    if(s->child) {
        struct board_clock_owner *child=s->child;
        ok=board_clock_finish(child);
        if(!child->released)native_clock_reboot_required();
        vm_offset_t allocation=child->allocation;
        s->child=NULL;
        kmem_free(kernel_map,allocation,PAGE_SIZE);
        gpu_log("waffle-gpu: CLOCK_OWNER released before CX restore result=%u\n",ok);
    }
    if(s->cx_acquired) {
        uint32_t current=read_reg(s->cc,WAFFLE_GPU_CX_GDSCR);
        write_reg(s->cc,WAFFLE_GPU_CX_GDSCR,current|1);
        delay_for_interval(100,NSEC_PER_USEC);
        gpu_log("waffle-gpu: restored CX collapse=%u; power status=%u\n",
            read_reg(s->cc,WAFFLE_GPU_CX_GDSCR)&1,cx_is_on(s->cc));
    }
    if(s->cfg_changed) {
        uint32_t current=read_reg(s->gcc,WAFFLE_GPU_CFG_AHB);
        write_reg(s->gcc,WAFFLE_GPU_CFG_AHB,(current&~3u)|(s->saved_cfg&3));
        gpu_log("waffle-gpu: restored CFG_AHB enable/gating=%u\n",read_reg(s->gcc,WAFFLE_GPU_CFG_AHB)&3);
    }
    vm_offset_t allocation=s->allocation;
    active_board_power=NULL;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    gpu_log("waffle-gpu: POWER_OWNER released after clock child, CX and CFG restore result=%u\n",ok);
    return ok;
}
void waffle_adreno_init(void)
{
    uint32_t waffle = 0, probe = 0;
    if (!PE_parse_boot_argn("waffle", &waffle, sizeof(waffle)) || waffle != 1 ||
        !PE_parse_boot_argn("waffle_gpu", &probe, sizeof(probe)) || probe == 0) return;
    if (probe > 94) {
        gpu_log("waffle-gpu: unsupported stage %u; no MMIO access\n", probe);
        loader_return();
        return;
    }
    if (probe == 61) {
        probe_llcc_snapshot();
        loader_return();
        return;
    }
    if(probe==92 || probe==93 || probe==94) {
        if(!PE_parse_boot_argn("waffle_fw_cxmx",&pll92_power,sizeof(pll92_power)) || pll92_power!=256) {
            gpu_log("waffle-gpu: PLL%u firmware power proof missing; no MMIO access\n",probe);
            loader_return();return;
        }
        gpu_log("waffle-gpu: PLL%u verified firmware CX/MX256 handoff\n",probe);
        uint32_t image=0;
        if(probe==94 && PE_parse_boot_argn("waffle_image",&image,sizeof(image)) && (image==6 || image==7 || image==8 || image==10 || image==11 || image==12 || image==13)){
            if(!(image==13?waffle_gpu_drm_register():(image==11 || image==12)?waffle_gpu_msm_register():waffle_gpu_user_register()))loader_return();
            return;
        }
        if(probe==94 && PE_parse_boot_argn("waffle_image",&image,sizeof(image)) && image==5){
            (void)waffle_gpu_service_probe();loader_return();return;
        }
        uint32_t session=0;
        if(probe==92)probe_gpu_body(probe);
        else if(probe==94 && PE_parse_boot_argn("waffle_session",&session,sizeof(session)) && session==1) {
            struct aop_gpu_owner *owner=aop_gpu_owner_begin(probe);
            if(owner) {
                gpu_log("waffle-gpu: full GPU owner returned live to init caller; no mutex held\n");
                (void)aop_gpu_owner_exercise(owner);
                (void)aop_gpu_owner_end(owner);
            }
        } else probe_aop_channel(probe);
        loader_return();return;
    }
    if (probe >= 45 && probe <= 91) {
        if (probe >= 46) probe_aop_channel(probe);
        else probe_aop_qmp();
        loader_return();
        return;
    }
    probe_gpu_body(probe);
    loader_return();
}
static struct board_power_owner *probe_gpu_body(unsigned probe)
{
    if(active_board_power){gpu_log("waffle-gpu: power owner already active; no writes\n");return NULL;}
    struct board_power_owner *owner=NULL;
    uint32_t session=0;
    if(probe==94 && PE_parse_boot_argn("waffle_session",&session,sizeof(session)) && session==1) {
        vm_offset_t allocation=0;
        if(sizeof(*owner)>PAGE_SIZE || kmem_alloc(kernel_map,&allocation,PAGE_SIZE,
            KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
        owner=(struct board_power_owner *)allocation;
        *owner=(struct board_power_owner){.allocation=allocation,.probe=probe};
        active_board_power=owner;
    }
    gpu_log("waffle-gpu: Adreno750 Gen7.9.1 profile-chipid=%08x stage=%u; %s\n",
        WAFFLE_GPU_CHIP_ID, probe,(probe==35 || probe==36 || probe==80 || probe==82 || probe==85)?"polled CP thread-control only":
        (probe==33 || probe==38 || probe==40 || probe==42 || probe==44 || probe==49 || probe==51 || probe==53 || probe==55 || probe==57 || probe==59 || probe==64 || probe==66 || probe==86 || probe==89 || probe==91 || probe==94)?"polled CP init only":"no GPU command submission");
    vm_offset_t gcc = ml_io_map(WAFFLE_GCC_BASE, WAFFLE_GCC_SIZE);
    if (!gcc) {
        gpu_log("waffle-gpu: GCC map failed\n");
        if(owner)(void)board_power_end(owner);
        return NULL;
    }
    if(owner)owner->gcc=gcc;
    show(gcc, WAFFLE_GCC_BASE, "GPU_CFG_AHB_CBCR", WAFFLE_GPU_CFG_AHB);
    show(gcc, WAFFLE_GCC_BASE, "GPU_MEMNOC_GFX_CBCR", WAFFLE_GPU_MEMNOC);
    if (probe == 1) {
        gpu_log("waffle-gpu: stage 1 complete; no registers written\n");
        
        return NULL;
    }
    /* CBCR bit0 enables the branch; bit1 is hardware clock gating. Test the
     * branch with gating disabled, then restore BOTH control bits. The first
     * hardware run returned 80000003: enabled but halted, with gating set.
     * Read-modify-write retains every other control field.
     * No PLL, rail, reset, GMU, SMMU or TrustZone accesses in this stage.
     */
    uint32_t saved = read_reg(gcc, WAFFLE_GPU_CFG_AHB);
    bool changed = (saved & 3) != 1, ready = false;
    if(owner){owner->saved_cfg=saved;owner->cfg_changed=changed;}
    if (changed) {
        gpu_log("waffle-gpu: force CFG_AHB branch, disable HW gating; prior=%08x\n", saved);
        write_reg(gcc, WAFFLE_GPU_CFG_AHB, (saved & ~3u) | 1);
    }
    for (unsigned i = 0; i < 100; ++i) {
        if (!(read_reg(gcc, WAFFLE_GPU_CFG_AHB) & (1u << 31))) { ready = true; break; }
        delay_for_interval(100, NSEC_PER_USEC);
    }
    if (ready) {
        vm_offset_t cc = ml_io_map(WAFFLE_GPUCC_BASE, WAFFLE_GPUCC_SIZE);
        if (cc) {
            if(owner)owner->cc=cc;
            show(cc, WAFFLE_GPUCC_BASE, "CX_GDSCR", WAFFLE_GPU_CX_GDSCR);
            show(cc, WAFFLE_GPUCC_BASE, "CX_GDS_HW_CTRL", WAFFLE_GPU_CX_HW_CTRL);
            show(cc, WAFFLE_GPUCC_BASE, "GX_GDSCR", WAFFLE_GPU_GX_GDSCR);
            show(cc, WAFFLE_GPUCC_BASE, "AHB_CBCR", WAFFLE_GPU_AHB);
            show(cc, WAFFLE_GPUCC_BASE, "CX_GMU_CBCR", WAFFLE_GPU_CX_GMU);
            show(cc, WAFFLE_GPUCC_BASE, "HUB_CLK_SRC", WAFFLE_GPU_HUB_RCGR);
            show(cc, WAFFLE_GPUCC_BASE, "GMU_CLK_SRC", WAFFLE_GPU_GMU_RCGR);
            gpu_log("waffle-gpu: stage 2 register inspection complete\n");
            if (probe >= 3) probe_cx(gcc, cc, probe, owner);
        } else gpu_log("waffle-gpu: GPUCC map failed\n");
    } else gpu_log("waffle-gpu: CFG_AHB still halted after 10ms; GPUCC untouched\n");
    if(owner) {
        if(owner->child) {
            gpu_log("waffle-gpu: POWER_OWNER begin returned heap=1 clock_live=1 acquired_cx=%u cfg_changed=%u\n",
                owner->cx_acquired,owner->cfg_changed);
            return owner;
        }
        (void)board_power_end(owner);
        return NULL;
    }
    if (changed) {
        uint32_t current = read_reg(gcc, WAFFLE_GPU_CFG_AHB);
        write_reg(gcc, WAFFLE_GPU_CFG_AHB, (current & ~3u) | (saved & 3));
        gpu_log("waffle-gpu: restored CFG_AHB enable/gating=%u\n",
            read_reg(gcc, WAFFLE_GPU_CFG_AHB) & 3);
    }
    gpu_log("waffle-gpu: probe ended; returning to loader\n");
    
    return NULL;
}

/* Internal adapter; service mutex serializes the entire parent lifetime. */
struct waffle_gpu_parent *waffle_gpu_parent_begin(void)
{
    uint32_t image=0;
    if(pll92_power!=256 || !PE_parse_boot_argn("waffle_image",&image,sizeof(image)) || (image!=5 && image!=6 && image!=7 && image!=8 && image!=10 && image!=11 && image!=12 && image!=13))return NULL;
    struct aop_gpu_owner *s=aop_gpu_owner_begin(94);
    if(s)gpu_log("waffle-gpu: full GPU owner returned live to init caller; no mutex held\n");
    return (struct waffle_gpu_parent *)s;
}
bool waffle_gpu_parent_copy(struct waffle_gpu_parent *parent,struct waffle_gpu_copy_job *job)
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(job)job->fence=0;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
        !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child ||
        (s->exercised && !s->exercise_ok))return false;
    struct board_clock_owner *clock=s->child->child;
    bool first=!s->exercised;
    bool ok=waffle_smmu_owner_copy(clock->child,job);
    clock->exercised=true;clock->ok=clock->ok && ok;
    s->exercised=true;s->exercise_ok=first?ok:s->exercise_ok && ok;
    return ok;
}
bool waffle_gpu_parent_buffers(struct waffle_gpu_parent *parent,struct waffle_gpu_buffer buffers[2])
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
       !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child || s->exercised)return false;
    return waffle_smmu_owner_buffers(s->child->child->child,buffers);
}
struct waffle_gpu_memory *waffle_gpu_parent_memory_new(struct waffle_gpu_parent *parent,uint64_t bytes,uint32_t flags)
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
       !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child)return NULL;
    return waffle_smmu_owner_memory_new(s->child->child->child,bytes,flags);
}
struct waffle_gpu_memory *waffle_gpu_parent_memory_adopt(struct waffle_gpu_parent *parent,struct waffle_gpu_memory *prepared)
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
       !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child)return NULL;
    return waffle_smmu_owner_memory_adopt(s->child->child->child,prepared);
}
bool waffle_gpu_parent_memory_reclaim(struct waffle_gpu_parent *parent,struct waffle_gpu_memory *bo,bool cpu_unmapped)
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
       !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child)return false;
    return waffle_smmu_owner_memory_reclaim(s->child->child->child,bo,cpu_unmapped);
}
bool waffle_gpu_parent_submit(struct waffle_gpu_parent *parent,struct waffle_gpu_submit_job *job)
{
    struct aop_gpu_owner *s=(struct aop_gpu_owner *)parent;
    if(job)job->fence=0;
    if(!s || active_aop_gpu!=s || s->locked || !s->child || s->child!=active_board_power ||
       !s->child->child || s->child->child!=active_board_clocks || !s->child->child->child ||
       (s->exercised && !s->exercise_ok))return false;
    struct board_clock_owner *clock=s->child->child;bool first=!s->exercised;
    bool ok=waffle_smmu_owner_submit(clock->child,job);
    clock->exercised=true;clock->ok=clock->ok && ok;s->exercised=true;
    s->exercise_ok=first?ok:s->exercise_ok && ok;return ok;
}
bool waffle_gpu_parent_end(struct waffle_gpu_parent *parent)
{
    return aop_gpu_owner_end((struct aop_gpu_owner *)parent);
}
