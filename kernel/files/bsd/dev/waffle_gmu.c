/* GMU Gen7.9.1 firmware placement and bounded boot/stop diagnostics. */
#include <kern/clock.h>
#include <pexpert/pexpert.h>
#include <vm/memory_types.h>
#include <arm/memory_types.h>
#include <libkern/libkern.h>
#include <mach/vm_param.h>
#include <sys/systm.h>
#include <sys/macan_firmware.h>
#include <sys/waffle_gpu.h>
#include <sys/waffle_gmu.h>
#include <sys/waffle_hfi.h>
#include <sys/waffle_hfi_tables.h>
#include <sys/waffle_scm.h>
#include <sys/waffle_gen7_config.h>
#include <sys/waffle_gen7_hwcg.h>
#include <sys/waffle_gen7_boot.h>
#include <sys/waffle_gpu_measure.h>
#include <sys/waffle_zap_load.h>
#include <sys/waffle_gpu_writeback.h>
#include <sys/waffle_gpu_compute.h>
#include <sys/waffle_gpu_image.h>
#include <sys/waffle_gpu_copy.h>
#include <sys/waffle_gpu_data.h>
#include <sys/waffle_gpu_present.h>
#include <console/video_console.h>
extern struct vc_info vinfo;
#include <vm/vm_kern.h>
extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern vm_offset_t ml_io_map_unmappable(vm_offset_t, vm_size_t, unsigned int);
extern void ml_io_unmap(vm_offset_t, vm_size_t);
extern vm_offset_t kvtophys(vm_offset_t);
extern void loader_log_putc(char);
extern void loader_return(void);
extern uint64_t loader_return_remaining_us(void);
static bool gpu_gen7_configuration_probe(vm_offset_t,vm_offset_t,struct waffle_gmu_plan *,unsigned);
struct gen7_config_io {
    vm_offset_t gpu,gmu,hfi_alias;
    unsigned probe;
    struct waffle_gmu_region *power;
    const struct waffle_gmu_plan *plan;
};
struct gen7_live_probe {
    struct gen7_config_io context;
    struct waffle_gen7_boot_state state;
};
static bool gpu_gen7_live_start(struct gen7_live_probe *,vm_offset_t,vm_offset_t,
    vm_offset_t,struct waffle_gmu_plan *,unsigned);
static void gpu_gen7_live_finish(struct gen7_live_probe *,unsigned);
static bool gen7_zap_transition(vm_offset_t,vm_offset_t,vm_offset_t,struct waffle_gmu_plan *);
static bool gen7_memory_writeback(vm_offset_t,vm_offset_t,vm_offset_t,struct waffle_gmu_plan *);
static void stop_unsafe(const char *);
static bool submit_session_open(vm_offset_t,vm_offset_t,vm_offset_t,struct waffle_gmu_plan *);
static bool submit_session_run(struct waffle_gmu_plan *);
static bool submit_session_close(struct waffle_gmu_plan *);
static void submit_session_destroy(struct waffle_gmu_plan *,unsigned);
static bool session_requested(void)
{
    uint32_t value=0;
    return PE_parse_boot_argn("waffle_session",&value,sizeof(value)) && value==1;
}
static bool ib_requested(void)
{
    uint32_t value=0;
    return PE_parse_boot_argn("waffle_ib",&value,sizeof(value)) && value==1;
}
static bool writeback_requested(void)
{
    uint32_t value=0;
    return PE_parse_boot_argn("waffle_writeback",&value,sizeof(value)) && value==1;
}
static bool zap_requested(void)
{
    uint32_t value=0;
    return PE_parse_boot_argn("waffle_zap",&value,sizeof(value)) && value==1;
}

static void say(const char *fmt, ...) __printflike(1, 2);
static void say(const char *fmt, ...)
{
    char text[256]; va_list ap;
    va_start(ap, fmt); vsnprintf(text, sizeof(text), fmt, ap); va_end(ap);
    for (char *p = text; *p; ++p) loader_log_putc(*p);
    printf("%s", text);
}
static struct waffle_gmu_region *region_at(struct waffle_gmu_plan *plan, uint32_t addr, uint32_t size)
{
    for (unsigned i = 0; i < plan->count; ++i) {
        struct waffle_gmu_region *r = &plan->regions[i];
        if (addr >= r->address && (uint64_t)addr + size <= (uint64_t)r->address + r->size) return r;
    }
    return NULL;
}
void waffle_gmu_free(struct waffle_gmu_plan *plan)
{
    if(plan->submit_session)stop_unsafe("live submit session still owns firmware buffers");
    for (unsigned i = 0; i < plan->count; ++i) {
        struct waffle_gmu_region *r = &plan->regions[i];
        if (r->memory) kmem_free(kernel_map, r->memory, round_page(r->size));
        r->memory = 0;
    }
    plan->count = 0;
}
bool waffle_gmu_prepare(struct waffle_gmu_plan *plan, unsigned probe)
{
    bool boot = probe >= 9;
    bzero(plan, sizeof(*plan));
    plan->split_gpu_va=probe>=39;
    plan->compact_gpu_va=probe>=54;
    uint64_t length = 0;
    plan->firmware = macan_image_file("fw", WAFFLE_GPU_GMU_FW, &length);
    if (!plan->firmware || length > 1024 * 1024) {
        say("waffle-gmu: no bounded uncompressed fw/%s\n", WAFFLE_GPU_GMU_FW); return false;
    }
    plan->length = (size_t)length;
    size_t cursor = 0;
    struct waffle_fw_block b;
    int result;
    while ((result = waffle_fw_next(plan->firmware, plan->length, &cursor, &b)) == 1) {
        if (b.size || (b.type != 1 && b.type != 7)) continue;
        unsigned kind = waffle_fw_region(b.address, b.value);
        if (!kind) { say("waffle-gmu: preallocation outside Gen7 VMA\n"); goto failed; }
        if (kind <= 2 || region_at(plan, b.address, b.value)) continue;
        uint32_t base = b.address & ~4095u;
        uint64_t end = ((uint64_t)b.address + b.value + 4095) & ~4095ULL;
        if (plan->count == WAFFLE_GMU_REGIONS || end - base > 4 * 1024 * 1024 ||
            !waffle_fw_region(base, (uint32_t)(end - base))) goto failed;
        for (unsigned i = 0; i < plan->count; ++i)
            if ((uint64_t)base < (uint64_t)plan->regions[i].address + plan->regions[i].size &&
                end > plan->regions[i].address) goto failed;
        struct waffle_gmu_region *r = &plan->regions[plan->count++];
        r->address = base; r->size = (uint32_t)(end - base);
        if (kmem_alloc(kernel_map, &r->memory, round_page(r->size),
                KMA_KOBJECT | KMA_ZERO | KMA_DATA, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) goto failed;
        say("waffle-gmu: allocate GMU %08x..%08x (%u bytes)\n", base, base + r->size - 1, r->size);
    }
    if (result < 0 || !plan->count) goto failed;
    if (boot) {
        const uint32_t address[] = {WAFFLE_GMU_LOG_ADDRESS, WAFFLE_GMU_HFI_ADDRESS};
        const uint32_t size[] = {WAFFLE_GMU_LOG_SIZE, WAFFLE_GMU_HFI_SIZE};
        for (unsigned i = 0; i < 2; ++i) {
            if (plan->count == WAFFLE_GMU_REGIONS) goto failed;
            for (unsigned j = 0; j < plan->count; ++j)
                if ((uint64_t)address[i] < (uint64_t)plan->regions[j].address + plan->regions[j].size &&
                    (uint64_t)address[i] + size[i] > plan->regions[j].address) goto failed;
            struct waffle_gmu_region *r = &plan->regions[plan->count++];
            r->address = address[i]; r->size = size[i];
            if (kmem_alloc(kernel_map, &r->memory, round_page(r->size),
                    KMA_KOBJECT | KMA_ZERO | KMA_DATA, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) goto failed;
        }
        /* Vendor Gen7 hwsched table: 6-word header, seventeen 12-word queue
         * headers; queue data starts at ALIGN(840,16), each ring is4KB.
         */
        struct waffle_gmu_region *hfi = region_at(plan, WAFFLE_GMU_HFI_ADDRESS, WAFFLE_GMU_HFI_SIZE);
        uint32_t *table = (uint32_t *)hfi->memory;
        table[0] = 0; table[1] = 210; table[2] = 6; table[3] = 12; table[4] = table[5] = 17;
        for (unsigned i = 0; i < 17; ++i) {
            uint32_t *q = table + 6 + i * 12;
            unsigned priority = i < 7 ? 0 : i < 11 ? 1 : i < 14 ? 2 : i < 16 ? 3 : 4;
            q[0] = 1; q[1] = WAFFLE_GMU_HFI_ADDRESS + 848 + 4096 * i;
            q[2] = i | (priority << 8); q[3] = 1024;
        }
    }
    if (probe >= 20) {
        const char *names[] = {WAFFLE_GPU_SQE_FW,WAFFLE_GPU_AQE_FW};
        const uint32_t addresses[] = {WAFFLE_GPU_SQE_ADDRESS,WAFFLE_GPU_AQE_ADDRESS};
        for (unsigned i = 0; i < 2; ++i) {
            uint64_t bytes = 0;
            const uint8_t *data = macan_image_file("fw",names[i],&bytes);
            if (!data || bytes < 8 || bytes > 0x18000 || (bytes&3) ||
                waffle_fw_u32(data) != 0 || plan->count == WAFFLE_GMU_REGIONS) goto failed;
            struct waffle_gmu_region *r = &plan->regions[plan->count++];
            r->address = addresses[i]; r->size = ((uint32_t)bytes-4+4095)&~4095u;
            r->gpu_only = r->readonly = true;
            if (kmem_alloc(kernel_map,&r->memory,round_page(r->size),
                    KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) goto failed;
            /* Native adreno_get_firmware excludes the first4-byte header. */
            memcpy((void *)r->memory,data+4,(size_t)bytes-4);
            if (memcmp((const void *)r->memory,data+4,(size_t)bytes-4)) goto failed;
            say("waffle-gmu: GPU ucode %s VA=%08x payload=%u mapped=%u version=%08x\n",
                names[i],r->address,(uint32_t)bytes-4,r->size,waffle_fw_u32(data+4));
        }
    }
    if (probe >= 21) {
        const uint32_t address[] = {WAFFLE_GPU_RING_ADDRESS,WAFFLE_GPU_SCRATCH_ADDRESS,WAFFLE_GPU_PWRUP_ADDRESS};
        const uint32_t sizes[] = {0x8000,4096,4096};
        for (unsigned i = 0; i < 3; ++i) {
            if (plan->count == WAFFLE_GMU_REGIONS) goto failed;
            struct waffle_gmu_region *r = &plan->regions[plan->count++];
            r->address=address[i];r->size=sizes[i];r->gpu_only=true;
            if (kmem_alloc(kernel_map,&r->memory,round_page(r->size),
                KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) goto failed;
        }
    }
    if (probe == 26 || probe >= 30) {
        if (plan->count == WAFFLE_GMU_REGIONS) goto failed;
        struct waffle_gmu_region *r=&plan->regions[plan->count++];
        r->address=WAFFLE_HWSCHED_POOL_ADDRESS;
        r->size=plan->compact_gpu_va?WAFFLE_GPU_COMPACT_POOL_BYTES:WAFFLE_HWSCHED_POOL_SIZE;
        if (kmem_alloc(kernel_map,&r->memory,round_page(r->size),
                KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) goto failed;
    }
    if(probe==94 && writeback_requested()) {
        if(plan->count==WAFFLE_GMU_REGIONS || region_at(plan,WAFFLE_GPU_WRITEBACK_ADDRESS,1))goto failed;
        struct waffle_gmu_region *r=&plan->regions[plan->count++];
        r->address=WAFFLE_GPU_WRITEBACK_ADDRESS;r->size=WAFFLE_GPU_WRITEBACK_BYTES;r->gpu_only=true;
        if(kmem_alloc(kernel_map,&r->memory,round_page(r->size),
            KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)goto failed;
    }
    cursor = 0;
    while ((result = waffle_fw_next(plan->firmware, plan->length, &cursor, &b)) == 1) {
        if (!b.size) continue;
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (!kind) goto failed;
        if (kind <= 2) continue;
        struct waffle_gmu_region *r = region_at(plan, b.address, b.size);
        if (!r) goto failed;
        memcpy((void *)(r->memory + b.address - r->address), b.payload, b.size);
    }
    if (result < 0) goto failed;
    for (unsigned i = 0; i < plan->count; ++i) {
        struct waffle_gmu_region *r = &plan->regions[i];
        for (vm_offset_t p = r->memory; p < r->memory + r->size; p += 64)
            __asm__ volatile("dc cvac, %0" :: "r"(p) : "memory");
    }
    __asm__ volatile("dsb sy" ::: "memory");
    say("waffle-gmu: firmware parsed, %u external regions prepared; CM3 remains reset\n", plan->count);
    return true;
failed:
    say("waffle-gmu: invalid firmware plan/allocation failure; no TCM writes\n");
    waffle_gmu_free(plan);
    return false;
}
static uint32_t rd(vm_offset_t base, unsigned off) { return *(volatile uint32_t *)(base + off); }
static void wr(vm_offset_t base, unsigned off, uint32_t value)
{
    *(volatile uint32_t *)(base + off) = value;
    __asm__ volatile("dsb sy" ::: "memory");
}
static bool wait_for(vm_offset_t base, unsigned off, uint32_t mask, uint32_t value, unsigned loops)
{
    for (unsigned i = 0; i < loops; ++i) {
        if ((rd(base, off) & mask) == value) return true;
        delay_for_interval(100, NSEC_PER_USEC);
    }
    return false;
}
static void stop_unsafe(const char *reason)
{
    say("waffle-gmu: REBOOT REQUIRED: %s; keep mapped pages until Android reset\n", reason);
    loader_return();
    for (;;) __asm__ volatile("wfi");
}
/* Diagnostic RAW submission observes both queues, as native HWSCHED does.
 * A firmware error is not an ordinary missing ACK: keep all pages and return
 * to the loader immediately rather than pretending native collapse succeeded. */
static bool hfi_raw_fault_packet(const uint32_t *packet,unsigned words,const char *queue)
{
    if (!packet || !words || ((packet[0]>>16)&15)!=0) return false;
    unsigned id=packet[0]&255;
    if (id!=100 && id!=150) return false; /* F2H_ERR / CONTEXT_BAD */
    say("waffle-gmu: RAW firmware fault queue=%s id=%u words=%u hdr=%08x\n",queue,id,words,packet[0]);
    if (id==100 && words>=2)
        say("waffle-gmu: HFI error major=%u minor=%u\n",packet[1]>>16,packet[1]&65535);
    /* CONTEXT_BAD layout depends on HFI minor version; preserve raw words
     * without guessing legacy word4 versus modern word8 error offsets. */
    for (unsigned i=1;i<words && i<=16;++i)
        say("waffle-gmu: fault word[%u]=%08x\n",i,packet[i]);
    return true;
}
static void hfi_raw_diagnostic(vm_offset_t gmu,vm_offset_t alias,unsigned *debug_budget)
{
    volatile uint32_t *table=(volatile uint32_t *)alias;
    volatile uint32_t *dbgq=table+30;
    volatile uint32_t *dbgring=(volatile uint32_t *)(alias+848+2*4096);
    uint32_t packet[255]={0},next=0;
    int count=waffle_hfi_read(dbgq,dbgring,packet,255,&next);
    if (count<0) stop_unsafe("malformed HFI debug queue during RAW");
    if (count>0) {
        __asm__ volatile("dsb sy":::"memory");
        dbgq[10]=next;
        __asm__ volatile("dsb sy":::"memory");
        if (hfi_raw_fault_packet(packet,(unsigned)count,"debug"))
            stop_unsafe("HFI debug queue reported firmware fault during RAW");
        if (*debug_budget) {
            --*debug_budget;
            say("waffle-gmu: RAW debug hdr=%08x words=%d data=%08x/%08x/%08x\n",
                packet[0],count,packet[1],packet[2],packet[3]);
        }
    }
    uint32_t status=rd(gmu,WAFFLE_GMU_REG(0x1f992));
    if (status&(1u<<15)) {
        say("waffle-gmu: RAW CM3 fault IRQ=%08x cmd=%u/%u msg=%u/%u dbg=%u/%u\n",
            status,table[16],table[17],table[28],table[29],dbgq[10],dbgq[11]);
        stop_unsafe("CM3 fault during RAW; do not reclaim live mappings");
    }
}
/* Read-only property query, using only an uncached alias while CM3 runs. */
static void hfi_raw_checkpoint(const struct waffle_gmu_plan *plan,const char *name)
{
    if (!plan || (!plan->fault_smmu && !plan->raw_stage_pause)) return;
    say("waffle-gmu: RAW checkpoint %s\n",name);
}
static void hfi_smmu_diagnostic(const struct waffle_gmu_plan *plan)
{
    if (!plan || !plan->fault_smmu) return;
    unsigned page=plan->fault_page,pages=plan->fault_pages;
    if (page!=4096 || !pages || ((uint64_t)pages+3)*page>WAFFLE_GPU_SMMU_SIZE)
        stop_unsafe("invalid SMMU diagnostic geometry");
    for (unsigned bank=0;bank<3;++bank) {
        vm_offset_t cb=plan->fault_smmu+(pages+bank)*page;
        uint32_t fsr=rd(cb,0x58);
        if (!(fsr&0xc00001feu)) continue;
        uint64_t far=(uint64_t)rd(cb,0x60)|((uint64_t)rd(cb,0x64)<<32);
        uint32_t syndrome=rd(cb,0x68),syndrome1=rd(cb,0x6c);
        uint32_t stream=rd(plan->fault_smmu,page+0x400+bank*4);
        say("waffle-gmu: CP SMMU fault bank=%u FSR=%08x FAR=%llx FSYNR=%08x/%08x CBFRSYNRA=%08x\n",
            bank,fsr,far,syndrome,syndrome1,stream);
        /* Do not clear/resume the stalled transaction or reclaim its mappings. */
        stop_unsafe("SMMU fault during RAW; pages retained");
    }
}

static void hfi_publish_notify(vm_offset_t gmu,volatile uint32_t *cmdq,uint32_t next)
{
    __asm__ volatile("dsb sy" ::: "memory");
    cmdq[11]=next;
    __asm__ volatile("dsb sy" ::: "memory");
    wr(gmu,WAFFLE_GMU_REG(0x1f994),1);
}

static bool hfi_exchange_watch(vm_offset_t gmu, vm_offset_t alias, const uint32_t *request,
    unsigned words, const char *name, bool zero_ack,const struct waffle_gmu_plan *plan)
{
    volatile uint32_t *table = (volatile uint32_t *)alias;
    volatile uint32_t *cmdq = table + 6;
    volatile uint32_t *msgq = table + 18;
    volatile uint32_t *cmdring = (volatile uint32_t *)(alias + 848);
    volatile uint32_t *msgring = (volatile uint32_t *)(alias + 848 + 4096);
    uint32_t next;
    bool raw=(request[0]&255)==131;
    unsigned debug_budget=16;
    if (raw) {
        hfi_raw_checkpoint(plan,"0-preflight-begin");
        hfi_smmu_diagnostic(plan);
        hfi_raw_checkpoint(plan,"1-smmu-read-done");
        hfi_raw_diagnostic(gmu,alias,&debug_budget);
        hfi_raw_checkpoint(plan,"2-debug-read-done");
    }
    if (waffle_hfi_write(cmdq, cmdring, request, words, &next) != (int)words) {
        say("waffle-gmu: HFI command queue invalid/full\n"); return false;
    }
    if (raw) hfi_raw_checkpoint(plan,"3-packet-staged");
    if (raw && plan && plan->raw_stage_pause) {
        say("waffle-gmu: RAW_EDGE68 staged hold 5s; index unpublished\n");
        delay_for_interval(5000000,NSEC_PER_USEC);
    }
    /* Keep publication and notification consecutive, as gen7_hfi_cmdq_write.
     * A live GMU can observe the new index before the doorbell: no diagnostic
     * reads, printing or delays belong inside this interval. */
    hfi_publish_notify(gmu,cmdq,next);
    if (raw) hfi_raw_checkpoint(plan,"4-doorbell-sent");
    else
        say("waffle-gmu: HFI cmdq type=%08x addr=%08x notified\n",cmdq[2],cmdq[1]);
    if (raw && plan && plan->raw_stage_pause) {
        say("waffle-gmu: RAW_EDGE68 notified hold 5s; no diagnostic polling\n");
        delay_for_interval(5000000,NSEC_PER_USEC);
    }
    for (unsigned i = 0; i < 10000; ++i) {
        if (raw) {
            hfi_smmu_diagnostic(plan);hfi_raw_diagnostic(gmu,alias,&debug_budget);
            if (!i) hfi_raw_checkpoint(plan,"5-first-poll-done");
        }
        uint32_t packet[255] = {0};
        int count = waffle_hfi_read(msgq, msgring, packet, 255, &next);
        if (count < 0) { say("waffle-gmu: malformed HFI message queue\n"); return false; }
        if (count > 0) {
            __asm__ volatile("dsb sy" ::: "memory");
            msgq[10] = next;
            __asm__ volatile("dsb sy" ::: "memory");
            say("waffle-gmu: HFI message words=%d hdr=%08x req=%08x value=%08x\n",
                count, packet[0], packet[1], packet[2]);
            if (raw && hfi_raw_fault_packet(packet,(unsigned)count,"message"))
                stop_unsafe("HFI message queue reported firmware fault during RAW");
            if (count >= 3 && ((packet[0] >> 16) & 15) == 1 && packet[1] == request[0]) {
                bool ok = zero_ack ? packet[2] == 0 : packet[2] != 0xffffffff;
                say("waffle-gmu: %s ACK matched seq%u value=%08x valid=%u\n",
                    name, request[0] >> 20, packet[2], ok);
                return ok;
            }
            if (i >= 32) break; /* bounded unsolicited traffic */
        }
        delay_for_interval(100, NSEC_PER_USEC);
    }
    say("waffle-gmu: HFI query timeout cmd r/w=%u/%u msg r/w=%u/%u IRQ=%08x\n",
        cmdq[10],cmdq[11],msgq[10],msgq[11],rd(gmu, WAFFLE_GMU_REG(0x1f992)));
    return false;
}
/* Exercise the actual RAW preflight and packet writer while keeping the
 * producer index private. Restore every staged word before normal collapse. */
static bool hfi_raw_stage_control(vm_offset_t gmu,vm_offset_t alias,
    const uint32_t *request,unsigned words,const struct waffle_gmu_plan *plan)
{
    if (!request || words!=11 || (request[0]&255)!=131) return false;
    volatile uint32_t *table=(volatile uint32_t *)alias;
    volatile uint32_t *cmdq=table+6;
    volatile uint32_t *ring=(volatile uint32_t *)(alias+848);
    unsigned budget=16;
    say("waffle-gmu: RAW_STAGE67 begin; publication disabled\n");
    hfi_smmu_diagnostic(plan);
    hfi_raw_diagnostic(gmu,alias,&budget);
    say("waffle-gmu: RAW_STAGE67 debug preflight passed\n");
    uint32_t read=cmdq[10],write=cmdq[11],next=0;
    if (read!=write || write>=1024 || cmdq[3]!=1024) return false;
    uint32_t saved[12];
    for(unsigned i=0;i<12;i++) saved[i]=ring[(write+i)%1024];
    if (waffle_hfi_write(cmdq,ring,request,words,&next)!=(int)words) return false;
    __asm__ volatile("dsb sy" ::: "memory");
    if (cmdq[10]!=read || cmdq[11]!=write)
        stop_unsafe("RAW staging control lost queue ownership");
    for(unsigned i=0;i<12;i++) ring[(write+i)%1024]=saved[i];
    __asm__ volatile("dsb sy" ::: "memory");
    say("waffle-gmu: RAW_STAGE67 staged/restored words=11 next=%u r/w=%u/%u; no publication or doorbell\n",
        next,read,write);
    return true;
}
static bool hfi_exchange(vm_offset_t gmu,vm_offset_t alias,const uint32_t *request,
    unsigned words,const char *name,bool zero_ack)
{
    return hfi_exchange_watch(gmu,alias,request,words,name,zero_ack,NULL);
}
/* START bring-up without requesting GX: stage25 captures one request; stage26
 * replies from pre-mapped normal-NC RAM. Always reset CM3 before freeing it. */
static bool hfi_boot_votes(vm_offset_t gmu,vm_offset_t alias,unsigned probe)
{
    const uint32_t frequency[]={((probe>=31?32u:probe>=24?13u:7u)<<20)|(4u<<8)|30u,
        1,1,probe>=75?0xffff00ffu:1u};
    if(!hfi_exchange(gmu,alias,frequency,4,"MINIMUM_DCVS",true)) return false;
    if(probe>=75){
        /* Native six-knob-off capture: quantized AB530, IB1; no frequency change. */
        const uint32_t bandwidth[]={(41u<<20)|(4u<<8)|30u,1,255,0x02120101};
        if(!hfi_exchange(gmu,alias,bandwidth,4,"NATIVE_DDR_AB",true)) return false;
    }
    return true;
}
static bool hfi_boot_acd(vm_offset_t gmu,vm_offset_t hfi_alias)
{
    const uint32_t acd_on[]={(36u<<20)|(4u<<8)|11u,12,1,0};
    uint32_t acd_table[69];
    return hfi_exchange(gmu,hfi_alias,acd_on,4,"ACD_ON",true) &&
        waffle_hfi_acd_table_packet(acd_table,69,37)==69 &&
        hfi_exchange(gmu,hfi_alias,acd_table,69,"ACD_TABLE",true);
}
static bool hfi_boot_features(vm_offset_t gmu,vm_offset_t hfi_alias,unsigned probe)
{
    bool running=true;
    if (running && probe >= 14) {
        /* Keep IFPC/NAP disabled: no RSC/PDC idle entry in this bounded test.
         * CORE_FW_START initializes power firmware, distinct from START10
         * (hwsched allocation) and DCVS requests. */
        /* Feature 11 is BCL, not IFPC (which is feature 9). Native PJD110
         * advertises BCL with enable=1, data=1 on the matched cold boot. */
        const uint32_t bcl[] = {(4u<<20)|(4u<<8)|11u,11,probe>=43?1u:0u,probe>=43?1u:0u};
        const uint32_t nap_off[] = {(5u<<20)|(4u<<8)|11u,10,0,0};
        const uint32_t hwsched_on[] = {(6u<<20)|(4u<<8)|11u,1,1,0};
        const uint32_t kprof_on[] = {(7u<<20)|(4u<<8)|11u,16,1,0};
        const uint32_t core_start[] = {((probe>=41 ? 9u : probe>=24 ? 8u : 6u)<<20)|(2u<<8)|14u,0};
        if (probe>=65) running=hfi_boot_acd(gmu,hfi_alias);
        if (running && probe>=69) {
            /* Native ACD profiling event; captured payload112/44/0. */
            const uint32_t event[]={(39u<<20)|(4u<<8)|13u,112,44,0};
            running=hfi_exchange(gmu,hfi_alias,event,4,"ACD_LOG_EVENT_ON",true);
        }
        if (running) running = hfi_exchange(gmu,hfi_alias,bcl,4,probe>=43?"BCL_ON":"BCL_OFF",true);
        /* Native cold startup omits disabled optional features. Explicit OFF
         * messages are retained only for historical probes through62. */
        if (running && probe<63) running = hfi_exchange(gmu,hfi_alias,nap_off,4,"NAP_OFF",true);
        if (running && probe >= 24) running = hfi_exchange(gmu,hfi_alias,hwsched_on,4,"HWSCHED_ON",true);
        if (running && probe >= 24) running = hfi_exchange(gmu,hfi_alias,kprof_on,4,"KPROF_ON",true);
        if (running && probe>=41) {
            /* Native gen7_hfi_send_dms_feature_ctrl advertises device support,
             * independently of dms_enabled/CP_ME_INIT's disable-DMS bit. */
            const uint32_t dms_capability[]={(8u<<20)|(4u<<8)|11u,27,1,0};
            running=hfi_exchange(gmu,hfi_alias,dms_capability,4,"DMS_CAPABILITY_ON",true);
        }
        if (running && probe>=48 && probe<65)
            running=hfi_boot_acd(gmu,hfi_alias);
        if (running && probe>=50) {
            const uint32_t bailout[]={(38u<<20)|(4u<<8)|11u,17,1,0};
            running=hfi_exchange(gmu,hfi_alias,bailout,4,"BAILOUT_TIMER_ON",true);
        }
        if (running) running = hfi_exchange(gmu,hfi_alias,core_start,2,"CORE_FW_START",true);
        if (running && probe >= 24) {
            const uint32_t features[][4] = {
                {((probe>=41?10u:9u)<<20)|(4u<<8)|11u,2,0,0},
                {((probe>=41?11u:10u)<<20)|(4u<<8)|11u,24,0,0},
                {(11u<<20)|(4u<<8)|11u,27,0,0},
                {(12u<<20)|(4u<<8)|11u,29,1,0},
            };
            const char *names[] = {"PREEMPTION_OFF","LPAC_OFF","DMS_OFF","AQE_ON"};
            for (unsigned i=0;running && i<4;++i) {
                if (probe>=63 && i<2) continue; /* Native PREEMPT/LPAC disabled. */
                if (probe>=41 && i==2) continue; /* Keep GMU DMS capability on. */
                running=hfi_exchange(gmu,hfi_alias,features[i],4,names[i],true);
            }
            say("waffle-gmu: HWSCHED feature preflight result=%u; no START10 or GPU commands\n",running);
            if (running && probe>=65)
                say("waffle-gmu: native ACD-first HFI order active\n");
            if (running && probe>=63)
                say("waffle-gmu: native optional-off profile: NAP/PREEMPTION/LPAC messages omitted\n");
        }
    }
    return running;
}
static bool hfi_start_capture(vm_offset_t gmu, vm_offset_t alias,
    struct waffle_gmu_plan *plan, unsigned probe)
{
    volatile uint32_t *table=(volatile uint32_t *)alias;
    volatile uint32_t *cmdq=table+6,*msgq=table+18;
    volatile uint32_t *cmdring=(volatile uint32_t *)(alias+848);
    volatile uint32_t *msgring=(volatile uint32_t *)(alias+848+4096);
    const uint32_t request[]={(13u<<20)|(1u<<8)|10u};
    struct waffle_hfi_pool pool={0};
    struct waffle_hfi_pool protected_pool={0};
    if (probe >= 30) {
        if (!plan->protected_address || !plan->protected_size) return false;
        protected_pool.base=plan->protected_address;protected_pool.size=plan->protected_size;
    }
    if (probe >= 26) {
        struct waffle_gmu_region *arena=region_at(plan,WAFFLE_HWSCHED_POOL_ADDRESS,plan->compact_gpu_va?WAFFLE_GPU_COMPACT_POOL_BYTES:WAFFLE_HWSCHED_POOL_SIZE);
        if (!arena || arena->gpu_only || arena->readonly) return false;
        pool.base=arena->address;pool.size=arena->size;
    }
    unsigned sequence=14,messages=0;
    uint32_t next;
    if (waffle_hfi_write(cmdq,cmdring,request,1,&next)!=1) return false;
    __asm__ volatile("dsb sy":::"memory");
    cmdq[11]=next;
    __asm__ volatile("dsb sy":::"memory");
    wr(gmu,WAFFLE_GMU_REG(0x1f994),1);
    for (unsigned i=0;i<10000;++i) {
        uint32_t packet[255]={0};
        int words=waffle_hfi_read(msgq,msgring,packet,255,&next);
        if (words<0) return false;
        if (words>0) {
            __asm__ volatile("dsb sy":::"memory");
            msgq[10]=next;
            __asm__ volatile("dsb sy":::"memory");
            if (++messages>64) return false;
            if (probe >= 26 && words>=3 && ((packet[0]>>16)&15)==1 && packet[1]==request[0]) {
                bool ok=packet[2]==0 && pool.count>0;
                say("waffle-gmu: HWSCHED START ACK status=%08x allocations=%u bytes=%u valid=%u\n",
                    packet[2],pool.count+protected_pool.count,pool.used+protected_pool.used,ok);
                return ok;
            }
            struct waffle_hfi_mem_request r;
            bool valid=waffle_hfi_mem_request_decode(packet,(unsigned)words,&r);
            say("waffle-gmu: START first message words=%d hdr=%08x version=%u valid_memalloc=%u\n",
                words,packet[0],packet[1],valid);
            for (int j=0;j<words;++j) say("waffle-gmu: START word%u=%08x\n",j,packet[j]);
            if (valid) say("waffle-gmu: START allocation kind=%u flags=%08x size=%u align=%08x handle=%u; request parsed\n",
                r.kind,r.flags,r.size,r.alignment,r.gmu_handle);
            if (probe == 25 || !valid) return valid;
            struct waffle_hfi_mem_request answer;
            int result=(probe>=30 && (r.flags&(1u<<12))) ?
                waffle_hfi_pool_reserve_secure(&protected_pool,&r,&answer):
                waffle_hfi_pool_reserve(&pool,&r,&answer);
            if (result) {
                say("waffle-gmu: START allocation refused result=%d; no reply, reset CM3 next\n",result);
                return false;
            }
            if (plan->split_gpu_va && answer.gpu_address && !(r.flags&(1u<<12)))
                answer.gpu_address=waffle_gpu_plan_alias(plan,answer.gpu_address);
            if(probe>=72 && answer.gpu_address && !(r.flags&(1u<<12)) &&
                (!plan->pool_permissions || !plan->pool_permissions(plan->pool_permissions_context,answer.gpu_address,answer.size,answer.flags)))
                stop_unsafe("allocation GPU permissions failed; mappings retained");
            const uint32_t response[]={((sequence++)<<20)|(1u<<16)|(11u<<8)|20u,
                packet[0],(uint32_t)answer.gpu_address,(uint32_t)(answer.gpu_address>>32),
                answer.flags,answer.kind,answer.host_handle,answer.gmu_handle,
                answer.gmu_address,answer.size,answer.alignment};
            if (waffle_hfi_write(cmdq,cmdring,response,11,&next)!=11) return false;
            __asm__ volatile("dsb sy":::"memory");cmdq[11]=next;
            __asm__ volatile("dsb sy":::"memory");wr(gmu,WAFFLE_GMU_REG(0x1f994),1);
            say("waffle-gmu: START allocation replied GPU=%llx GMU=%08x host_handle=%u reserved=%u\n",
                answer.gpu_address,answer.gmu_address,answer.host_handle,pool.used+protected_pool.used);
        }
        delay_for_interval(100,NSEC_PER_USEC);
    }
    say("waffle-gmu: START allocation capture timed out\n");
    return false;
}
static bool gpu_firmware_probe(vm_offset_t gpu, struct waffle_gmu_plan *plan)
{
    struct waffle_gmu_region *sqe = region_at(plan,WAFFLE_GPU_SQE_ADDRESS,4);
    struct waffle_gmu_region *aqe = region_at(plan,WAFFLE_GPU_AQE_ADDRESS,4);
    if (!sqe || !aqe || !sqe->gpu_only || !aqe->gpu_only) return false;
    const unsigned indices[] = {0x830,0x831,0xb70,0xb71};
    const uint32_t values[] = {WAFFLE_GPU_SQE_ADDRESS,0,WAFFLE_GPU_AQE_ADDRESS,0};
    uint32_t saved[4], control = rd(gpu,0x808*4);
    if (control != 0) { say("waffle-gmu: CP control=%08x; require fresh disabled state\n",control); return false; }
    for (unsigned i = 0; i < 4; ++i) saved[i] = rd(gpu,indices[i]*4);
    /* Native hwsched init_ucode_regs sets bases before starting CP. Do NOT
     * write SQE_CNTL3 here: enabling+halting can still prefetch oldbase0. */
    bool ok = true;
    for (unsigned i = 0; i < 4; ++i) {
        wr(gpu,indices[i]*4,values[i]);
        if (rd(gpu,indices[i]*4) != values[i]) ok = false;
    }
    if (rd(gpu,0x808*4) != 0) stop_unsafe("CP became enabled during ucode base test");
    say("waffle-gmu: SQE/AQE base readback=%s; CP remains disabled\n",ok?"matches":"FAILED");
    for (unsigned i = 0; i < 4; ++i) wr(gpu,indices[i]*4,saved[i]);
    bool restored = rd(gpu,0x808*4)==0;
    for (unsigned i = 0; i < 4; ++i)
        if (rd(gpu,indices[i]*4)!=saved[i]) restored = false;
    say("waffle-gmu: SQE/AQE register restore=%s\n",restored?"matches":"FAILED");
    return ok && restored;
}
static uint32_t packet7(unsigned opcode, unsigned count)
{
    unsigned a=count,b=opcode;
    a^=a>>16;a^=a>>8;a^=a>>4;
    b^=b>>16;b^=b>>8;b^=b>>4;
    return (7u<<28)|count|(((~0x6996u>>(a&15))&1)<<15)|
        (opcode<<16)|(((~0x6996u>>(b&15))&1)<<23);
}
static bool gpu_cp_probe(vm_offset_t gpu, struct waffle_gmu_plan *plan, unsigned probe)
{
    struct waffle_gmu_region *ring=region_at(plan,WAFFLE_GPU_RING_ADDRESS,0x8000);
    struct waffle_gmu_region *scratch=region_at(plan,WAFFLE_GPU_SCRATCH_ADDRESS,4096);
    struct waffle_gmu_region *power=region_at(plan,WAFFLE_GPU_PWRUP_ADDRESS,4096);
    if (!ring || !scratch || !power || rd(gpu,0x808*4)!=0 ||
        rd(gpu,0x807*4)!=0 || rd(gpu,0x806*4)!=0) return false;
    vm_offset_t alias=ml_io_map_unmappable(kvtophys(scratch->memory),PAGE_SIZE,VM_WIMG_WCOMB);
    if (!alias) return false;
    /* Native Gen7 init: disable concurrent binning, disable DMS (not enabled),
     * use an empty register-list lock. No ZAP/security switch or draw yet. */
    const uint32_t commands[]={packet7(0x17,1),1u<<27,packet7(0x48,7),
        1|2|8|64|256|2048,3,0x20000000,2,WAFFLE_GPU_PWRUP_ADDRESS,0,1u<<31};
    memcpy((void *)ring->memory,commands,sizeof(commands));
    for (vm_offset_t p=ring->memory;p<ring->memory+sizeof(commands);p+=64)
        __asm__ volatile("dc cvac, %0"::"r"(p):"memory");
    __asm__ volatile("dsb sy":::"memory");
    const struct {unsigned index;uint32_t value;} setup[]={
        {0x844,0x6f},{0xad0,0xf},{0xb78,1},
        {0x804,WAFFLE_GPU_SCRATCH_ADDRESS},{0x805,0},
        {0xa98,WAFFLE_GPU_SCRATCH_ADDRESS+4},{0xa99,0},
        {0x802,12|(2u<<8)},{0x800,WAFFLE_GPU_RING_ADDRESS},{0x801,0},
        {0x830,WAFFLE_GPU_SQE_ADDRESS},{0x831,0},
        {0xb70,WAFFLE_GPU_AQE_ADDRESS},{0xb71,0},
    };
    uint32_t saved[sizeof(setup)/sizeof(setup[0])];
    for (unsigned i=0;i<sizeof(setup)/sizeof(setup[0]);++i)
        saved[i]=rd(gpu,setup[i].index*4);
    bool ok=true;
    for (unsigned i=0;i<sizeof(setup)/sizeof(setup[0]);++i) {
        say("waffle-gmu: CP setup index=%04x value=%08x (CP disabled)\n",
            setup[i].index,setup[i].value);
        wr(gpu,setup[i].index*4,setup[i].value);
        if(rd(gpu,setup[i].index*4)!=setup[i].value) ok=false;
    }
    say("waffle-gmu: CP ring/ucode/APRIV setup readback=%u\n",ok);
    if (probe == 22 || !ok) {
        if (rd(gpu,0x808*4)!=0) stop_unsafe("CP enabled during disabled setup");
        bool restored=true;
        for (unsigned i=sizeof(setup)/sizeof(setup[0]);i>0;--i) {
            wr(gpu,setup[i-1].index*4,saved[i-1]);
            if(rd(gpu,setup[i-1].index*4)!=saved[i-1]) restored=false;
        }
        if (rd(gpu,0x808*4)!=0) stop_unsafe("CP enabled during setup restoration");
        say("waffle-gmu: CP disabled setup result=%u restore=%u; no enable or WPTR writes\n",
            ok,restored);
        ml_io_unmap(alias,PAGE_SIZE);
        return ok && restored;
    }
    say("waffle-gmu: enable CP SQE with valid microcode/ring; WPTR still zero\n");
    wr(gpu,0x808*4,1);
    if (probe == 23) {
        /* Isolate microcode startup from packet submission after stage21
         * caused a system-fatal reset. Keep WPTR0 and all mappings alive. */
        delay_for_interval(100,NSEC_PER_USEC);
        uint32_t control=rd(gpu,0x808*4), status=rd(gpu,0x210*4);
        uint32_t rptr=rd(gpu,0x806*4), wptr=rd(gpu,0x807*4);
        uint32_t taken=*(volatile uint32_t *)alias;
        ok=control==1 && rptr==0 && wptr==0 && taken==0 && !(status&~1u);
        say("waffle-gmu: CP enable-only result=%u SQE=%08x RBBM=%08x rptr=%u wptr=%u DMA=%u; no packets submitted\n",
            ok,control,status,rptr,wptr,taken);
        wr(gpu,0x808*4,3);
        say("waffle-gmu: CP enable-only halt requested; resources kept until GXoff\n");
        ml_io_unmap(alias,PAGE_SIZE);
        return ok;
    }
    say("waffle-gmu: submit CP init10words\n");
    wr(gpu,0x807*4,10);
    uint32_t taken=0,status=0;
    for (unsigned i=0;i<10000;++i) {
        taken=*(volatile uint32_t *)alias;status=rd(gpu,0x210*4);
        if (taken==10 && !(status&~1u)) break;
        delay_for_interval(100,NSEC_PER_USEC);
    }
    uint32_t rptr=rd(gpu,0x806*4),wptr=rd(gpu,0x807*4);
    say("waffle-gmu: CP init rptrDMA=%u rptrREG=%u wptr=%u RBBM=%08x CPstatus=%08x IRQ=%08x SQE=%08x\n",
        taken,rptr,wptr,status,rd(gpu,0x825*4),rd(gpu,0x201*4),rd(gpu,0x808*4));
    ok=taken==10 && rptr==10 && !(status&~1u);
    /* Halt only AFTER valid bases were installed. Keep every buffer mapped
     * until subsequent GXcollapse and GBIF/QTBdrain, including failedinit. */
    wr(gpu,0x808*4,3);
    say("waffle-gmu: CP init result=%u; halt requested, resources kept until GXoff\n",ok);
    ml_io_unmap(alias,PAGE_SIZE);
    return ok;
}
static bool gpu_power_probe(vm_offset_t gmu, vm_offset_t cc, struct waffle_gmu_plan *plan, unsigned probe,
    vm_offset_t hfi_alias,struct gen7_live_probe *live)
{
    /* Native oob_gpu=0: SETbit30, ACKbit31, CLEARrequestbit31.
     * No SQE/AQE/RBBM start writes; only read GX after power checks. */
    say("waffle-gmu: OOB_GPU request at lowest stock frequency\n");
    wr(gmu,WAFFLE_GMU_REG(0x1f991),1u<<31);
    wr(gmu,WAFFLE_GMU_REG(0x1f994),1u<<30);
    bool acknowledged = wait_for(gmu,WAFFLE_GMU_REG(0x1f992),1u<<31,1u<<31,1000);
    uint32_t status = rd(gmu,WAFFLE_GMU_REG(0x1f8d0));
    uint32_t gdsc = rd(cc,WAFFLE_GPU_GX_GDSCR);
    bool powered = !(status & 3) && (gdsc & (1u<<31));
    say("waffle-gmu: OOB_GPU ack=%u GXon=%u status=%08x GDSCR=%08x\n",
        acknowledged,powered,status,gdsc);
    wr(gmu,WAFFLE_GMU_REG(0x1f991),1u<<31);
    bool success = acknowledged && powered;
    if (success) {
        vm_offset_t gpu = ml_io_map(WAFFLE_GPU_BASE,WAFFLE_GPU_SIZE);
        if (!gpu) success = false;
        else {
            say("waffle-gmu: read powered GX RBBM_STATUS/CP_STATUS1/SQE_CNTL\n");
            uint32_t rbbm = rd(gpu,0x210*4), cp = rd(gpu,0x825*4), sqe = rd(gpu,0x808*4);
            say("waffle-gmu: GX registers RBBM=%08x CP=%08x SQE=%08x\n",rbbm,cp,sqe);
            if (probe==87) {
                /* Lucid OLE offsets from pinned clk-alpha-pll.c. Read only
                 * while OOB/GX ownership is held; no PLL programming here. */
                for(unsigned i=0;i<2;i++) {
                    unsigned b=i*0x1000;
                    say("waffle-gmu: PLL87 pll=%u MODE=%08x OPMODE=%08x STATUS=%08x L=%08x ALPHA=%08x\n",
                        i,rd(cc,b),rd(cc,b+4),rd(cc,b+0xc),rd(cc,b+0x10),rd(cc,b+0x14));
                    say("waffle-gmu: PLL87 pll=%u USER=%08x/%08x CONFIG=%08x/%08x/%08x TEST=%08x/%08x/%08x/%08x\n",
                        i,rd(cc,b+0x18),rd(cc,b+0x1c),rd(cc,b+0x20),rd(cc,b+0x24),rd(cc,b+0x28),
                        rd(cc,b+0x2c),rd(cc,b+0x30),rd(cc,b+0x34),rd(cc,b+0x38));
                }
            }
            if (probe >= 33) {
                success = gpu_gen7_live_start(live,gpu,gmu,hfi_alias,plan,probe);
                if (success && probe==87) for(unsigned i=0;i<2;i++) {
                    unsigned b=i*0x1000;
                    say("waffle-gmu: PLL87_READY pll=%u MODE=%08x OPMODE=%08x L=%08x CONFIG=%08x/%08x/%08x\n",
                        i,rd(cc,b),rd(cc,b+4),rd(cc,b+0x10),rd(cc,b+0x20),rd(cc,b+0x24),rd(cc,b+0x28));
                }
            }
            else if (probe >= 31) success = gpu_gen7_configuration_probe(gpu,gmu,plan,probe);
            else if (probe >= 21 && probe <= 23) success = gpu_cp_probe(gpu,plan,probe);
            else if (probe >= 20) success = gpu_firmware_probe(gpu,plan);
        }
    }
    if(success && plan && plan->submit_session) {
        say("waffle-gmu: SESSION OOB ownership transferred; init returned with GX retained\n");
        return true;
    }
    wr(gmu,WAFFLE_GMU_REG(0x1f994),1u<<31);
    say("waffle-gmu: OOB_GPU released; notify slumber next\n");
    return success;
}
/* Pinned OnePlus qcom_scm-smc.c: STD/SMC64/SIP, x2..x5 arguments,
 * extended argument pointer in x5 when required; interrupted-call x6 context. */
static int32_t scm_raw(uint32_t function,uint32_t arginfo,
    const uint64_t arguments[4],uint64_t *answer)
{
    uint64_t session = 0;
    for (unsigned i = 0; i < 16; ++i) {
        register uint64_t x0 __asm__("x0") = i ? 1 : function;
        register uint64_t x1 __asm__("x1") = arginfo;
        register uint64_t x2 __asm__("x2") = arguments[0];
        register uint64_t x3 __asm__("x3") = arguments[1];
        register uint64_t x4 __asm__("x4") = arguments[2];
        register uint64_t x5 __asm__("x5") = arguments[3];
        register uint64_t x6 __asm__("x6") = session;
        register uint64_t x7 __asm__("x7") = 0;
        __asm__ volatile("smc #0" : "+r"(x0),"+r"(x1),"+r"(x2),"+r"(x3),
            "+r"(x4),"+r"(x5),"+r"(x6),"+r"(x7) : :
            "x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
        session = x6;
        if (x0 != 1) { *answer = x1; return (int32_t)x0; }
    }
    return -1;
}
static int32_t scm_one(uint32_t function,uint64_t argument,uint64_t *answer)
{
    const uint64_t arguments[4]={argument,0,0,0};
    return scm_raw(function,1,arguments,answer);
}
/* E09: only reached after a verified CP_INIT, with live OOB/GX ownership. */
struct zap_runtime {vm_offset_t payload;};
static bool zap_pas_call(void *context,uint32_t function,uint32_t arginfo,
    const uint64_t *args,uint64_t *answer)
{
    (void)context;
    int32_t status=-1;
    for(unsigned retry=0;retry<=20;++retry) {
        status=scm_raw(function,arginfo,args,answer);
        if(status!=-12)break;
        delay_for_interval(30000,NSEC_PER_USEC);
    }
    say("waffle-gmu: ZAP_PAS function=%08x transport=%d service=%llx\n",function,status,*answer);
    return status==0;
}
static bool zap_copy_payload(void *opaque,const uint8_t *data,unsigned bytes,unsigned memory_bytes)
{
    struct zap_runtime *c=opaque;
    if(!c || !c->payload || bytes>memory_bytes || memory_bytes>8192)return false;
    /* WC alias into the reserved no-map range, never a normal XNU allocation. */
    volatile uint8_t *out=(volatile uint8_t *)(c->payload+0x2000);
    for(unsigned i=0;i<memory_bytes;++i)out[i]=i<bytes?data[i]:0;
    __asm__ volatile("dsb sy":::"memory");
    for(unsigned i=0;i<memory_bytes;++i)if(out[i]!=(i<bytes?data[i]:0))return false;
    say("waffle-gmu: ZAP_PAYLOAD copied=%u reserved=%llx readback=1\n",bytes,WAFFLE_ZAP_RESERVED_BASE);
    return true;
}
static bool gen7_zap_transition(vm_offset_t gpu,vm_offset_t gmu,vm_offset_t hfi_alias,
    struct waffle_gmu_plan *plan)
{
    uint32_t lpac=0;
    if(!PE_parse_boot_argn("waffle_lpac_map",&lpac,sizeof(lpac)) || lpac!=1 ||
        rd(gpu,0xf400*4)!=1) return false;
    uint64_t length=0;
    const uint8_t *image=macan_image_file("fw","gen70900_zap.mbn",&length);
    struct waffle_zap_image p;
    if(!waffle_zap_parse(image,length,&p) || PAGE_SIZE!=16384)return false;
    /* Probe all PAS commands before allocating or submitting INIT_IMAGE. */
    for(unsigned i=0;i<4;++i) {
        const unsigned commands[]={7,1,2,5};
        uint64_t answer=0;
        if(scm_one(0x42000601,0x02000200|commands[i],&answer) || answer!=1) {
            say("waffle-gmu: ZAP_PAS unavailable command=%u\n",commands[i]);return false;
        }
    }
    vm_offset_t metadata=0,alias=0,payload=0;
    if(kmem_alloc(kernel_map,&metadata,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
        VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
    uint64_t pa=kvtophys(metadata);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(metadata+PAGE_SIZE-1)!=pa+PAGE_SIZE-1)goto free_metadata;
    for(vm_offset_t a=metadata;a<metadata+PAGE_SIZE;a+=64)
        __asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    alias=ml_io_map_unmappable(pa,PAGE_SIZE,VM_WIMG_WCOMB);
    payload=ml_io_map_unmappable(WAFFLE_ZAP_RESERVED_BASE&~16383ULL,PAGE_SIZE,VM_WIMG_WCOMB);
    if(!alias || !payload)goto free_metadata;
    volatile uint8_t *out=(volatile uint8_t *)alias;
    for(unsigned i=0;i<p.header_bytes;++i)out[i]=image[i];
    for(unsigned i=0;i<p.hash_bytes;++i)out[p.header_bytes+i]=image[p.hash_offset+i];
    __asm__ volatile("dsb sy":::"memory");
    struct zap_runtime runtime={payload};
    const struct waffle_zap_io io={&runtime,zap_pas_call,zap_copy_payload};
    struct waffle_zap_state state;
    if(!waffle_zap_load(&io,image,length,pa,&state)) {
        say("waffle-gmu: ZAP_LOAD result=0 stage=%u retained=%u\n",state.stage,state.retain);
        if(state.retain)stop_unsafe("ZAP PAS state uncertain; retain metadata and reserved aliases");
        goto free_metadata;
    }
    /* Native PAS metadata lifetime ends after MDT load, but retain this16KiB
     * diagnostic allocation until Android reset to avoid speculative reuse. */
    say("waffle-gmu: ZAP_LOAD authenticated=1 stage=%u metadata retained until reset\n",state.stage);
    const uint32_t packet[]={(43u<<20)|(3u<<8)|131u,0x70e60001u,0};
    if(!hfi_exchange_watch(gmu,hfi_alias,packet,3,"ZAP_UNSECURE",true,plan))
        stop_unsafe("ZAP authenticated but CP secure switch ACK failed");
    if(!wait_for(gmu,WAFFLE_GMU_REG(0x23b0c),1u<<23,0,2000))
        stop_unsafe("ZAP secure switch idle timeout");
    uint32_t trust=rd(gpu,0xf400*4);
    if(trust)stop_unsafe("ZAP secure switch TRUST readback nonzero");
    ml_io_unmap(payload,PAGE_SIZE);
    say("waffle-gmu: ZAP_TRANSITION result=1 TRUST=%08x; no draw\n",trust);
    if(session_requested())return submit_session_open(gpu,gmu,hfi_alias,plan);
    if(writeback_requested())return gen7_memory_writeback(gpu,gmu,hfi_alias,plan);
    return true;
free_metadata:
    if(payload)ml_io_unmap(payload,PAGE_SIZE);
    if(alias)ml_io_unmap(alias,PAGE_SIZE);
    kmem_free(kernel_map,metadata,PAGE_SIZE);
    return false;
}
static bool gen7_memory_writeback(vm_offset_t gpu,vm_offset_t gmu,vm_offset_t hfi_alias,
    struct waffle_gmu_plan *plan)
{
    struct waffle_gmu_region *r=region_at(plan,WAFFLE_GPU_WRITEBACK_ADDRESS,WAFFLE_GPU_WRITEBACK_BYTES);
    if(!r || !r->gpu_only || r->readonly || r->size!=16384 || rd(gpu,0xf400*4)!=0)return false;
    uint64_t pa=kvtophys(r->memory);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(r->memory+16383)!=pa+16383)return false;
    /* No CPU access through the cached alias after clean+invalidate. */
    for(vm_offset_t a=r->memory;a<r->memory+16384;a+=64)
        __asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    vm_offset_t alias=ml_io_map_unmappable(pa,16384,VM_WIMG_WCOMB);
    if(!alias)return false;
    volatile uint32_t *out=(volatile uint32_t *)alias;
    for(unsigned i=0;i<4096;++i)out[i]=waffle_writeback_initial(i);
    __asm__ volatile("dsb sy":::"memory");
    for(unsigned i=0;i<4096;++i)if(out[i]!=waffle_writeback_initial(i)) {
        ml_io_unmap(alias,16384);return false;
    }
    uint64_t va=waffle_gpu_plan_alias(plan,r->address)+WAFFLE_GPU_WRITEBACK_OFFSET;
    uint32_t packet[9];
    if(waffle_writeback_packet(packet,9,44,va)!=9){ml_io_unmap(alias,16384);return false;}
    uint32_t commands[9],indirect[5];unsigned command_words=0;
    if(ib_requested()) {
        for(unsigned i=0;i<9;++i)commands[i]=packet[i];
        command_words=8;
        for(unsigned i=0;i<8;++i)out[256+i]=commands[i+1];
        __asm__ volatile("dsb sy":::"memory");
        for(unsigned i=0;i<8;++i)if(out[256+i]!=commands[i+1]) {
            ml_io_unmap(alias,16384);return false;
        }
        if(waffle_writeback_ib_packet(indirect,5,44,waffle_gpu_plan_alias(plan,r->address)+1024,8)!=5) {
            ml_io_unmap(alias,16384);return false;
        }
        say("waffle-gmu: GPU_IB begin VA=%llx words=8 staged_readback=1\n",waffle_gpu_plan_alias(plan,r->address)+1024);
    }
    say("waffle-gmu: GPU_WRITEBACK begin VA=%llx PA=%llx initial_zero=1 guards=2\n",va,pa+256);
    if(!hfi_exchange_watch(gmu,hfi_alias,ib_requested()?indirect:packet,ib_requested()?5:9,
        "GPU_WRITEBACK",true,plan))
        stop_unsafe("GPU writeback ACK failed; retain result alias");
    if(!wait_for(gmu,WAFFLE_GMU_REG(0x23b0c),1u<<23,0,2000))
        stop_unsafe("GPU writeback idle timeout; retain alias");
    /* Bounded NC polling observes the actual GPU transfer, not its ACK. */
    bool seen=false;
    for(unsigned attempt=0;attempt<2000;++attempt) {
        __asm__ volatile("dsb sy":::"memory");
        seen=true;
        for(unsigned i=0;i<4;++i)if(out[64+i]!=waffle_writeback_values[i])seen=false;
        if(seen)break;
        delay_for_interval(100,NSEC_PER_USEC);
    }
    unsigned wrong=0;
    for(unsigned i=0;i<4096;++i) {
        uint32_t expected=command_words && i>=256 && i<264 ? commands[i-255] : waffle_writeback_expected(i);
        if(out[i]!=expected) {
            if(!wrong)say("waffle-gmu: GPU_WRITEBACK mismatch index=%u got=%08x expected=%08x\n",i,out[i],expected);
            ++wrong;
        }
    }
    if(ib_requested())say("waffle-gmu: GPU_IB result=%u command_words=8; GPU fetch and writeback\n",seen&&!wrong);
    say("waffle-gmu: GPU_WRITEBACK values=%08x/%08x/%08x/%08x\n",out[64],out[65],out[66],out[67]);
    say("waffle-gmu: GPU_WRITEBACK result=%u wrong_words=%u checked=4096; no draw\n",seen&&!wrong,wrong);
    ml_io_unmap(alias,16384);
    return seen && !wrong;
}
/* Native kgsl_set_smmu_aperture: bind the CP SMMU register aperture to
 * the user context bank. Probe37/38 only, before CM3/GX start. Android reset
 * restores native policy; no guessed register offset or secure-mode change. */
static bool scm_gpu_aperture(unsigned selector,unsigned bank)
{
    if (selector>1 || bank>255) return false;
    uint64_t answer=0;
    int32_t status=scm_one(0x42000601,0x02000c1b,&answer);
    say("waffle-gmu: SCM CP SMMU aperture availability status=%d value=%llx\n",status,answer);
    if (status || answer!=1 || PAGE_SIZE!=16384) return false;
    vm_offset_t metadata=0,alias=0;
    if (kmem_alloc(kernel_map,&metadata,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) return false;
    uint64_t pa=kvtophys(metadata);
    bool ok=false;
    if (!pa || (pa&16383) || pa>=(1ULL<<36) ||
        kvtophys(metadata+PAGE_SIZE-1)!=pa+PAGE_SIZE-1) goto release;
    for (vm_offset_t p=metadata;p<metadata+PAGE_SIZE;p+=64)
        __asm__ volatile("dc civac, %0"::"r"(p):"memory");
    __asm__ volatile("dsb sy":::"memory");
    alias=ml_io_map_unmappable(pa,PAGE_SIZE,VM_WIMG_WCOMB);
    if (!alias) goto release;
    /* QCOM_SCM_ARGS(4): x5 points to args[3..9], all unused entries zero. */
    volatile uint8_t *extended=(volatile uint8_t *)alias;
    for (unsigned i=0;i<56;++i) extended[i]=0;
    waffle_scm_put64(extended,0xffffffffu);
    __asm__ volatile("dsb sy":::"memory");
    const uint64_t arguments[4]={0xffff0000u|(selector<<8)|bank,0xffffffffu,0xffffffffu,pa};
    for (unsigned retry=0;;++retry) {
        status=scm_raw(0x42000c1b,4,arguments,&answer);
        if (status!=-12 || retry==20) break;
        delay_for_interval(30000,NSEC_PER_USEC);
    }
    ok=status==0; /* Native qcom_scm_call checks transport status, not a1. */
    say("waffle-gmu: SCM CP SMMU aperture selector=%u CB%u status=%d result=%llx ready=%u\n",selector,bank,status,answer,ok);
release:
    if (alias) ml_io_unmap(alias,PAGE_SIZE);
    kmem_free(kernel_map,metadata,PAGE_SIZE);
    return ok;
}

bool waffle_scm_gpu_aperture(void) { return scm_gpu_aperture(0,0); }
bool waffle_scm_lpac_aperture(void) { return scm_gpu_aperture(1,1); }

bool waffle_scm_assign_pages(const uint64_t *pages,unsigned count,unsigned mode)
{
    if (!count || count>32 || mode>WAFFLE_SCM_RECLAIM_TABLE) return false;
    vm_offset_t metadata=0,alias=0;
    if (PAGE_SIZE!=WAFFLE_SCM_METADATA_SIZE ||
        kmem_alloc(kernel_map,&metadata,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) return false;
    uint64_t metadata_pa=kvtophys(metadata),arguments[4];
    bool valid=metadata_pa && !(metadata_pa&16383) && metadata_pa<(1ULL<<36) &&
        kvtophys(metadata+PAGE_SIZE-1)==metadata_pa+PAGE_SIZE-1;
    if (!valid) goto release;
    for (vm_offset_t p=metadata;p<metadata+PAGE_SIZE;p+=64)
        __asm__ volatile("dc civac, %0"::"r"(p):"memory");
    __asm__ volatile("dsb sy":::"memory");
    alias=ml_io_map_unmappable(metadata_pa,PAGE_SIZE,VM_WIMG_WCOMB);
    if (!alias) {valid=false;goto release;}
    valid=waffle_scm_assign_encode_mode((volatile uint8_t *)alias,PAGE_SIZE,metadata_pa,pages,count,mode,arguments);
    if (!valid) goto release;
    __asm__ volatile("dsb sy":::"memory");
    uint64_t answer=~0ULL;
    int32_t status=scm_raw(WAFFLE_SCM_ASSIGN_FUNCTION,WAFFLE_SCM_ASSIGN_ARGINFO,arguments,&answer);
    say("waffle-gmu: SCM pages mode=%u count=%u status=%d result=%llx\n",mode,count,status,answer);
    if (status || answer) stop_unsafe("SCM page ownership transition not confirmed");
release:
    if (alias) ml_io_unmap(alias,PAGE_SIZE);
    kmem_free(kernel_map,metadata,PAGE_SIZE);
    return valid;
}
static bool secure_page_probe(bool table)
{
    uint64_t answer=0;
    int32_t status=scm_one(0x42000601,0x02000c16,&answer);
    say("waffle-gmu: SCM MP_ASSIGN availability status=%d value=%llx\n",status,answer);
    if (status || answer!=1) return false;
    if (PAGE_SIZE!=WAFFLE_SCM_METADATA_SIZE) return false;
    vm_offset_t page=0,metadata=0,alias=0;
    if (kmem_alloc(kernel_map,&page,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) return false;
    if (kmem_alloc(kernel_map,&metadata,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) {
        kmem_free(kernel_map,page,PAGE_SIZE);return false;
    }
    uint64_t target_pa=kvtophys(page),metadata_pa=kvtophys(metadata),arguments[4];
    bool valid=target_pa && metadata_pa && !(target_pa&16383) && !(metadata_pa&16383) &&
        target_pa!=metadata_pa && target_pa<(1ULL<<36) && metadata_pa<(1ULL<<36) &&
        kvtophys(page+PAGE_SIZE-1)==target_pa+PAGE_SIZE-1 &&
        kvtophys(metadata+PAGE_SIZE-1)==metadata_pa+PAGE_SIZE-1;
    if (!valid) goto release;
    for (vm_offset_t p=page;p<page+PAGE_SIZE;p+=64)
        __asm__ volatile("dc civac, %0"::"r"(p):"memory");
    for (vm_offset_t p=metadata;p<metadata+PAGE_SIZE;p+=64)
        __asm__ volatile("dc civac, %0"::"r"(p):"memory");
    __asm__ volatile("dsb sy":::"memory");
    alias=ml_io_map_unmappable(metadata_pa,PAGE_SIZE,VM_WIMG_WCOMB);
    if (!alias) {valid=false;goto release;}
    valid=waffle_scm_assign_encode_mode((volatile uint8_t *)alias,PAGE_SIZE,metadata_pa,&target_pa,1,
        table?WAFFLE_SCM_SHARE_TABLE:WAFFLE_SCM_LOCK_DATA,arguments);
    if (!valid) goto release;
    __asm__ volatile("dsb sy":::"memory");
    say("waffle-gmu: SCM assign whole page PA=%llx table_share=%u\n",target_pa,table);
    answer=~0ULL;
    status=scm_raw(WAFFLE_SCM_ASSIGN_FUNCTION,WAFFLE_SCM_ASSIGN_ARGINFO,arguments,&answer);
    say("waffle-gmu: SCM assign status=%d result=%llx\n",status,answer);
    if (status || answer) stop_unsafe("protected page ownership uncertain after assign");
    if (table) {
        /* Native table ownership keeps HLOS RW and gives CP_PIXEL read only. */
        *(volatile uint64_t *)page=0x5441424c45534852ULL;
        valid=*(volatile uint64_t *)page==0x5441424c45534852ULL;
    }
    if (!waffle_scm_assign_encode_mode((volatile uint8_t *)alias,PAGE_SIZE,metadata_pa,&target_pa,1,
            table?WAFFLE_SCM_RECLAIM_TABLE:WAFFLE_SCM_RECLAIM_DATA,arguments))
        stop_unsafe("cannot encode protected page reclaim");
    __asm__ volatile("dsb sy":::"memory");
    answer=~0ULL;
    status=scm_raw(WAFFLE_SCM_ASSIGN_FUNCTION,WAFFLE_SCM_ASSIGN_ARGINFO,arguments,&answer);
    say("waffle-gmu: SCM reclaim status=%d result=%llx\n",status,answer);
    if (status || answer) stop_unsafe("protected page reclaim not confirmed");
    __asm__ volatile("dsb sy":::"memory");
    /* Only after confirmed HLOS ownership may the CPU touch or free it. */
    *(volatile uint64_t *)page=0x574146464c455343ULL;
    valid=valid && *(volatile uint64_t *)page==0x574146464c455343ULL;
    bzero((void *)page,PAGE_SIZE);
    say("waffle-gmu: SCM %s page roundtrip=%u; CPU access restored\n",table?"table":"protected",valid);
release:
    if (alias) ml_io_unmap(alias,PAGE_SIZE);
    kmem_free(kernel_map,metadata,PAGE_SIZE);
    kmem_free(kernel_map,page,PAGE_SIZE);
    return valid;
}
static bool secure_gpu_init(void)
{
    uint64_t answer = 0;
    say("waffle-gmu: SCM query GPU_INIT_REGS availability (SMC64 STD)\n");
    int32_t status = scm_one(0x42000601,0x02002801,&answer);
    say("waffle-gmu: SCM availability status=%d answer=%llx\n",status,answer);
    if (status || !answer) return false;
    /* ALWAYS + BCL + TSENSE, native Gen7.9.0 feature requests; first-boot trace confirms0xb/ret0. */
    say("waffle-gmu: SCM GPU_INIT_REGS request=0000000b\n");
    status = scm_one(0x42002801,11,&answer);
    say("waffle-gmu: SCM GPU_INIT_REGS status=%d result=%llx\n",status,answer);
    return status == 0;
}
struct power_sequence {
    vm_offset_t rsc, pdc;
    uint32_t saved[17], pdc_start, pdc_enable;
    bool changed, native_sleep;
};
/* Gen7.9.x is explicitly in adreno_is_gen7_2_x_family: use sequence154,
 * NOT180, and hidden TCS data80000021. All offsets below are DWORDS. */
static const struct {unsigned index; uint32_t value;} rsc_setup[] = {
    {0x4,1u<<24}, {0xb,1}, {0xe,0}, {0xd,0}, {0x10,0}, {0xf,0},
    {0x12,0x80000021}, {0x11,0}, {0x100,0},
    {0x8,0x4520}, {0x9,0x4510}, {0xa,0x4514},
    {0x154,0xeaaae5a0}, {0x155,0xe1a1ebab}, {0x156,0xa2e0a581},
    {0x157,0xecac82e2}, {0x158,0x0020edad},
};
/* PJD110 hardware-wired hidden TCS addresses. Vendor writes0 to these
 * fields, which reads back unchanged. Never overwrite them; require the
 * measured device routing before enabling any sequence. */
static uint32_t rsc_wired_address(unsigned index)
{
    if (index == 0xd) return 0x82204514;
    if (index == 0xf) return 0x82204510;
    if (index == 0x11) return 0x82204520;
    return 0;
}
static void power_sequence_restore(struct power_sequence *seq)
{
    if (!seq->changed) return;
    if (seq->native_sleep) {
        /* Native gen7_rscc_sleep_sequence polls ASLEEP, not SEQ_BUSY.
         * The sleep/wake program must remain installed while asleep.
         * CM3 is held reset and bus drains still precede freeing RAM. */
        if (!(rd(seq->rsc,4*4) & (1u<<16))) stop_unsafe("RSC lost asleep state");
        seq->changed = false;
        say("waffle-gmu: RSC/PDC retained in native asleep state; Android reset required before retry\n");
        return;
    }
    if (rd(seq->rsc,0x101*4)) stop_unsafe("RSC still busy during restore");
    wr(seq->pdc,0x1140*4,0); /* quiescent, CM3 must be held reset */
    for (unsigned i = sizeof(rsc_setup)/sizeof(rsc_setup[0]); i > 0; --i) {
        if (rsc_wired_address(rsc_setup[i-1].index)) continue;
        uint32_t value = seq->saved[i-1];
        if (rsc_setup[i-1].index == 4) value &= 1u<<24; /* only writable clock-gating bit */
        wr(seq->rsc,rsc_setup[i-1].index*4,value);
    }
    wr(seq->pdc,0x1148*4,seq->pdc_start);
    wr(seq->pdc,0x1140*4,seq->pdc_enable);
    bool restored = rd(seq->pdc,0x1148*4) == seq->pdc_start &&
        rd(seq->pdc,0x1140*4) == seq->pdc_enable;
    for (unsigned i = 0; i < sizeof(rsc_setup)/sizeof(rsc_setup[0]); ++i) {
        uint32_t mask = rsc_setup[i].index == 4 ? 1u<<24 : 0xffffffff;
        if ((rd(seq->rsc,rsc_setup[i].index*4) & mask) != (seq->saved[i] & mask)) restored = false;
    }
    if (!restored) stop_unsafe("RSC/PDC restore readback mismatch");
    seq->changed = false;
    say("waffle-gmu: RSC/PDC configuration restored\n");
}
static bool power_sequence_prepare(struct power_sequence *seq)
{
    bzero(seq,sizeof(*seq));
    seq->rsc = ml_io_map(WAFFLE_RSCC_BASE,WAFFLE_RSCC_SIZE);
    seq->pdc = ml_io_map(WAFFLE_GPU_PDC_BASE,WAFFLE_GPU_PDC_SIZE);
    if (!seq->rsc || !seq->pdc) return false;
    uint32_t busy = rd(seq->rsc,0x101*4);
    say("waffle-gmu: RSC status=%08x busy=%08x PDC enable=%08x\n",
        rd(seq->rsc,4*4),busy,rd(seq->pdc,0x1140*4));
    if (busy || (rd(seq->rsc,4*4) & (1u<<16))) {
        say("waffle-gmu: RSC busy/asleep; require Android reset before retry\n"); return false;
    }
    seq->pdc_start = rd(seq->pdc,0x1148*4);
    seq->pdc_enable = rd(seq->pdc,0x1140*4);
    for (unsigned i = 0; i < sizeof(rsc_setup)/sizeof(rsc_setup[0]); ++i)
        seq->saved[i] = rd(seq->rsc,rsc_setup[i].index*4);
    for (unsigned i = 0; i < sizeof(rsc_setup)/sizeof(rsc_setup[0]); ++i) {
        uint32_t wired = rsc_wired_address(rsc_setup[i].index);
        if (wired && seq->saved[i] != wired) {
            say("waffle-gmu: unexpected hardware-wired TCS address at index%03x\n",rsc_setup[i].index);
            return false;
        }
    }
    seq->changed = true;
    wr(seq->pdc,0x1140*4,0);
    for (unsigned i = 0; i < sizeof(rsc_setup)/sizeof(rsc_setup[0]); ++i)
        if (!rsc_wired_address(rsc_setup[i].index))
            wr(seq->rsc,rsc_setup[i].index*4,rsc_setup[i].value);
    wr(seq->pdc,0x1148*4,0);
    wr(seq->pdc,0x1140*4,0x80000001);
    uint32_t pdc_start = rd(seq->pdc,0x1148*4), pdc_enable = rd(seq->pdc,0x1140*4);
    say("waffle-gmu: PDC start=%08x enable=%08x (vendor write80000001)\n",pdc_start,pdc_enable);
    bool ok = pdc_start == 0 && pdc_enable == 0x80000001;
    for (unsigned i = 0; i < sizeof(rsc_setup)/sizeof(rsc_setup[0]); ++i) {
        uint32_t mask = rsc_setup[i].index == 4 ? 1u<<24 : 0xffffffff;
        uint32_t observed = rd(seq->rsc,rsc_setup[i].index*4);
        uint32_t expected = rsc_wired_address(rsc_setup[i].index);
        if (!expected) expected = rsc_setup[i].value;
        if ((observed & mask) != expected) {
            say("waffle-gmu: RSC index=%03x expected=%08x observed=%08x mask=%08x\n",
                rsc_setup[i].index,expected,observed,mask);
            ok = false;
        }
    }
    say("waffle-gmu: RSC/PDC Gen7.9 sequence readback=%s; no sleep/wake trigger\n",ok ? "matches" : "FAILED");
    return ok;
}
static const struct { uint32_t index, value; } gmu_boot_setup[] = {
        {0x1f8f1,1}, {0x1f8f0,1}, {0x1f81c,0}, {0x1f801,2},
        {0x1f985,WAFFLE_GMU_HFI_ADDRESS}, {0x1f984,1}, {0x1f986,0},
        {0x23b11,(1u<<31)|(0x32u<<18)|0x8a0}, {0x1f82d,0x4052},
        {0x1f9d0,0}, {0x1f9ce,0}, {0x1f9cf,0x07090100},
        {0x1f9cd,WAFFLE_GMU_LOG_ADDRESS|15},
        {0x1f40f,1}, {0x1f400,1}, {0x1f401,1},
        {0x1f993,0xffffffff}, {0x23b06,0xffffffff},
    };

/* State shared by begin/finish must outlive either callee's stack. */
struct gmu_boot_context {
    vm_offset_t gmu,qtb,gbif,cc,hfi_alias;
    struct waffle_gmu_plan *plan;
    unsigned probe,stop_evidence;
    struct gen7_live_probe live;
    struct power_sequence powerseq;
    bool slumber_attempted,slumber_ready,counter_changed,minimum_attempted;
    bool running,configured,cm3_released;
    uint32_t saved_counter,old_halt;
    uint64_t old_fence;
    uint32_t saved[sizeof(gmu_boot_setup)/sizeof(gmu_boot_setup[0])];
};
static bool gmu_boot_begin(struct gmu_boot_context *s)
{
    vm_offset_t gmu=s->gmu,qtb=s->qtb;
    struct waffle_gmu_plan *plan=s->plan;
    unsigned probe=s->probe;

    s->gbif = ml_io_map(WAFFLE_GPU_BASE + 0x3c00 * 4, 0x1000);
    s->cc = ml_io_map(WAFFLE_GPUCC_BASE, WAFFLE_GPUCC_SIZE);
    if (!s->gbif || !s->cc) return false;
    if (probe >= 11) {
        struct waffle_gmu_region *hfi = region_at(plan, WAFFLE_GMU_HFI_ADDRESS, PAGE_SIZE);
        if (!hfi) return false;
        /* Only the first physical16KB page: table+cmd/msg/debug rings.
         * The complete HFI allocation is not physically contiguous. */
        s->hfi_alias = ml_io_map_unmappable(kvtophys(hfi->memory), PAGE_SIZE, VM_WIMG_WCOMB);
        if (!s->hfi_alias) return false;
    }
    if (probe >= 15 && !power_sequence_prepare(&s->powerseq)) {
        power_sequence_restore(&s->powerseq);
        if (s->hfi_alias) ml_io_unmap(s->hfi_alias,PAGE_SIZE);
        return false;
    }
    if (probe >= 17 && !secure_gpu_init()) {
        power_sequence_restore(&s->powerseq);
        if (s->hfi_alias) ml_io_unmap(s->hfi_alias,PAGE_SIZE);
        return false;
    }
    if (probe >= 16 && rd(gmu,WAFFLE_GMU_REG(0x23b07)) != 0) {
        say("waffle-gmu: existing RSC control request; refuse test\n");
        power_sequence_restore(&s->powerseq);
        if (s->hfi_alias) ml_io_unmap(s->hfi_alias,PAGE_SIZE);
        return false;
    }
    s->old_halt = rd(s->gbif, 0x45 * 4);
    s->old_fence = *(volatile uint64_t *)(qtb + 0x410);
    /* All indices below are Gen7, relative to GPU_BASE, from gen7_reg.h.
     * Stage9 stops at FW_INIT_RESULT100; stage10 initializes HFI only.
     * No GPU voltage request,
     * SQE/AQE or TrustZone operation is issued.
     */

    s->configured=true;
    for (unsigned i = 0; i < sizeof(gmu_boot_setup)/sizeof(gmu_boot_setup[0]); ++i) {
        s->saved[i] = rd(gmu, WAFFLE_GMU_REG(gmu_boot_setup[i].index));
        wr(gmu, WAFFLE_GMU_REG(gmu_boot_setup[i].index), gmu_boot_setup[i].value);
    }
    wr(s->gbif, 0x45 * 4, 0);
    *(volatile uint64_t *)(qtb + 0x410) = s->old_fence & ~1ULL;
    __asm__ volatile("dsb sy" ::: "memory");
    if (!wait_for(qtb, 0x418, 1, 0, 10)) {
        say("waffle-gmu: QTB did not resume; CM3 stays reset\n");
        return false;
    }
    say("waffle-gmu: release CM3 reset, wait for firmware readiness (2s cap)\n");
    s->cm3_released=true;
    wr(gmu, WAFFLE_GMU_SYSRESET, 0);
    s->running = wait_for(gmu, WAFFLE_GMU_FW_INIT, 0x1ff, 0x100, 20000);
    say("waffle-gmu: FW_INIT=%08x ready=%u hostIRQ=%08x AOIRQ=%08x\n",
        rd(gmu, WAFFLE_GMU_FW_INIT), s->running, rd(gmu, WAFFLE_GMU_REG(0x1f992)),
        rd(gmu, WAFFLE_GMU_REG(0x23b05)));
    if (s->running && probe >= 10) {
        /* Isolate queue initialization from START/DCVS commands and power
         * sequencer programming. This bounded probe does not enter idle. */
        wr(gmu, WAFFLE_GMU_REG(0x1f986), 1);
        bool hfi_ready = wait_for(gmu, WAFFLE_GMU_REG(0x1f980), 1, 1, 1000);
        say("waffle-gmu: HFI init status=%08x ready=%u hostIRQ=%08x AOIRQ=%08x\n",
            rd(gmu, WAFFLE_GMU_REG(0x1f980)), hfi_ready,
            rd(gmu, WAFFLE_GMU_REG(0x1f992)), rd(gmu, WAFFLE_GMU_REG(0x23b05)));
        s->running = hfi_ready;
        if (s->running && probe >= 11) {
            const uint32_t query[] = {(1u << 20) | (3u << 8) | 12u,122,0};
            s->running = hfi_exchange(gmu, s->hfi_alias, query, 3, "GET_VALUE122", false);
        }
        if (s->running && probe >= 12) {
            uint32_t version = rd(gmu, WAFFLE_GMU_DTCM + 0xffc * 4);
            say("waffle-gmu: HFI firmware version=%08x; PERF table only, no START/DCVS\n", version);
            if (version < 0x20060001u) s->running = false;
            else s->running = hfi_exchange(gmu, s->hfi_alias, waffle_hfi_perf_table,
                sizeof(waffle_hfi_perf_table)/sizeof(uint32_t), "PERF_TABLE", true);
        }
    }
    if (s->running && probe >= 13)
        s->running = hfi_exchange(gmu, s->hfi_alias, waffle_hfi_bw_table,
            sizeof(waffle_hfi_bw_table)/sizeof(uint32_t), "BW_TABLE", true);
    if (s->running && probe>=14) s->running=hfi_boot_features(gmu,s->hfi_alias,probe);
    if (s->running && probe >= 25) s->running=hfi_start_capture(gmu,s->hfi_alias,plan,probe);
    if (s->running && probe >= 17 && (probe < 25 || probe >= 31)) {
        /* Lowest captured stock level: GXindex1=231MHz, DDRindex1.
         * No OOB_GPU or CP/SQE/AQE start; always notify slumber afterwards. */
        s->minimum_attempted = true;
        s->running = hfi_boot_votes(gmu,s->hfi_alias,probe);
        say("waffle-gmu: after minimum vote GXstatus=%08x GDSCR=%08x DCVSreturn=%08x\n",
            rd(gmu,WAFFLE_GMU_REG(0x1f8d0)),rd(s->cc,WAFFLE_GPU_GX_GDSCR),
            rd(gmu,WAFFLE_GMU_REG(0x1cbff)));
    }
    if(s->running && (probe==93 || probe==94) && !waffle_gpu_native_runtime_clock(probe))
        stop_unsafe("native GMU260 transition failed; retain PLL and power");
    if (s->running && probe >= 18 && (probe < 25 || probe >= 31)) s->running = gpu_power_probe(gmu,s->cc,plan,probe,s->hfi_alias,&s->live);
    return s->running;
}
static bool gmu_boot_finish(struct gmu_boot_context *s)
{
    vm_offset_t gmu=s->gmu,qtb=s->qtb;
    struct waffle_gmu_plan *plan=s->plan;
    unsigned probe=s->probe;
    if(!s->cm3_released)goto restore;
    if ((s->running || s->minimum_attempted) && probe >= 16 && (probe < 25 || probe >= 31)) {
        bool exercise_ok = s->running;
        const uint32_t slumber[] = {((plan->session_slumber_sequence ? plan->session_slumber_sequence : probe==94 && writeback_requested() ? 45u : probe==94 && zap_requested() ? 44u : probe>=79 ? 43u : probe>=33 ? 35u : probe >= 31 ? 33u : probe >= 24 ? 14u : probe >= 17 ? 8u : 7u)<<20)|(3u<<8)|33u,1,1};
        s->saved_counter = rd(gmu,WAFFLE_GMU_REG(0x1f840));
        s->counter_changed = true;
        wr(gmu,WAFFLE_GMU_REG(0x1f840),0);
        s->slumber_attempted = true;
        s->running = hfi_exchange(gmu,s->hfi_alias,slumber,3,"PREPARE_SLUMBER",true);
        s->slumber_ready = s->running && wait_for(gmu,WAFFLE_GMU_REG(0x23b0c),1u<<30,0,1000);
        say("waffle-gmu: slumber idle=%u busy=%08x powerstate=%08x\n",s->slumber_ready,
            rd(gmu,WAFFLE_GMU_REG(0x23b0c)),rd(gmu,WAFFLE_GMU_REG(0x1f8ec)));
        if (s->slumber_ready) s->stop_evidence|=WAFFLE_GEN7_STOP_SLUMBER;
        s->running = exercise_ok && s->slumber_ready;
    }
    wr(gmu, WAFFLE_GMU_REG(0x1f8f1), 1);
    wr(gmu, WAFFLE_GMU_REG(0x23b14), 7);
    wr(gmu, WAFFLE_GMU_REG(0x23b10), 0);
    wr(gmu, WAFFLE_GMU_SYSRESET, 1);
    if (!wait_for(gmu, WAFFLE_GMU_SYSRESET, 1, 1, 100)) stop_unsafe("CM3 reset readback failed");
    s->stop_evidence|=WAFFLE_GEN7_STOP_CM3_RESET;
    if (s->slumber_attempted) {
        if (!s->slumber_ready) stop_unsafe("slumber command/idle failed after CM3 reset");
        wr(gmu,WAFFLE_GMU_REG(0x23b07),1);
        bool asleep = wait_for(s->powerseq.rsc,4*4,1u<<16,1u<<16,1000);
        wr(gmu,WAFFLE_GMU_REG(0x23b07),0);
        say("waffle-gmu: RSC sleep complete=%u busy=%08x status=%08x\n",
            asleep,rd(s->powerseq.rsc,0x101*4),rd(s->powerseq.rsc,4*4));
        if (!asleep) stop_unsafe("RSC sleep failed");
        s->powerseq.native_sleep = true;
        s->stop_evidence|=WAFFLE_GEN7_STOP_RSC_ASLEEP;
    }
    uint32_t gx_status = rd(gmu, WAFFLE_GMU_REG(0x1f8d0));
    say("waffle-gmu: GX power/clock status=%08x GDSCR=%08x\n", gx_status, rd(s->cc, WAFFLE_GPU_GX_GDSCR));
    if (!(gx_status & 1) || (rd(s->cc, WAFFLE_GPU_GX_GDSCR) & (1u << 31)))
        stop_unsafe("GX unexpectedly powered");
    s->stop_evidence|=WAFFLE_GEN7_STOP_GX_OFF;
    wr(s->gbif, 0x45 * 4, 2);
    if (!wait_for(s->gbif, 0x46 * 4, 2, 2, 100)) stop_unsafe("GBIF drain timeout");
    s->stop_evidence|=WAFFLE_GEN7_STOP_GBIF_DRAINED;
    *(volatile uint64_t *)(qtb + 0x410) = s->old_fence | 1;
    __asm__ volatile("dsb sy" ::: "memory");
    if (!wait_for(qtb, 0x418, 1, 1, 10)) stop_unsafe("QTB drain timeout");
    s->stop_evidence|=WAFFLE_GEN7_STOP_QTB_DRAINED;
    if (probe>=33) gpu_gen7_live_finish(&s->live,s->stop_evidence);
    if(plan->submit_session)submit_session_destroy(plan,s->stop_evidence);
    for (unsigned i = 0; i < plan->count; ++i) {
        struct waffle_gmu_region *r = &plan->regions[i];
        for (vm_offset_t a = r->memory; a < r->memory + r->size; a += 64)
            __asm__ volatile("dc ivac, %0" :: "r"(a) : "memory");
    }
    __asm__ volatile("dsb sy" ::: "memory");
    say("waffle-gmu: CM3 held reset again; GBIF/QTB drained; FW readiness=%u\n", s->running);
    struct waffle_gmu_region *log = region_at(plan, WAFFLE_GMU_LOG_ADDRESS, 64);
    if (log) {
        uint32_t *words = (uint32_t *)log->memory;
        say("waffle-gmu: log header %08x %08x %08x %08x %08x %08x %08x %08x\n",
            words[0],words[1],words[2],words[3],words[4],words[5],words[6],words[7]);
    }
restore:
    if (s->counter_changed) wr(gmu,WAFFLE_GMU_REG(0x1f840),s->saved_counter);
    power_sequence_restore(&s->powerseq);
    if (s->hfi_alias) ml_io_unmap(s->hfi_alias, PAGE_SIZE);
    for (unsigned i = sizeof(gmu_boot_setup)/sizeof(gmu_boot_setup[0]); i > 0; --i)
        wr(gmu, WAFFLE_GMU_REG(gmu_boot_setup[i-1].index), s->saved[i-1]);
    wr(s->gbif, 0x45 * 4, s->old_halt);
    *(volatile uint64_t *)(qtb + 0x410) = s->old_fence;
    __asm__ volatile("dsb sy" ::: "memory");
    return (rd(gmu, WAFFLE_GMU_SYSRESET) & 1) && s->running;
}
static bool boot_probe(vm_offset_t gmu,vm_offset_t qtb,struct waffle_gmu_plan *plan,unsigned probe)
{
    if(probe==27 || probe==28)return secure_page_probe(probe==28);
    struct gmu_boot_context fallback={0},*s=&fallback;
    vm_offset_t allocation=0;
    if(session_requested()) {
        if(sizeof(*s)>PAGE_SIZE || kmem_alloc(kernel_map,&allocation,PAGE_SIZE,
            KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
        s=(struct gmu_boot_context *)allocation;
    }
    *s=(struct gmu_boot_context){.gmu=gmu,.qtb=qtb,.plan=plan,.probe=probe};
    bool begun=gmu_boot_begin(s),ok=false;
    if(s->configured) {
        if(plan->submit_session) {
            say("waffle-gmu: GMU_OWNER begin returned heap=%u; state retained\n",allocation!=0);
            bool submitted=begun && submit_session_run(plan);
            if(!submit_session_close(plan))stop_unsafe("session cannot release OOB with uncertain completion");
            s->running=submitted;
        }
        ok=gmu_boot_finish(s);
    }
    if(allocation) {
        /* A live/unknown engine never reaches here: finish retains on failure. */
        if(plan->submit_session)stop_unsafe("GMU owner cannot free an active submission session");
        kmem_free(kernel_map,allocation,PAGE_SIZE);
        say("waffle-gmu: GMU_OWNER released after finish result=%u\n",ok);
    }
    return ok;
}
struct waffle_tcm_context {
    vm_offset_t gmu,backup;
    size_t total;
    bool boot,restore_ready;
};
static bool tcm_owner_load(struct waffle_tcm_context *c,struct waffle_gmu_plan *plan,unsigned probe)
{

    c->boot = probe >= 9;
    c->gmu = ml_io_map(WAFFLE_GMU_BASE, WAFFLE_GMU_SIZE);
    if (!c->gmu || !(*(volatile uint32_t *)(c->gmu + WAFFLE_GMU_SYSRESET) & 1)) return false;
    size_t cursor = 0;
    struct waffle_fw_block b;
    int result;
    while ((result = waffle_fw_next(plan->firmware, plan->length, &cursor, &b)) == 1) {
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (b.size && kind && kind <= 2) c->total += b.size;
    }
    if (result < 0 || !c->total || c->total > 32768) return false;
    if (c->boot) c->total = 32768;
    if (kmem_alloc(kernel_map, &c->backup, round_page(c->total), KMA_KOBJECT | KMA_ZERO | KMA_DATA,
            VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) return false;
    cursor = 0;
    size_t saved = 0;
    /* Save ALL touched words before the first write, so overlapping firmware
     * payloads cannot make the backup depend on earlier payload writes.
     */
    while (waffle_fw_next(plan->firmware, plan->length, &cursor, &b) == 1) {
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (!b.size || !kind || kind > 2) continue;
        uint32_t offset = kind == 1 ? WAFFLE_GMU_ITCM + b.address :
            WAFFLE_GMU_DTCM + b.address - 0x10004000;
        for (unsigned n = 0; n < b.size; n += 4)
            *(uint32_t *)(c->backup + saved + n) = *(volatile uint32_t *)(c->gmu + offset + n);
        saved += b.size;
    }
    if (c->boot) for (unsigned n = 0; n < 16384; n += 4) {
        *(uint32_t *)(c->backup + n) = rd(c->gmu, WAFFLE_GMU_ITCM + n);
        *(uint32_t *)(c->backup + 16384 + n) = rd(c->gmu, WAFFLE_GMU_DTCM + n);
    }
    cursor = 0;
    bool ok = true;
    while (waffle_fw_next(plan->firmware, plan->length, &cursor, &b) == 1) {
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (!b.size || !kind || kind > 2) continue;
        uint32_t offset = kind == 1 ? WAFFLE_GMU_ITCM + b.address :
            WAFFLE_GMU_DTCM + b.address - 0x10004000;
        for (unsigned n = 0; n < b.size; n += 4)
            *(volatile uint32_t *)(c->gmu + offset + n) = waffle_fw_u32(b.payload + n);
        __asm__ volatile("dsb sy" ::: "memory");
        for (unsigned n = 0; n < b.size; n += 4)
            if (*(volatile uint32_t *)(c->gmu + offset + n) != waffle_fw_u32(b.payload + n)) ok = false;
        say("waffle-gmu: TCM %08x bytes=%u readback=%s\n", b.address, b.size, ok ? "matches" : "FAILED");
    }
    c->restore_ready=true;
    return ok;
}
static bool tcm_owner_restore(struct waffle_tcm_context *c,struct waffle_gmu_plan *plan)
{
    if(!c->restore_ready || !c->backup || !(rd(c->gmu,WAFFLE_GMU_SYSRESET)&1))
        stop_unsafe("TCM snapshot cannot restore while CM3 state is unknown");
    size_t cursor=0,saved=0;
    struct waffle_fw_block b;
    while (waffle_fw_next(plan->firmware, plan->length, &cursor, &b) == 1) {
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (!b.size || !kind || kind > 2) continue;
        uint32_t offset = kind == 1 ? WAFFLE_GMU_ITCM + b.address :
            WAFFLE_GMU_DTCM + b.address - 0x10004000;
        for (unsigned n = 0; n < b.size; n += 4)
            *(volatile uint32_t *)(c->gmu + offset + n) = c->boot ?
                rd(c->backup, (kind == 1 ? b.address : 16384 + b.address - 0x10004000) + n) :
                *(uint32_t *)(c->backup + saved + n);
        saved += b.size;
    }
    if (c->boot) for (unsigned n = 0; n < 16384; n += 4) {
        wr(c->gmu, WAFFLE_GMU_ITCM + n, *(uint32_t *)(c->backup + n));
        wr(c->gmu, WAFFLE_GMU_DTCM + n, *(uint32_t *)(c->backup + 16384 + n));
    }
    __asm__ volatile("dsb sy" ::: "memory");
    cursor = 0; saved = 0;
    bool restored = true;
    if (c->boot) for (unsigned n = 0; n < 16384; n += 4)
        if (rd(c->gmu, WAFFLE_GMU_ITCM + n) != rd(c->backup, n) ||
            rd(c->gmu, WAFFLE_GMU_DTCM + n) != rd(c->backup, 16384 + n)) restored = false;
    while (waffle_fw_next(plan->firmware, plan->length, &cursor, &b) == 1) {
        unsigned kind = waffle_fw_region(b.address, b.size);
        if (!b.size || !kind || kind > 2) continue;
        uint32_t offset = kind == 1 ? WAFFLE_GMU_ITCM + b.address :
            WAFFLE_GMU_DTCM + b.address - 0x10004000;
        for (unsigned n = 0; n < b.size; n += 4) {
            uint32_t original = c->boot ? rd(c->backup, (kind == 1 ? b.address : 16384 + b.address - 0x10004000) + n) :
                *(uint32_t *)(c->backup + saved + n);
            if (*(volatile uint32_t *)(c->gmu + offset + n) != original) restored = false;
        }
        saved += b.size;
    }
    if(!restored)stop_unsafe("TCM restoration readback failed; retain snapshot owner");
    kmem_free(kernel_map, c->backup, round_page(c->total));
    c->backup=0;c->restore_ready=false;
    say("waffle-gmu: TCM restore readback=%s; boot_test=%u CM3 held reset\n", restored ? "matches" : "FAILED", c->boot);
    return restored;}
bool waffle_gmu_probe_tcm(struct waffle_gmu_plan *plan,unsigned probe,vm_offset_t qtb)
{
    struct waffle_tcm_context tcm={0};
    bool ok=tcm_owner_load(&tcm,plan,probe);
    if(!tcm.restore_ready)return false;
    if(ok && tcm.boot)ok=boot_probe(tcm.gmu,qtb,plan,probe);
    bool restored=tcm_owner_restore(&tcm,plan);
    return ok && restored;
}
/* This component owns all GMU/TCM state. Parent must retain plan and SMMU. */
struct waffle_gmu_owner {
    struct waffle_tcm_context tcm;
    struct gmu_boot_context boot;
    struct waffle_gmu_plan *plan;
    vm_offset_t allocation;
    bool exercise_ok;
};
struct waffle_gmu_owner *waffle_gmu_owner_begin(struct waffle_gmu_plan *plan,unsigned probe,vm_offset_t qtb)
{
    if(!plan || probe!=94 || !session_requested() || plan->submit_session ||
        sizeof(struct waffle_gmu_owner)>PAGE_SIZE)return NULL;
    vm_offset_t allocation=0;
    if(kmem_alloc(kernel_map,&allocation,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
        VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
    struct waffle_gmu_owner *owner=(struct waffle_gmu_owner *)allocation;
    owner->allocation=allocation;owner->plan=plan;owner->exercise_ok=true;
    if(!tcm_owner_load(&owner->tcm,plan,probe))goto failed;
    owner->boot=(struct gmu_boot_context){.gmu=owner->tcm.gmu,.qtb=qtb,.plan=plan,.probe=probe};
    if(!gmu_boot_begin(&owner->boot) || !plan->submit_session)goto failed;
    say("waffle-gmu: GMU_OWNER begin returned heap=1; state retained\n");
    say("waffle-gmu: TCM_OWNER begin returned snapshot=32768 heap=1 OOB=1\n");
    return owner;
failed:
    if(owner->boot.configured) {
        if(plan->submit_session && !submit_session_close(plan))
            stop_unsafe("GMU constructor cannot release active submission owner");
        (void)gmu_boot_finish(&owner->boot);
    }
    if(owner->tcm.restore_ready)(void)tcm_owner_restore(&owner->tcm,plan);
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    return NULL;
}
static bool owner_copy_sequence(struct waffle_gmu_owner *);
static bool owner_glsl_prepare(struct waffle_gmu_owner *);
bool waffle_gmu_owner_exercise(struct waffle_gmu_owner *owner)
{
    if(!owner || !owner->plan->submit_session)return false;
    owner->exercise_ok=owner->plan->compute_image==9?owner_glsl_prepare(owner):owner->plan->compute_image==4?owner_copy_sequence(owner):submit_session_run(owner->plan);
    return owner->exercise_ok;
}
bool waffle_gmu_owner_end(struct waffle_gmu_owner *owner)
{
    if(!owner || !owner->plan->submit_session)return false;
    if(!submit_session_close(owner->plan))stop_unsafe("GMU owner cannot stop with uncertain completion");
    owner->boot.running=owner->exercise_ok;
    bool ok=gmu_boot_finish(&owner->boot);
    bool restored=tcm_owner_restore(&owner->tcm,owner->plan);
    if(owner->plan->submit_session)stop_unsafe("GMU owner still has an active child session");
    vm_offset_t allocation=owner->allocation;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    say("waffle-gmu: TCM_OWNER released after GMU stop and snapshot restoration result=%u\n",ok&&restored);
    return ok && restored;
}

static uint32_t gen7_config_read(void *context,uint32_t index)
{
    struct gen7_config_io *io=context;
    if (!waffle_gen7_index_allowed(index)) stop_unsafe("Gen7 register outside mapped domains");
    uint32_t value=index<0x10000u ? rd(io->gpu,index*4) : rd(io->gmu,WAFFLE_GMU_REG(index));
    if (index==0x50b) say("waffle-gmu: Gen7 busy-mask read=%08x\n",value);
    return value;
}
static void gen7_config_write(void *context,uint32_t index,uint32_t value)
{
    struct gen7_config_io *io=context;
    if (!waffle_gen7_index_allowed(index)) stop_unsafe("Gen7 register outside mapped domains");
    if (index==0x50b) say("waffle-gmu: Gen7 busy-mask write=%08x\n",value);
    if (index<0x10000u) wr(io->gpu,index*4,value);
    else wr(io->gmu,WAFFLE_GMU_REG(index),value);
}
static void gen7_config_mismatch(void *context,uint32_t index,uint32_t expected,uint32_t actual,bool restoring)
{
    (void)context;
    say("waffle-gmu: Gen7 config mismatch index=%x expected=%08x actual=%08x restoring=%u\n",
        index,expected,actual,restoring);
}
static void gen7_clock_delay(void *context,unsigned usec)
{
    (void)context;
    delay_for_interval(usec,NSEC_PER_USEC);
}
struct clock_measure_context {vm_offset_t gcc,gpucc;};
static uint32_t clock_measure_read(void *opaque,unsigned bank,uint32_t off)
{
    struct clock_measure_context *c=opaque;
    return rd(bank?c->gpucc:c->gcc,off);
}
static void clock_measure_write(void *opaque,unsigned bank,uint32_t off,uint32_t value)
{
    struct clock_measure_context *c=opaque;
    wr(bank?c->gpucc:c->gcc,off,value);
}
static bool gen7_measure_clocks(unsigned probe)
{
    uint32_t requested=0;
    if(!PE_parse_boot_argn("waffle_gpu_measure",&requested,sizeof(requested)))return true;
    if(requested!=1 || probe!=93)return false;
    /* ml_io_map uses permanent io_submap mappings. Only the unmappable
     * variant allocates from kernel_map and may be paired with ml_io_unmap. */
    struct clock_measure_context context={
        ml_io_map_unmappable(WAFFLE_GCC_BASE,round_page(WAFFLE_GCC_SIZE),VM_WIMG_IO),
        ml_io_map_unmappable(WAFFLE_GPUCC_BASE,round_page(WAFFLE_GPUCC_SIZE),VM_WIMG_IO)};
    if(!context.gcc || !context.gpucc)return false;
    const struct waffle_measure_io io={&context,clock_measure_read,clock_measure_write,gen7_clock_delay};
    struct waffle_measure_result gfx={0},gmu={0};
    bool a=waffle_measure_clock(&io,0xf,&gfx);
    if(!gfx.restored)stop_unsafe("GFX debug mux restore unverified");
    bool b=waffle_measure_clock(&io,0x1f,&gmu);
    if(!gmu.restored)stop_unsafe("GMU debug mux restore unverified");
    say("waffle-gmu: CLOCK_MEASURE GFX hz=%llu short=%u full=%u complete=%u restored=%u\n",
        gfx.hz,gfx.short_count,gfx.full_count,gfx.complete,gfx.restored);
    say("waffle-gmu: CLOCK_MEASURE GMU hz=%llu short=%u full=%u complete=%u restored=%u\n",
        gmu.hz,gmu.short_count,gmu.full_count,gmu.complete,gmu.restored);
    say("waffle-gmu: CLOCK_MEASURE result=%u; no CP RAW\n",a&&b);
    ml_io_unmap(context.gcc,round_page(WAFFLE_GCC_SIZE));
    ml_io_unmap(context.gpucc,round_page(WAFFLE_GPUCC_SIZE));
    return a&&b;
}
static int gen7_hwcg_exercise(void *context)
{
    const struct waffle_gen7_io io={context,gen7_config_read,gen7_config_write,gen7_config_mismatch,NULL};
    say("waffle-gmu: Gen7 HWCG initial global=%x status=%x\n",
        gen7_config_read(context,WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL),
        gen7_config_read(context,WAFFLE_GEN7_RBBM_CGC_P2S_STATUS));
    uint32_t status=0,index=0;
    int result=waffle_gen7_hwcg_probe(&io,gen7_clock_delay,&status,&index);
    say("waffle-gmu: Gen7 HWCG result=%d TXDONE=%u status=%x failed_index=%x; native off/restore complete=%u\n",
        result,!!(status&1),status,index,result!=-3);
    return result;
}
static bool gpu_gen7_configuration_probe(vm_offset_t gpu,vm_offset_t gmu,struct waffle_gmu_plan *plan,unsigned probe)
{
    struct waffle_gmu_region *power=region_at(plan,WAFFLE_GPU_PWRUP_ADDRESS,4096);
    if (!power || !power->gpu_only || power->readonly ||
        plan->protected_address!=(probe>=56?0x100000000ULL:0xa0000000u) || plan->protected_size!=0x400000u) return false;
    struct gen7_config_io context={.gpu=gpu,.gmu=gmu};
    const struct waffle_gen7_io io={&context,gen7_config_read,gen7_config_write,gen7_config_mismatch,
        probe==32?gen7_hwcg_exercise:NULL};
    uint32_t failed_index=0;
    int result=waffle_gen7_config_probe(&io,(uint32_t *)power->memory,power->size/4,&failed_index);
    if (result==-3) stop_unsafe("Gen7 configuration/clock restore failed");
    if (!result) {
        for (vm_offset_t p=power->memory;p<power->memory+616;p+=64)
            __asm__ volatile("dc cvac, %0"::"r"(p):"memory");
        __asm__ volatile("dsb sy":::"memory");
    }
    say("waffle-gmu: Gen7 native configuration result=%d failed_index=%x; CP disabled, HWCG %s, registers restored\n",
        result,failed_index,probe==32?"exercised":"deferred");
    if (!result) say("waffle-gmu: Gen7 restore list ready VA=%x bytes=616 ifpc=58 preempt=17 dynamic=0\n",power->address);
    return result==0;
}

static bool gen7_live_prepare(void *context)
{
    struct gen7_config_io *io=context;
    if (!io->power || io->power->size<616) return false;
    for (vm_offset_t p=io->power->memory;p<io->power->memory+616;p+=64)
        __asm__ volatile("dc cvac, %0"::"r"(p):"memory");
    __asm__ volatile("dsb sy":::"memory");
    if (io->plan && io->plan->fault_smmu && !io->plan->raw_stage_pause) {
        say("waffle-gmu: CP diagnostic pre-publication pause; SMMU stall armed\n");
        delay_for_interval(1500000,NSEC_PER_USEC);
    }
    return true;
}
static bool gen7_restore_snapshot(const struct waffle_gmu_region *power,unsigned probe)
{
    if (!power || !power->memory || power->size<616) return false;
    const uint32_t *list=(const uint32_t *)power->memory;
    for(unsigned i=0;i<154;i++)
        say("waffle-gmu: RESTORE_SNAPSHOT probe=%u word[%u]=%08x\n",probe,i,list[i]);
    say("waffle-gmu: RESTORE_SNAPSHOT complete probe=%u words=154; RAW not sent\n",probe);
    return true;
}
static bool gen7_ramlog_manifest(const struct waffle_gmu_plan *plan,unsigned probe)
{
    unsigned seen=0,pages=0;
    if (!plan || PAGE_SIZE!=0x4000) return false;
    for(unsigned i=0;i<plan->count;i++) {
        const struct waffle_gmu_region *r=&plan->regions[i];
        unsigned bit=r->address==WAFFLE_GMU_LOG_ADDRESS?1u:r->address==WAFFLE_GMU_HFI_ADDRESS?2u:0u;
        if (!bit) continue;
        unsigned bytes=bit==1?0x10000u:0x4000u;
        if ((seen&bit) || !r->memory || r->size<bytes) return false;
        seen|=bit;
        for(unsigned off=0;off<bytes;off+=0x4000) {
            uint64_t pa=kvtophys(r->memory+off);
            if ((pa&0x3fff) || pa<0x8c0000000ULL || pa>0xbffffc000ULL ||
                kvtophys(r->memory+off+0x3fff)!=pa+0x3fff) return false;
            say("waffle-gmu: RAM_LOG %s %u pa=%llx bytes=4000\n",
                bit==1?"GMU_LOG":"HFI",off/0x4000,(unsigned long long)pa);
            pages++;
        }
    }
    if (seen!=3 || pages!=5) return false;
    say("waffle-gmu: RAM_LOG_MANIFEST complete probe=%u pages=5\n",probe);
    return true;
}
static bool gen7_live_exchange(void *context,const uint32_t *packet,unsigned words,bool zero_ack)
{
    struct gen7_config_io *io=context;
    if (io->probe==59 && !gen7_ramlog_manifest(io->plan,io->probe)) {
        say("waffle-gmu: RAM_LOG_MANIFEST refused; RAW not sent\n");
        return false;
    }
    if ((io->probe==53 || io->probe==55 || io->probe==57 || io->probe==59 || io->probe==64 || io->probe==66 || io->probe==68 || io->probe==70 || io->probe==71 || io->probe==73 || io->probe==76 || io->probe==80 || io->probe==82 || io->probe==85 || io->probe==86 || io->probe==89 || io->probe==91 || io->probe==94)) {
        say("waffle-gmu: PRE_RAW_SNAPSHOT words=%u CPstate=%08x AO_busy=%08x\n",
            words,rd(io->gpu,0x808*4),rd(io->gmu,WAFFLE_GMU_REG(0x23b0c)));
        for(unsigned i=0;i<words;i++) say("waffle-gmu: PRE_RAW packet[%u]=%08x\n",i,packet[i]);
        const uint32_t *list=(const uint32_t *)io->power->memory;
        for(unsigned i=0;i<16;i++) say("waffle-gmu: PRE_RAW restore[%u]=%08x\n",i,list[i]);
        if (io->probe!=68 && io->probe!=70 && io->probe!=71 && io->probe!=73 && io->probe!=76 && io->probe!=80 && io->probe!=82 && io->probe!=85 && io->probe!=86 && io->probe!=89 && io->probe!=91 && io->probe!=94) {
        say("waffle-gmu: PRE_RAW_HOLD begin 5s; RAW not sent yet\n");
        delay_for_interval(5000000,NSEC_PER_USEC);
        say("waffle-gmu: PRE_RAW_HOLD end; publishing RAW\n");
        }
    }
    return hfi_exchange_watch(io->gmu,io->hfi_alias,packet,words,words==3?"CP_THREAD_RAW":"CP_INIT_RAW",zero_ack,io->plan);
}
static bool gpu_gen7_live_start(struct gen7_live_probe *live,vm_offset_t gpu,vm_offset_t gmu,
    vm_offset_t hfi_alias,struct waffle_gmu_plan *plan,unsigned probe)
{
    struct waffle_gmu_region *power=region_at(plan,WAFFLE_GPU_PWRUP_ADDRESS,4096);
    struct waffle_gmu_region *sqe=region_at(plan,WAFFLE_GPU_SQE_ADDRESS,4);
    struct waffle_gmu_region *aqe=region_at(plan,WAFFLE_GPU_AQE_ADDRESS,4);
    if (!live || !hfi_alias || !power || !power->gpu_only || power->readonly ||
        !sqe || !aqe || !sqe->gpu_only || !aqe->gpu_only || !sqe->readonly || !aqe->readonly ||
        plan->protected_address!=(probe>=56?0x100000000ULL:0xa0000000u) || plan->protected_size!=0x400000u) return false;
    plan->raw_stage_pause=probe==68 || probe==70 || probe==71 || probe==73 || probe==76 || probe==80 || probe==82 || probe==85 || probe==86 || probe==89 || probe==91 || probe==94;
    live->state.config.native_trusted_window=probe>=56;
    if (probe>=56) say("waffle-gmu: native trusted window base=f0000000 size=fffff000 protected_VA=100000000\n");
    live->context=(struct gen7_config_io){.gpu=gpu,.gmu=gmu,.hfi_alias=hfi_alias,.power=power,.plan=plan,.probe=probe};
    const struct waffle_gen7_io registers={&live->context,gen7_config_read,gen7_config_write,gen7_config_mismatch,NULL};
    const struct waffle_gen7_cp_io io={&registers,gen7_live_prepare,gen7_live_exchange,gen7_clock_delay};
    uint64_t sqe_va=plan->split_gpu_va?waffle_gpu_plan_alias(plan,WAFFLE_GPU_SQE_ADDRESS):WAFFLE_GPU_SQE_ADDRESS;
    uint64_t aqe_va=plan->split_gpu_va?waffle_gpu_plan_alias(plan,WAFFLE_GPU_AQE_ADDRESS):WAFFLE_GPU_AQE_ADDRESS;
    uint64_t restore_va=plan->split_gpu_va?waffle_gpu_plan_alias(plan,WAFFLE_GPU_PWRUP_ADDRESS):WAFFLE_GPU_PWRUP_ADDRESS;
    if (plan->split_gpu_va) say("waffle-gmu: native global GPU VA SQE=%llx AQE=%llx restore=%llx\n",sqe_va,aqe_va,restore_va);
    int result=(probe==35 || probe==36 || probe==71 || probe==73 || probe==76 || probe==80 || probe==82 || probe==85) ?
        waffle_gen7_boot_thread_start(&io,&live->state,(uint32_t *)power->memory,power->size/4,
        sqe_va,aqe_va,restore_va,(probe==80 || probe==82 || probe==85 || probe==86 || probe==89 || probe==91 || probe==94)?42:34) : (probe==34 || probe==37 || probe==39 || probe==41 || probe==43 || probe==48 || probe==50 || probe==52 || probe==54 || probe==56 || probe==58 || probe==60 || probe==62 || probe==63 || probe==65 || probe==67 || probe==69 || probe==72 || probe==74 || probe==75 || probe==77 || probe==78 || probe==79 || probe==81 || probe==83 || probe==84 || probe==87 || probe==88 || probe==90 || probe==93) ?
        waffle_gen7_boot_prepare(&io,&live->state,(uint32_t *)power->memory,power->size/4,
            sqe_va,aqe_va,restore_va,(probe==80 || probe==82 || probe==85 || probe==86 || probe==89 || probe==91 || probe==94)?42:34) :
        waffle_gen7_boot_start(&io,&live->state,(uint32_t *)power->memory,power->size/4,
            sqe_va,aqe_va,restore_va,(probe==80 || probe==82 || probe==85 || probe==86 || probe==89 || probe==91 || probe==94)?42:34);
    if ((probe==34 || probe==37 || probe==39 || probe==41 || probe==43 || probe==48 || probe==50 || probe==52 || probe==54 || probe==56 || probe==58 || probe==60 || probe==62 || probe==63 || probe==65 || probe==67 || probe==69 || probe==72 || probe==74 || probe==75 || probe==77 || probe==78 || probe==79 || probe==81 || probe==83 || probe==84 || probe==87 || probe==88 || probe==90 || probe==93) && !result) {
        /* Conservative ownership transition ONLY: no packet publication.
         * Exercise native collapse with config/HWCG/bases left active, exactly
         * like the RAW path, to isolate pre-CP setup and post-CP lifetime. */
        if (probe==78) {
            say("waffle-gmu: STATE78 TRUST=%08x RB_BASE=%08x/%08x RB_CNTL=%08x RPTR_ADDR=%08x/%08x RPTR=%08x WPTR=%08x SQE_CNTL=%08x\n",
                rd(gpu,0xf400*4),rd(gpu,0x800*4),rd(gpu,0x801*4),rd(gpu,0x802*4),
                rd(gpu,0x804*4),rd(gpu,0x805*4),rd(gpu,0x806*4),rd(gpu,0x807*4),rd(gpu,0x808*4));
        }
        if (probe==77) {
            say("waffle-gmu: TIMER77 before hold remaining_us=%llu\n",loader_return_remaining_us());
            gen7_clock_delay(&live->context,10000000);
            say("waffle-gmu: TIMER77 after hold remaining_us=%llu; no RAW sent\n",loader_return_remaining_us());
        }
        if (probe==74 || probe==79 || probe==81 || probe==83 || probe==84 || probe==87 || probe==88 || probe==90 || probe==93) {
            unsigned budget=16;
            const uint32_t query[]={((probe>=79?42u:40u)<<20)|(3u<<8)|12u,122,0};
            if(rd(gpu,0x808*4) || !gen7_live_prepare(&live->context))
                stop_unsafe("post-prepare query preflight failed");
            hfi_raw_diagnostic(gmu,hfi_alias,&budget);
            if(!hfi_exchange_watch(gmu,hfi_alias,query,3,"POST_PREPARE_QUERY",false,plan))
                stop_unsafe("post-prepare HFI query failed");
            say("waffle-gmu: QUERY%u post-prepare query passed; no RAW sent\n",probe);
        }
        if (probe==67) {
            uint32_t packet[11];
            if (rd(gpu,0x808*4)) stop_unsafe("CP unexpectedly live in RAW staging control");
            if (!gen7_live_prepare(&live->context) ||
                waffle_hfi_cp_init_packet(packet,11,34,restore_va)!=11 ||
                !hfi_raw_stage_control(gmu,hfi_alias,packet,11,plan))
                say("waffle-gmu: RAW_STAGE67 refused; RAW not sent\n");
        }
        if(probe==93 && !gen7_measure_clocks(probe))stop_unsafe("clock measurement incomplete; no RAW sent");
        if (probe==62) {
            /* Gen7 GBIF SCACHE register DWORD indices from pinned gen7_reg.h.
             * Read while GX/OOB is owned, before collapse; no LLCC programming. */
            say("waffle-gmu: LLCC62 GPU GBIF_SCACHE_CNTL0=%08x GBIF_SCACHE_CNTL1=%08x; RAW not sent\n",
                rd(gpu,0x3c01*4),rd(gpu,0x3c02*4));
        }
        if (probe==60 && !gen7_restore_snapshot(power,probe))
            say("waffle-gmu: RESTORE_SNAPSHOT refused; RAW not sent\n");
        if (probe==58) {
            if (!gen7_ramlog_manifest(plan,probe)) say("waffle-gmu: RAM_LOG_MANIFEST refused\n");
            say("waffle-gmu: RAMLOG_HOLD begin 5s; RAW not sent\n");
            gen7_clock_delay(&live->context,5000000);
            say("waffle-gmu: RAMLOG_HOLD end; RAW not sent\n");
        }
        if (probe==52) {
            say("waffle-gmu: LIVE_LOG_HOLD begin 5s; RAW not sent\n");
            gen7_clock_delay(&live->context,5000000);
            say("waffle-gmu: LIVE_LOG_HOLD end; RAW not sent\n");
        }
        if (!waffle_gen7_config_submitting(&live->state.config)) stop_unsafe("preparation hold failed");
        say("waffle-gmu: Gen7 live preparation passed HWCG=%x; hold until collapse, RAW not sent\n",live->state.clock_status);
    }
    if (probe==35 || probe==36 || probe==80 || probe==82 || probe==85) say("waffle-gmu: Gen7 thread-only result=%d detail=%d ACK=%u busy=%x polls=%u; ME_INIT not sent\n",
        result,live->state.detail,live->state.cp.acknowledged,live->state.cp.last_busy,live->state.cp.polls);
    say("waffle-gmu: Gen7 polled CP start result=%d detail=%d phase=%u index=%x HWCG=%x ACK=%u busy=%x polls=%u; no ZAP or draw\n",
        result,live->state.detail,live->state.config.phase,live->state.failed_index,
        live->state.clock_status,live->state.cp.acknowledged,live->state.cp.last_busy,live->state.cp.polls);
    if (live->state.config.phase==WAFFLE_GEN7_RETAINED)
        stop_unsafe("CP start found unsafe register state");
    if (live->state.config.phase!=WAFFLE_GEN7_SUBMITTED &&
        waffle_gen7_boot_finish(&registers,&live->state))
        stop_unsafe("pre-submission boot rollback failed");
    if(!result && probe==94 && zap_requested())
        return gen7_zap_transition(gpu,gmu,hfi_alias,plan);
    return result==0;
}
static void gpu_gen7_live_finish(struct gen7_live_probe *live,unsigned evidence)
{
    if (!live || live->state.config.phase==WAFFLE_GEN7_EMPTY ||
        live->state.config.phase==WAFFLE_GEN7_RELEASED) return;
    if (!waffle_gen7_config_stopped(&live->state.config,evidence))
        stop_unsafe("CP stop evidence incomplete");
    const struct waffle_gen7_io io={&live->context,gen7_config_read,gen7_config_write,gen7_config_mismatch,NULL};
    if (waffle_gen7_boot_finish(&io,&live->state)) stop_unsafe("CP AO restoration failed after collapse");
    say("waffle-gmu: Gen7 CP lifecycle released after full collapse; no gated GX access\n");
}

/* Owned submission session: no borrowed callee stack, and no user queue yet.
 * Outer diagnostic retains plan/tables/power until close and verified stop. */
static bool present_gpu_pixels(const volatile uint32_t *pixels)
{
    /* The image3 loader gate verified BGRA GOP; do not guess geometry or PA. */
    uintptr_t base=vinfo.v_baseaddr;
    if(!waffle_present_valid(base,vinfo.v_physaddr,vinfo.v_width,vinfo.v_height,vinfo.v_depth,vinfo.v_rowbytes)) {
        say("waffle-gmu: PRESENT refused base=%llx physical=%llx width=%u height=%u depth=%u stride=%u\n",
            (uint64_t)base,vinfo.v_physaddr,vinfo.v_width,vinfo.v_height,vinfo.v_depth,vinfo.v_rowbytes);
        return false;
    }
    vm_offset_t backup=0;
    if(kmem_alloc(kernel_map,&backup,WAFFLE_PRESENT_BYTES,KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) {
        say("waffle-gmu: PRESENT backup allocation failed\n");return false;
    }
    say("waffle-gmu: PRESENT begin format=BGRA8 x=592 y=1456 width=256 height=256 cpu_blit=1\n");
    volatile uint32_t *fb=(volatile uint32_t *)base;
    waffle_present_transfer(fb,vinfo.v_rowbytes,pixels,(uint32_t *)backup,0);
    __asm__ volatile("dsb sy":::"memory");
    unsigned wrong=waffle_present_transfer(fb,vinfo.v_rowbytes,pixels,(uint32_t *)backup,1);
    say("waffle-gmu: PRESENT write checked=65536 wrong=%u\n",wrong);
    if(!wrong)delay_for_interval(5000000,NSEC_PER_USEC);
    waffle_present_transfer(fb,vinfo.v_rowbytes,pixels,(uint32_t *)backup,2);
    __asm__ volatile("dsb sy":::"memory");
    unsigned restored=waffle_present_transfer(fb,vinfo.v_rowbytes,pixels,(uint32_t *)backup,3);
    say("waffle-gmu: PRESENT restore checked=65536 wrong=%u\n",restored);
    kmem_free(kernel_map,backup,WAFFLE_PRESENT_BYTES);
    return !wrong && !restored;
}
enum submit_phase { SUBMIT_READY=1,SUBMIT_BUSY,SUBMIT_POISONED,SUBMIT_CLOSED };
struct waffle_submit_session {
    enum submit_phase phase;
    vm_offset_t gpu,gmu,hfi,alias,allocation,data_alias;
    struct waffle_gmu_plan *plan;
    uint64_t result_va,ib_va,data_va;
    unsigned next_sequence,submitted,completed;
    bool owns_oob;
};
static bool submit_session_open(vm_offset_t gpu,vm_offset_t gmu,vm_offset_t hfi,
    struct waffle_gmu_plan *plan)
{
    if(!plan || plan->submit_session || PAGE_SIZE!=16384 || !ib_requested() ||
        rd(gpu,0xf400*4) || (rd(gmu,WAFFLE_GMU_REG(0x1f8d0))&3) ||
        loader_return_remaining_us()<10000000)return false;
    struct waffle_gmu_region *r=region_at(plan,WAFFLE_GPU_WRITEBACK_ADDRESS,16384);
    if(!r || !r->gpu_only || r->readonly || r->size!=16384)return false;
    uint64_t pa=kvtophys(r->memory);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(r->memory+16383)!=pa+16383)return false;
    vm_offset_t allocation=0;
    if(kmem_alloc(kernel_map,&allocation,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
        VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
    for(vm_offset_t a=r->memory;a<r->memory+16384;a+=64)
        __asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    vm_offset_t alias=ml_io_map_unmappable(pa,16384,VM_WIMG_WCOMB);
    if(!alias){kmem_free(kernel_map,allocation,PAGE_SIZE);return false;}
    struct waffle_submit_session *s=(struct waffle_submit_session *)allocation;
    *s=(struct waffle_submit_session){.phase=SUBMIT_READY,.gpu=gpu,.gmu=gmu,.hfi=hfi,
        .alias=alias,.allocation=allocation,.plan=plan,.next_sequence=44,.owns_oob=true,
        .result_va=waffle_gpu_plan_alias(plan,r->address)+256,
        .ib_va=waffle_gpu_plan_alias(plan,r->address)+1024};
    plan->submit_session=s;
    say("waffle-gmu: SESSION opened heap=1 OOB=1 BO_alias=1 next_sequence=44\n");
    return true;
}
static bool submit_session_exchange(struct waffle_submit_session *s,unsigned words,const char *name)
{
    if(!s || s->phase!=SUBMIT_READY || !s->owns_oob || s->submitted!=s->completed ||
        s->next_sequence>=4095 || loader_return_remaining_us()<3000000)return false;
    uint32_t ib[5];
    if(waffle_writeback_ib_packet(ib,5,s->next_sequence,s->ib_va,words)!=5)return false;
    s->phase=SUBMIT_BUSY;++s->submitted;++s->next_sequence;
    struct waffle_gmu_plan watch=*s->plan;
    watch.raw_stage_pause=false;
    if(!hfi_exchange_watch(s->gmu,s->hfi,ib,5,name,true,&watch) ||
        !wait_for(s->gmu,WAFFLE_GMU_REG(0x23b0c),1u<<23,0,2000)) {
        s->phase=SUBMIT_POISONED;return false;
    }
    return true;
}
static bool submit_session_submit(struct waffle_submit_session *s)
{
    if(!s || s->phase!=SUBMIT_READY || !s->owns_oob || s->submitted!=s->completed ||
        s->next_sequence>=4095 || loader_return_remaining_us()<3000000)return false;
    if(rd(s->gpu,0xf400*4) || (rd(s->gmu,WAFFLE_GMU_REG(0x1f8d0))&3)) {
        s->phase=SUBMIT_POISONED;return false;
    }
    const unsigned fence=s->submitted+1,sequence=s->next_sequence;
    uint32_t direct[9],token[4];
    if(waffle_writeback_packet(direct,9,sequence,s->result_va)!=9)return false;
    for(unsigned i=0;i<4;++i)direct[4+i]=token[i]=waffle_writeback_values[i]^(fence*0x01010101u);
    volatile uint32_t *out=(volatile uint32_t *)s->alias;
    for(unsigned i=0;i<4096;++i)out[i]=i>=256 && i<264 ? direct[i-255] : waffle_writeback_initial(i);
    __asm__ volatile("dsb sy":::"memory");
    for(unsigned i=0;i<4096;++i)if(out[i]!=(i>=256 && i<264 ? direct[i-255] : waffle_writeback_initial(i)))return false;
    if(!submit_session_exchange(s,8,"SESSION_IB"))return false;
    for(unsigned attempt=0;attempt<2000;++attempt) {
        __asm__ volatile("dsb sy":::"memory");
        bool seen=true;
        for(unsigned i=0;i<4;++i)if(out[64+i]!=token[i])seen=false;
        if(seen)break;
        delay_for_interval(100,NSEC_PER_USEC);
    }
    unsigned wrong=0;
    for(unsigned i=0;i<4096;++i) {
        uint32_t expected=i>=256 && i<264 ? direct[i-255] :
            i>=64 && i<68 ? token[i-64] : waffle_writeback_initial(i);
        if(out[i]!=expected) {
            if(!wrong)say("waffle-gmu: SESSION mismatch fence=%u index=%u got=%08x expected=%08x\n",fence,i,out[i],expected);
            ++wrong;
        }
    }
    say("waffle-gmu: SESSION fence=%u seq=%u values=%08x/%08x/%08x/%08x wrong_words=%u\n",
        fence,sequence,out[64],out[65],out[66],out[67],wrong);
    if(wrong){s->phase=SUBMIT_POISONED;return false;}
    s->completed=fence;s->phase=SUBMIT_READY;
    return true;
}
static bool submit_session_compute_job(struct waffle_submit_session *s,unsigned mode,unsigned image,struct waffle_gpu_copy_job *job)
{
    if(!s || (mode!=1 && mode!=2) || image>3 || (image==3 && mode!=2) || s->phase!=SUBMIT_READY || !s->owns_oob ||
        (job?(mode!=2 || image!=2 || s->submitted!=s->completed || s->next_sequence!=44+s->submitted || s->submitted>=1024):(s->submitted || s->completed || s->next_sequence!=44)) ||
        s->ib_va!=waffle_gpu_compact_alias(WAFFLE_GPU_DYNAMIC_ADDRESS)+1024 ||
        rd(s->gpu,0xf400*4) || (rd(s->gmu,WAFFLE_GMU_REG(0x1f8d0))&3))return false;
    bool glsl=job && (s->plan->compute_image==8 || s->plan->compute_image==9 || s->plan->compute_image==10 || s->plan->compute_image==11 || s->plan->compute_image==12);
    bool prepare=glsl && s->plan->compute_image==9;
    unsigned command_words=glsl?WAFFLE_GLSL_WORDS:WAFFLE_COMPUTE_WORDS;
    if(glsl && !s->data_alias)return false;
    if(job && job->uploaded && (!glsl || (s->plan->compute_image!=11 && s->plan->compute_image!=12)))return false;
    bool uploaded=job && job->uploaded;
    uint32_t input[256];
    unsigned fence=s->submitted+1,sequence=s->next_sequence;
    if(job){
        job->fence=0;
        if(job->words!=256 || !waffle_job_buffer_valid((uintptr_t)job->input,s->alias) ||
            !waffle_job_buffer_valid((uintptr_t)job->output,s->alias))return false;
        if(s->data_alias && (!waffle_job_buffer_valid((uintptr_t)job->input,s->data_alias) || !waffle_job_buffer_valid((uintptr_t)job->output,s->data_alias)))return false;
        for(unsigned i=0;i<256;i++)input[i]=job->input[i];
    }
    _Static_assert(WAFFLE_IMAGE_WORDS==WAFFLE_COMPUTE_WORDS,"image command layout changed");
    uint32_t (*initial)(unsigned,unsigned)=image>=2?waffle_copy_initial:image?waffle_image_initial:waffle_compute_initial;
    uint32_t (*expected)(unsigned,unsigned)=image>=2?waffle_copy_expected:image?waffle_image_expected:waffle_compute_expected;
    _Static_assert(WAFFLE_COPY_WORDS==WAFFLE_COMPUTE_WORDS,"copy command layout changed");
    unsigned first=image?3072:64,pixels=image?256:8;
    bool separate=job && s->data_alias;
    volatile uint32_t *data=(volatile uint32_t *)s->data_alias;
    if(separate){
        if(!uploaded)for(unsigned i=0;i<4096;i++)data[i]=waffle_data_word(input,i,false);
        __asm__ volatile("dsb sy":::"memory");
        for(unsigned i=0;i<4096;i++)if(data[i]!=waffle_data_word(input,i,false))return false;
    }
    volatile uint32_t *out=(volatile uint32_t *)s->alias;
    if(!uploaded)for(unsigned i=0;i<4096;i++)out[i]=glsl?waffle_glsl_command_word(fence,i,s->data_va,false,prepare):separate?waffle_data_command_word(input,fence,i,s->data_va,false):job?waffle_job_word(input,fence,i,false):initial(mode,i);
    __asm__ volatile("dsb sy":::"memory");
    for(unsigned i=0;i<4096;i++)if(out[i]!=(glsl?waffle_glsl_command_word(fence,i,s->data_va,false,prepare):separate?waffle_data_command_word(input,fence,i,s->data_va,false):job?waffle_job_word(input,fence,i,false):initial(mode,i)))return false;
    if(uploaded)say("waffle-gmu: MSM_COMMAND accepted fence=%u words=191 source=user_bo\n",fence);
    if(glsl)say("waffle-gmu: GLSL_JOB mode=%s command_words=191 bindless=1 source=GLSL450\n",prepare?"prepare":"dispatch");
    if(job)say("waffle-gmu: COPY_JOB begin fence=%u seq=%u pixels=256\n",fence,sequence);
    if(image>=2)say("waffle-gmu: IMAGE_COPY input_word=3328 output_word=3072 pixels=256\n");
    if(image)say("waffle-gmu: IMAGE begin width=16 height=16 pixels=256 dispatch=%u\n",mode==2);
    say("waffle-gmu: COMPUTE begin mode=%u dispatch=%u words=%u output_poison=1\n",prepare?1:mode,mode==2 && !prepare,command_words);
    if(!submit_session_exchange(s,command_words,"COMPUTE_IB"))return false;
    for(unsigned attempt=0;attempt<2000;attempt++) {
        __asm__ volatile("dsb sy":::"memory");
        bool seen=out[2048]==(job?fence:1);
        if(mode==2 && !prepare)for(unsigned i=0;i<pixels;i++)if((separate?data[i]:out[first+i])!=(job?input[i]:expected(mode,first+i)))seen=false;
        if(seen)break;
        delay_for_interval(100,NSEC_PER_USEC);
    }
    unsigned wrong=0;
    for(unsigned i=0;i<4096;i++)if(out[i]!=(glsl?waffle_glsl_command_word(fence,i,s->data_va,true,prepare):separate?waffle_data_command_word(input,fence,i,s->data_va,true):job?waffle_job_word(input,fence,i,true):expected(mode,i))) {
        if(!wrong)say("waffle-gmu: COMPUTE mismatch mode=%u index=%u got=%08x expected=%08x\n",mode,i,out[i],glsl?waffle_glsl_command_word(fence,i,s->data_va,true,prepare):separate?waffle_data_command_word(input,fence,i,s->data_va,true):job?waffle_job_word(input,fence,i,true):expected(mode,i));
        ++wrong;
    }
    say("waffle-gmu: COMPUTE values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x control=%08x checked=4096 wrong_words=%u mode=%u\n",
        out[first],out[first+1],out[first+2],out[first+3],out[first+4],out[first+5],out[first+6],out[first+7],out[2048],wrong,mode);
    if(image && !job)for(unsigned i=0;i<256;i+=8)
        say("waffle-gmu: IMAGE pixels offset=%u values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x\n",i,
            out[first+i],out[first+i+1],out[first+i+2],out[first+i+3],out[first+i+4],out[first+i+5],out[first+i+6],out[first+i+7]);
    if(separate){
        unsigned data_wrong=0;
        for(unsigned i=0;i<4096;i++)if(data[i]!=waffle_data_word(input,i,!prepare)){
            if(!data_wrong)say("waffle-gmu: DATA_BO mismatch fence=%u word=%u got=%08x expected=%08x\n",fence,i,data[i],waffle_data_word(input,i,!prepare));
            ++data_wrong;
        }
        say("waffle-gmu: DATA_BO checked=4096 wrong_words=%u fence=%u independent=1\n",data_wrong,fence);
        wrong+=data_wrong;
    }
    if(wrong){s->phase=SUBMIT_POISONED;return false;}
    s->completed=s->submitted;s->phase=SUBMIT_READY;
    if(job){
        for(unsigned i=0;i<256;i++)job->output[i]=separate?data[i]:out[3072+i];
        job->fence=fence;
        say("waffle-gmu: COPY_JOB done fence=%u seq=%u control=%08x checked=4096 wrong_words=0\n",fence,sequence,out[2048]);
        for(unsigned i=0;i<256;i+=8)say("waffle-gmu: COPY_JOB pixels fence=%u offset=%u values=%08x/%08x/%08x/%08x/%08x/%08x/%08x/%08x\n",fence,i,
            job->output[i],job->output[i+1],job->output[i+2],job->output[i+3],job->output[i+4],job->output[i+5],job->output[i+6],job->output[i+7]);
    }
    return true;
}
static bool submit_session_compute(struct waffle_submit_session *s,unsigned mode,unsigned image)
{
    return submit_session_compute_job(s,mode,image,NULL);
}
static bool submit_session_run(struct waffle_gmu_plan *plan)
{
    struct waffle_submit_session *s=plan->submit_session;
    if(plan->compute_mode) {
        if(!submit_session_compute(s,plan->compute_mode,plan->compute_image))return false;
    } else for(unsigned i=0;i<3;++i) {
        if(!submit_session_submit(s))return false;
        if(i<2)delay_for_interval(1000000,NSEC_PER_USEC);
    }
    plan->session_slumber_sequence=s->next_sequence;
    if(plan->compute_image==3 && !present_gpu_pixels((volatile uint32_t *)s->alias+3072))return false;
    say("waffle-gmu: SESSION result=1 submitted=%u completed=%u next_sequence=%u OOB=1; bounded kernel session\n",
        s->submitted,s->completed,s->next_sequence);
    return true;
}
static bool submit_session_close(struct waffle_gmu_plan *plan)
{
    struct waffle_submit_session *s=plan->submit_session;
    if(!s || s->phase!=SUBMIT_READY || !s->owns_oob || s->submitted!=s->completed)return false;
    if(!wait_for(s->gmu,WAFFLE_GMU_REG(0x23b0c),1u<<23,0,2000)) {
        s->phase=SUBMIT_POISONED;return false;
    }
    /* Use the consumed sequence on every exit, even a safe preflight refusal. */
    plan->session_slumber_sequence=s->next_sequence;
    wr(s->gmu,WAFFLE_GMU_REG(0x1f994),1u<<31);
    s->owns_oob=false;s->phase=SUBMIT_CLOSED;
    say("waffle-gmu: SESSION closed OOB_released=1 outstanding=0\n");
    return true;
}
static void submit_session_destroy(struct waffle_gmu_plan *plan,unsigned evidence)
{
    struct waffle_submit_session *s=plan->submit_session;
    const unsigned complete=WAFFLE_GEN7_STOP_SLUMBER|WAFFLE_GEN7_STOP_CM3_RESET|
        WAFFLE_GEN7_STOP_RSC_ASLEEP|WAFFLE_GEN7_STOP_GX_OFF|
        WAFFLE_GEN7_STOP_GBIF_DRAINED|WAFFLE_GEN7_STOP_QTB_DRAINED;
    if(!s || s->phase!=SUBMIT_CLOSED || s->owns_oob || s->submitted!=s->completed ||
        (evidence&complete)!=complete)stop_unsafe("session destroy requires full native stop evidence");
    vm_offset_t allocation=s->allocation;
    if(s->data_alias)ml_io_unmap(s->data_alias,16384);
    ml_io_unmap(s->alias,16384);
    plan->submit_session=NULL;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    say("waffle-gmu: SESSION destroyed after full stop; aliases and heap released\n");
}

/* Bounded post-bootstrap BO binding. Parent owns mappings and backing pages
 * until full stop. Never replace an alias after a command has been published. */
bool waffle_gmu_owner_memory_idle(struct waffle_gmu_owner *owner)
{
    struct waffle_submit_session *s=owner && owner->plan?owner->plan->submit_session:NULL;
    return s && s->phase==SUBMIT_READY && s->owns_oob && s->submitted==s->completed &&
        s->next_sequence==44+s->submitted && !rd(s->gpu,0xf400*4) &&
        !(rd(s->gmu,WAFFLE_GMU_REG(0x1f8d0))&3);
}
bool waffle_gmu_owner_can_bind_bo(struct waffle_gmu_owner *owner)
{
    struct waffle_submit_session *s=owner && owner->plan?owner->plan->submit_session:NULL;
    return s && s->phase==SUBMIT_READY && s->owns_oob && !s->submitted && !s->completed &&
        s->next_sequence==44 && !rd(s->gpu,0xf400*4) &&
        !(rd(s->gmu,WAFFLE_GMU_REG(0x1f8d0))&3);
}
bool waffle_gmu_owner_bind_bo(struct waffle_gmu_owner *owner,struct waffle_gmu_region *r)
{
    if(!waffle_gmu_owner_can_bind_bo(owner) || !r || r->address!=WAFFLE_GPU_DYNAMIC_ADDRESS ||
        !r->memory || !r->gpu_only || r->readonly || r->size!=16384)return false;
    uint64_t pa=kvtophys(r->memory);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(r->memory+16383)!=pa+16383)return false;
    struct waffle_submit_session *s=owner->plan->submit_session;
    uint64_t va=waffle_gpu_plan_alias(owner->plan,r->address);
    if(!va || !waffle_gpu_va_valid(va+16383))return false;
    for(vm_offset_t a=r->memory;a<r->memory+16384;a+=64)
        __asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    vm_offset_t alias=ml_io_map_unmappable(pa,16384,VM_WIMG_WCOMB);
    if(!alias)return false;
    vm_offset_t old_alias=s->alias;
    s->alias=alias;s->result_va=va+256;s->ib_va=va+1024;
    ml_io_unmap(old_alias,16384);
    say("waffle-gmu: SESSION rebound BO VA=%llx PA=%llx idle=1 outstanding=0\n",va,pa);
    return true;
}

bool waffle_gmu_owner_bind_data_bo(struct waffle_gmu_owner *owner,struct waffle_gmu_region *r)
{
    if(!waffle_gmu_owner_can_bind_bo(owner) || !r || r->address!=WAFFLE_GPU_DATA_ADDRESS ||
        !r->memory || !r->gpu_only || r->readonly || r->size!=16384)return false;
    struct waffle_submit_session *s=owner->plan->submit_session;
    if(s->data_alias || s->ib_va!=waffle_gpu_compact_alias(WAFFLE_GPU_DYNAMIC_ADDRESS)+1024)return false;
    uint64_t pa=kvtophys(r->memory),va=waffle_gpu_plan_alias(owner->plan,r->address);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(r->memory+16383)!=pa+16383 || !va ||
        !waffle_gpu_va_valid(va+16383) || va==s->ib_va-1024)return false;
    for(vm_offset_t a=r->memory;a<r->memory+16384;a+=64)__asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    vm_offset_t alias=ml_io_map_unmappable(pa,16384,VM_WIMG_WCOMB);
    if(!alias)return false;
    if(alias==s->alias){ml_io_unmap(alias,16384);return false;}
    s->data_alias=alias;s->data_va=va;
    say("waffle-gmu: DATA_BO bound VA=%llx PA=%llx separate_alias=1\n",va,pa);
    return true;
}

bool waffle_gmu_owner_bind_user_buffer(struct waffle_gmu_owner *owner,const struct waffle_gpu_buffer *bo)
{
    if(!waffle_gmu_owner_can_bind_bo(owner) || !bo || bo->readonly || !bo->memory ||
        !waffle_gpu_user_buffer_valid(bo->gpu_va,bo->bytes))return false;
    struct waffle_submit_session *s=owner->plan->submit_session;
    if(s->data_alias || s->ib_va!=waffle_gpu_compact_alias(WAFFLE_GPU_DYNAMIC_ADDRESS)+1024)return false;
    uint64_t pa=kvtophys(bo->memory);
    if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(bo->memory+16383)!=pa+16383)return false;
    for(vm_offset_t a=bo->memory;a<bo->memory+16384;a+=64)__asm__ volatile("dc civac, %0"::"r"(a):"memory");
    __asm__ volatile("dsb sy":::"memory");
    vm_offset_t alias=ml_io_map_unmappable(pa,16384,VM_WIMG_WCOMB);
    if(!alias)return false;
    if(alias==s->alias){ml_io_unmap(alias,16384);return false;}
    s->data_alias=alias;s->data_va=bo->gpu_va;
    say("waffle-gmu: USER_BO bound VA=%llx PA=%llx separate_alias=1\n",bo->gpu_va,pa);
    return true;
}

bool waffle_gmu_owner_buffers(struct waffle_gmu_owner *owner,struct waffle_gpu_buffer buffers[2])
{
    struct waffle_submit_session *s=owner && owner->plan?owner->plan->submit_session:NULL;
    if(!s || !buffers || (owner->plan->compute_image!=11 && owner->plan->compute_image!=12) || s->phase!=SUBMIT_READY ||
       s->submitted || !s->alias || !s->data_alias || s->data_va!=WAFFLE_GPU_USER_TEST_VA)return false;
    buffers[0]=(struct waffle_gpu_buffer){.gpu_va=s->ib_va-1024,.memory=s->alias,.bytes=16384};
    buffers[1]=(struct waffle_gpu_buffer){.gpu_va=s->data_va,.memory=s->data_alias,.bytes=16384};
    return true;
}
/* General root command submission, still gated off until its client backend
 * is complete. Caller owns BO registry, stable command storage and serialization. */
bool waffle_gmu_owner_submit(struct waffle_gmu_owner *owner,struct waffle_gpu_submit_job *job)
{
    if(job)job->fence=0;
    if(!owner || !owner->plan || owner->plan->compute_image!=13 || !job || !job->commands ||
       !job->count || job->count>WAFFLE_GPU_SUBMIT_COMMANDS || !waffle_gmu_owner_memory_idle(owner))return false;
    struct waffle_submit_session *s=owner->plan->submit_session;
    if(s->submitted>=1024 || s->ib_va!=waffle_gpu_compact_alias(WAFFLE_GPU_DYNAMIC_ADDRESS)+1024)return false;
    uint32_t commands[WAFFLE_GPU_SUBMIT_WORDS];unsigned words=0;
    for(unsigned c=0;c<job->count;c++){
        const struct waffle_gpu_command *command=&job->commands[c];
        if(!waffle_gpu_command_valid(command) || command->bytes/4>WAFFLE_GPU_SUBMIT_WORDS-words)return false;
        const volatile uint32_t *source=(const volatile uint32_t *)(command->buffer->memory+command->offset);
        for(unsigned i=0;i<command->bytes/4;i++)commands[words++]=source[i];
    }
    unsigned fence=s->submitted+1,sequence=s->next_sequence;
    uint64_t result_va=s->ib_va-1024+8192;
    volatile uint32_t *out=(volatile uint32_t *)s->alias;
    for(unsigned i=0;i<4096;i++)out[i]=waffle_gpu_submit_initial(i,words,commands,fence,result_va,false);
    __asm__ volatile("dsb sy":::"memory");
    for(unsigned i=0;i<4096;i++)if(out[i]!=waffle_gpu_submit_initial(i,words,commands,fence,result_va,false))return false;
    say("waffle-gmu: GENERAL_SUBMIT begin fence=%u seq=%u root_words=%u kernel_tail=15 extra_IB_depth=0\n",fence,sequence,words);
    if(!submit_session_exchange(s,words+WAFFLE_GPU_SUBMIT_TAIL_WORDS,"GENERAL_IB")){owner->exercise_ok=false;return false;}
    for(unsigned attempt=0;attempt<2000;attempt++){
        __asm__ volatile("dsb sy":::"memory");
        if(out[2048]==fence)break;
        delay_for_interval(100,NSEC_PER_USEC);
    }
    unsigned wrong=0;
    for(unsigned i=0;i<4096;i++)if(out[i]!=waffle_gpu_submit_initial(i,words,commands,fence,result_va,true)){
        if(!wrong)say("waffle-gmu: GENERAL_SUBMIT mismatch index=%u got=%08x expected=%08x\n",i,out[i],waffle_gpu_submit_initial(i,words,commands,fence,result_va,true));
        wrong++;
    }
    if(wrong){s->phase=SUBMIT_POISONED;owner->exercise_ok=false;return false;}
    s->completed=s->submitted;s->phase=SUBMIT_READY;job->fence=fence;
    say("waffle-gmu: GENERAL_SUBMIT done fence=%u seq=%u control=%08x checked=4096 wrong_words=0\n",fence,sequence,out[2048]);
    return true;
}

/* The parent owns power, SMMU, BO and serialization; no user pointer is accepted. */
bool waffle_gmu_owner_copy(struct waffle_gmu_owner *owner,struct waffle_gpu_copy_job *job)
{
    if(job)job->fence=0;
    if(!owner || !owner->plan || !job)return false;
    bool ok=submit_session_compute_job(owner->plan->submit_session,2,2,job);
    if(!ok && owner->plan->submit_session && owner->plan->submit_session->phase==SUBMIT_POISONED)owner->exercise_ok=false;
    return ok;
}
static bool owner_copy_sequence(struct waffle_gmu_owner *owner)
{
    uint32_t input[256],output[256];
    say("waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1\n");
    for(unsigned fence=1;fence<=3;fence++){
        for(unsigned i=0;i<256;i++){input[i]=waffle_job_test_pixel(fence,i);output[i]=0xbad00000u+i;}
        struct waffle_gpu_copy_job job={.input=input,.output=output,.words=256};
        if(!waffle_gmu_owner_copy(owner,&job) || job.fence!=fence)return false;
        unsigned wrong=0;for(unsigned i=0;i<256;i++)if(output[i]!=input[i])++wrong;
        say("waffle-gmu: COPY_CALLER fence=%u checked=256 wrong=%u\n",job.fence,wrong);
        if(wrong)return false;
    }
    struct waffle_submit_session *s=owner->plan->submit_session;
    owner->plan->session_slumber_sequence=s->next_sequence;
    say("waffle-gmu: SESSION result=1 submitted=%u completed=%u next_sequence=%u OOB=1; bounded kernel session\n",s->submitted,s->completed,s->next_sequence);
    return s->submitted==3 && s->completed==3 && s->next_sequence==47;
}

static bool owner_glsl_prepare(struct waffle_gmu_owner *owner)
{
    uint32_t input[256],output[256];
    for(unsigned i=0;i<256;i++)input[i]=waffle_job_test_pixel(1,i);
    struct waffle_gpu_copy_job job={input,output,256,0,false};
    if(!waffle_gmu_owner_copy(owner,&job) || job.fence!=1)return false;
    unsigned wrong=0;for(unsigned i=0;i<256;i++)if(output[i]!=0xdead0000u+i)++wrong;
    say("waffle-gmu: GLSL_PREPARE output_poison=256 wrong=%u dispatch=0\n",wrong);
    struct waffle_submit_session *s=owner->plan->submit_session;
    owner->plan->session_slumber_sequence=s->next_sequence;
    say("waffle-gmu: SESSION result=1 submitted=%u completed=%u next_sequence=%u OOB=1; bounded kernel session\n",s->submitted,s->completed,s->next_sequence);
    return !wrong;
}
