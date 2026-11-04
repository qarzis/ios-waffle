/* Adreno750 QTB500 translation test, using the PJD110 vendor driver's ECATS
 * protocol (arm-smmu-qcom.c). GMU stays in reset and GX stays powered off.
 * Only an unused context/stream entry is borrowed, then restored.
 */
#include <kern/clock.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <mach/vm_param.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <sys/waffle_gpu.h>
#include <sys/waffle_gmu.h>
#include <sys/waffle_gpu_data.h>
#include <sys/waffle_smmu.h>
#include <sys/waffle_gpu_registry.h>
#include <sys/waffle_gpu_reclaim.h>
#include <sys/waffle_scm.h>
#include <sys/waffle_gpu_writeback.h>
#include <vm/vm_kern.h>
extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern uint64_t kvtophys(vm_offset_t);
extern void loader_log_putc(char);
extern void loader_return(void);
void waffle_smmu_probe(vm_offset_t, uint32_t, uint32_t, uint32_t, uint32_t, unsigned);
#define FSR_FAULT_MASK 0xc00001feu

static void log_line(const char *fmt, ...) __printflike(1, 2);
static void log_line(const char *fmt, ...)
{
    char text[256]; va_list ap;
    va_start(ap, fmt); vsnprintf(text, sizeof(text), fmt, ap); va_end(ap);
    for (char *p = text; *p; ++p) loader_log_putc(*p);
    printf("%s", text);
}
static uint32_t r32(vm_offset_t p, uint32_t o) { return *(volatile uint32_t *)(p + o); }
static uint64_t r64(vm_offset_t p, uint32_t o) { return *(volatile uint64_t *)(p + o); }
static void barrier(void) { __asm__ volatile("dsb sy" ::: "memory"); }
static void w32(vm_offset_t p, uint32_t o, uint32_t v) { *(volatile uint32_t *)(p + o) = v; barrier(); }
static void w64(vm_offset_t p, uint32_t o, uint64_t v) { *(volatile uint64_t *)(p + o) = v; barrier(); }
static bool poll(vm_offset_t base, uint32_t off, uint32_t mask, uint32_t value, unsigned us)
{
    for (unsigned i = 0; i < us; ++i) {
        if ((r32(base, off) & mask) == value) return true;
        delay_for_interval(1, NSEC_PER_USEC);
    }
    return false;
}
static void clean(vm_offset_t p)
{
    for (vm_offset_t a = p; a < p + 4096; a += 64)
        __asm__ volatile("dc cvac, %0" :: "r"(a) : "memory");
    barrier();
}
static bool tlb_sync(vm_offset_t cb)
{
    w32(cb, 0x610, (uint32_t)(r64(cb,0x20)>>48)); /* TLBIASID: current TTBR0 ASID */
    w32(cb, 0x7f0, 0); /* TLBSYNC */
    return poll(cb, 0x7f4, 1, 0, 10000);
}
#define TABLE_LIMIT 160
#define PTE_ADDRESS 0x0000fffffffff000ULL
struct table_pool {
    unsigned count;
    vm_offset_t memory[TABLE_LIMIT];
    uint64_t phys[TABLE_LIMIT];
};
static uint64_t *new_table(struct table_pool *pool)
{
    if (pool->count == TABLE_LIMIT) return NULL;
    unsigned i = pool->count;
    if (kmem_alloc(kernel_map, &pool->memory[i], PAGE_SIZE, KMA_KOBJECT | KMA_ZERO | KMA_DATA,
            VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) return NULL;
    ++pool->count;
    pool->phys[i] = kvtophys(pool->memory[i]);
    if ((pool->phys[i] & 4095) || pool->phys[i] >= (1ULL << 36)) return NULL;
    return (uint64_t *)pool->memory[i];
}
static uint64_t *next_table(struct table_pool *pool, uint64_t *entry)
{
    if (*entry & 1) {
        for (unsigned i = 0; i < pool->count; ++i)
            if (pool->phys[i] == (*entry & PTE_ADDRESS)) return (uint64_t *)pool->memory[i];
        return NULL;
    }
    uint64_t *table = new_table(pool);
    if (table) *entry = pool->phys[pool->count - 1] | 3;
    return table;
}
static bool map_page_access(struct table_pool *pool, uint64_t iova, uint64_t pa, bool readonly,bool unprivileged)
{
    if (!pool->count || iova >> 39 || (iova & 4095) || pa >= (1ULL << 36) || (pa & 4095)) return false;
    uint64_t *root = (uint64_t *)pool->memory[0];
    uint64_t *second = next_table(pool, &root[(iova >> 30) & 511]);
    uint64_t *leaf = second ? next_table(pool, &second[(iova >> 21) & 511]) : NULL;
    if (!leaf) return false;
    uint64_t *entry = &leaf[(iova >> 12) & 511];
    if ((*entry & 1) && (*entry & PTE_ADDRESS) != pa) return false;
    *entry = pa | 3 | (2ULL << 8) | (1ULL << 10) | (1ULL << 11) | (readonly ? 1ULL<<7 : 0) | (unprivileged ? 1ULL<<6 : 0);
    return true;
}
static bool map_page(struct table_pool *pool,uint64_t iova,uint64_t pa,bool readonly)
{
    return map_page_access(pool,iova,pa,readonly,false);
}
/* Change only the high GPU alias, before replying to the allocation request.
 * GMU's low alias retains its independent read/write permissions. */
struct pool_permission_context {struct table_pool *tables;vm_offset_t cb,lpac_cb;};
static uint64_t *permission_table(struct table_pool *pool,uint64_t entry)
{
    if((entry&3)!=3) return NULL;
    for(unsigned i=0;i<pool->count;i++) if(pool->phys[i]==(entry&PTE_ADDRESS)) return (uint64_t *)pool->memory[i];
    return NULL;
}
static bool pool_permission_sync(struct pool_permission_context *c)
{
    bool user_ok=tlb_sync(c->cb);
    bool lpac_ok=!c->lpac_cb || tlb_sync(c->lpac_cb);
    return user_ok && lpac_ok;
}
static bool pool_permissions(void *opaque,uint64_t va,uint32_t size,uint32_t flags)
{
    struct pool_permission_context *c=opaque;
    if (!c || !c->tables || !c->tables->count || !c->tables->memory[0] || !c->cb || !size || (va&4095) ||
        va<waffle_gpu_compact_alias(WAFFLE_HWSCHED_POOL_ADDRESS) ||
        va+size<va || va+size>waffle_gpu_compact_alias(WAFFLE_HWSCHED_POOL_ADDRESS)+0xf00000 ||
        !(flags&1) || (flags&(1u<<12))) return false;
    uint64_t offset=va-WAFFLE_GPU_GLOBAL_BASE;
    for(uint32_t off=0;off<size;off+=4096) {
        uint64_t iova=offset+off;
        uint64_t *root=(uint64_t *)c->tables->memory[0];
        uint64_t *second=permission_table(c->tables,root[(iova>>30)&511]);
        uint64_t *leaf=second?permission_table(c->tables,second[(iova>>21)&511]):NULL;
        if (!leaf) return false;
        uint64_t *entry=&leaf[(iova>>12)&511],old=*entry;
        if ((old&3)!=3) return false;
        uint64_t value=(old&~(3ULL<<6))|((flags&4)?0:1ULL<<7)|((flags&2)?0:1ULL<<6);
        if(value==old) continue;
        *entry=0;clean((vm_offset_t)entry&~4095ULL);
        if(!pool_permission_sync(c)) return false;
        *entry=value;clean((vm_offset_t)entry&~4095ULL);
        if(!pool_permission_sync(c)) return false;
    }
    log_line("waffle-iommu: allocation GPU permissions VA=%llx size=%u flags=%x applied\n",va,size,flags);
    return true;
}
enum ecats_access { ECATS_PRIV=1, ECATS_INST=2, ECATS_WRITE=4 };
static bool translate_page_access(vm_offset_t qtb, vm_offset_t cb, uint64_t iova,
    uint64_t expected, unsigned sid,unsigned access,unsigned attempts)
{
    if(sid>1023 || (access&~7u) || !attempts || attempts>3) return false;
    for (unsigned attempt = 0; attempt < attempts; ++attempt) {
        w64(qtb, 0x430, sid);
        /* Pinned qtb500_trigger_atos: nonsecure translation, no data transfer. */
        uint64_t input=(4u<<8)|8;
        if(access&ECATS_PRIV) input|=1u<<13;
        if(access&ECATS_INST) input|=1u<<12;
        if(access&ECATS_WRITE) input|=1;
        w64(qtb, 0x438, input);
        w64(qtb, 0x440, iova);
        w64(qtb, 0x448, 1);
        bool finished = false;
        for (unsigned us = 0; us < 1000; ++us) {
            if ((r64(qtb, 0x450) & 1) || (r64(qtb, 0x458) & 1)) { finished = true; break; }
            delay_for_interval(1, NSEC_PER_USEC);
        }
        uint64_t output = r64(qtb, 0x458);
        uint32_t fsr_raw = r32(cb, 0x58), fsr = fsr_raw & FSR_FAULT_MASK;
        log_line("waffle-iommu: ECATS SID=%u VA=%llx expected=%llx PA=%llx done=%u FSRraw=%08x faults=%08x access=%x\n",
            sid, iova, expected, output >> 12, finished, fsr_raw, fsr,access);
        if(attempts==1 && (!finished || (output&1) || fsr || (output>>12)!=expected))
            log_line("waffle-iommu: ACCESS_MATRIX failure VA=%llx access=%x OUT=%llx FSR=%08x FAR=%llx\n",
                iova,access,output,fsr_raw,r64(cb,0x60));
        w64(qtb, 0x448, 0);
        if (fsr) {
            log_line("waffle-iommu: fault FAR=%llx\n", r64(cb, 0x60));
            w32(cb, 0x58, fsr);
            if (fsr & (1u << 30)) w32(cb, 8, 1);
        }
        if (finished && !(output & 1) && !fsr && (output >> 12) == expected) return true;
    }
    return false;
}
static bool translate_page(vm_offset_t qtb,vm_offset_t cb,uint64_t iova,uint64_t expected,unsigned sid)
{
    return translate_page_access(qtb,cb,iova,expected,sid,ECATS_PRIV,3);
}
/* Observe real START allocations now; run ECATS only after GMU has stopped. */
struct access_matrix_context {
    struct pool_permission_context permissions;
    unsigned count;
    struct {uint64_t va;uint32_t size,flags;} allocations[32];
};
static bool access_matrix_capture(void *opaque,uint64_t va,uint32_t size,uint32_t flags)
{
    struct access_matrix_context *c=opaque;
    if(c->count==32 || !pool_permissions(&c->permissions,va,size,flags)) return false;
    c->allocations[c->count].va=va;c->allocations[c->count].size=size;
    c->allocations[c->count++].flags=flags;
    return true;
}
static bool access_matrix_buffer(vm_offset_t qtb,vm_offset_t cb,uint64_t va,
    vm_offset_t memory,uint32_t size,unsigned access,bool instruction,unsigned *checks)
{
    if(!size || (va&4095) || (memory&4095)) return false;
    uint32_t last=(size-1)&~4095u;
    for(unsigned edge=0;edge<2;++edge) {
        if(edge && !last) break;
        unsigned offset=edge?last:0;
        for(unsigned n=0;n<3;++n) {
            if((n==1 && !(access&ECATS_WRITE)) || (n==2 && !instruction)) continue;
            unsigned mode=n==0?(access&~ECATS_WRITE):n==1?access:access|ECATS_INST;
            ++*checks;
            if(!translate_page_access(qtb,cb,va+offset,kvtophys(memory+offset),0,mode,1)) return false;
        }
    }
    return true;
}
static bool access_matrix_run(struct access_matrix_context *c,
    struct waffle_gmu_plan *plan,vm_offset_t qtb,vm_offset_t cb,vm_offset_t gmu,vm_offset_t cc)
{
    unsigned checks=0;
    bool ok=c->count && (r32(gmu,WAFFLE_GMU_SYSRESET)&1) &&
        (r32(cc,WAFFLE_GPU_GX_GDSCR)&((1u<<31)|1))==1 &&
        (r64(qtb,0x410)&1) && (r64(qtb,0x418)&1) && !r64(qtb,0x448) &&
        !(r32(cb,0x58)&FSR_FAULT_MASK);
    log_line("waffle-iommu: ACCESS_MATRIX begin ready=%u allocations=%u; CM3 reset/GX off, no RAW\n",ok,c->count);
    struct waffle_gmu_region *arena=NULL;
    unsigned firmware_buffers=0;
    for(unsigned i=0;ok && i<plan->count;++i) {
        struct waffle_gmu_region *r=&plan->regions[i];
        if(r->address==WAFFLE_HWSCHED_POOL_ADDRESS) arena=r;
        if(r->address==WAFFLE_GPU_SQE_ADDRESS || r->address==WAFFLE_GPU_AQE_ADDRESS ||
            r->address==WAFFLE_GPU_PWRUP_ADDRESS) {
            ++firmware_buffers;
            bool code=r->address!=WAFFLE_GPU_PWRUP_ADDRESS;
            ok=access_matrix_buffer(qtb,cb,waffle_gpu_plan_alias(plan,r->address),r->memory,
                r->size,code?0:ECATS_PRIV|ECATS_WRITE,code,&checks);
        }
    }
    if(!arena || firmware_buffers!=3) ok=false;
    uint64_t base=waffle_gpu_plan_alias(plan,WAFFLE_HWSCHED_POOL_ADDRESS);
    for(unsigned i=0;ok && i<c->count;++i) {
        uint64_t offset=c->allocations[i].va-base;
        uint32_t size=c->allocations[i].size,flags=c->allocations[i].flags;
        if(c->allocations[i].va<base || offset>arena->size || size>arena->size-offset) {ok=false;break;}
        unsigned access=((flags&2)?ECATS_PRIV:0)|((flags&4)?ECATS_WRITE:0);
        ok=access_matrix_buffer(qtb,cb,c->allocations[i].va,arena->memory+offset,size,access,false,&checks);
    }
    log_line("waffle-iommu: ACCESS_MATRIX result=%u checks=%u allocations=%u; translation only, no RAW\n",ok,checks,c->count);
    return ok;
}

/* Diagnostic only: native GPUHALT policy with stall enabled (CFCFG1,HUPCF0),
 * while keeping host fault IRQs masked. All engines are still reset here. */
static bool diagnostic_context_stall(vm_offset_t cb)
{
    uint32_t old=r32(cb,0);
    if (!(old&1) || (old&(1u<<6)) || (r32(cb,0x58)&FSR_FAULT_MASK)) return false;
    uint32_t wanted=(old|(1u<<7))&~(1u<<8);
    w32(cb,0,wanted);
    bool ok=r32(cb,0)==wanted;
    log_line("waffle-iommu: diagnostic stall context=%llx SCTLR=%08x ready=%u\n",(uint64_t)cb,wanted,ok);
    return ok;
}
/* Native non-GPUHALT policy terminates a faulting transaction but continues
 * subsequent ones (HUPCF=1), preventing an outstanding fault hanging the GPU.
 * This diagnostic retains CFIE=0: XNU has no GPU SMMU fault IRQ handler yet. */
static bool gpu_context_fault_continue(vm_offset_t cb)
{
    uint32_t old=r32(cb,0);
    if (!(old&1) || (old&(1u<<6)) || (r32(cb,0x58)&FSR_FAULT_MASK)) return false;
    uint32_t wanted=(old|(1u<<8))&~(1u<<7);
    w32(cb,0,wanted);
    bool ok=r32(cb,0)==wanted;
    log_line("waffle-iommu: fault-continue CB0 SCTLR=%08x ready=%u; CFIE masked\n",wanted,ok);
    return ok;
}
/* Independent GPU user stream SID0/context0, alongside GMU SID5/context1.
 * Only unused bank/stream slots can be borrowed. Same tested page-table format. */
struct gpu_context {
    vm_offset_t smmu, cb;
    uint32_t page, ctl, cbar, cba2r, smr, s2cr, old[9];
    unsigned bank, slot, sid;
    bool changed;
};
static const uint32_t gpu_cb_offsets[] = {4,0x10,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c};
static bool gpu_context_begin_at(struct gpu_context *g, vm_offset_t smmu,
    unsigned page, unsigned pages, unsigned contexts, unsigned matches, uint64_t root,
    unsigned bank,unsigned slot,unsigned sid)
{
    bzero(g,sizeof(*g));
    if (bank>=contexts || slot>=matches || sid>0x7fff || (root & 4095) || root >= (1ULL<<36)) return false;
    g->smmu = smmu; g->page = page; g->cb = smmu + (pages+bank)*page;
    g->bank=bank;g->slot=slot;g->sid=sid;
    g->ctl = r32(g->cb,0);
    if ((g->ctl & 1) || (r32(g->cb,0x58) & FSR_FAULT_MASK)) return false;
    for (unsigned i = 0; i < matches; ++i) {
        uint32_t smr = r32(smmu,0x800+i*4), s2cr = r32(smmu,0xc00+i*4);
        uint32_t mask = (smr>>16)&0x7fff;
        if ((smr>>31) && (((smr & 0x7fff & ~mask) == (sid&~mask)) ||
                ((s2cr&0x30000)==0 && (s2cr&255)==bank))) return false;
    }
    g->smr = r32(smmu,0x800+slot*4); g->s2cr = r32(smmu,0xc00+slot*4);
    if (g->smr>>31) return false;
    g->cbar = r32(smmu,page+bank*4); g->cba2r = r32(smmu,page+0x800+bank*4);
    for (unsigned i = 0; i < 9; ++i) g->old[i] = r32(g->cb,gpu_cb_offsets[i]);
    g->changed = true;
    w32(g->cb,0,0); w32(smmu,page+0x800+bank*4,1); w32(smmu,page+bank*4,0x1f300);
    w32(g->cb,4,0x32b);
    w32(g->cb,0x10,1|(1u<<4)|(7u<<15));
    w32(g->cb,0x30,25|(1u<<8)|(1u<<10)|(3u<<12)|(1u<<23));
    uint64_t ttbr=root|((uint64_t)(bank+1)<<48);
    w64(g->cb,0x20,ttbr); w64(g->cb,0x28,0);
    w32(g->cb,0x38,0x44); w32(g->cb,0x3c,0);
    if (!tlb_sync(g->cb)) return false;
    w32(g->cb,0,1|2|4|(1u<<5)|(1u<<12));
    if (!(r32(g->cb,0)&1) || r64(g->cb,0x20)!=ttbr) return false;
    w32(smmu,0xc00+slot*4,bank); w32(smmu,0x800+slot*4,(1u<<31)|sid);
    bool ok = r32(smmu,0x800+slot*4)==((1u<<31)|sid) && (r32(smmu,0xc00+slot*4)&0x300ff)==bank;
    log_line("waffle-iommu: GPU context%u/SID%u enabled=%u\n",bank,sid,ok);
    return ok;
}
static bool gpu_context_begin(struct gpu_context *g, vm_offset_t smmu,
    unsigned page,unsigned pages,unsigned contexts,unsigned matches,uint64_t root)
{
    return gpu_context_begin_at(g,smmu,page,pages,contexts,matches,root,0,0,0);
}
/* Engines remain reset, QTB is halted by the caller. Mirror the existing
 * lower table into native TTBR1: physical pages and permissions stay identical.
 * arm_smmu_lpae_tcr shifts the same 39-bit geometry into T1, selects ASID from
 * TTBR0 (A1 clear), then set_ttbr0_cfg enables both halves. */
static inline bool gpu_context_split(struct gpu_context *g)
{
    if (!g || !g->changed || !((g->bank==0 && g->sid==0) ||
            (g->bank==1 && g->sid==1))) return false;
    uint32_t ctl=r32(g->cb,0),tcr=r32(g->cb,0x30);
    uint64_t ttbr=r64(g->cb,0x20);
    if (!(ctl&1) || (r32(g->cb,0x58)&FSR_FAULT_MASK) ||
        (tcr&63)!=25 || !(tcr&(1u<<23)) || r64(g->cb,0x28) || !(ttbr&PTE_ADDRESS)) return false;
    uint32_t low=tcr&0xffffu;
    /* TG0=00 and TG1=10 both encode 4KB granules. Copying TG0 into TG1
     * leaves a reserved encoding. Native qcom allocator selects TG1_4K=2
     * before arm_smmu_lpae_tcr shifts the upper-half fields. */
    if (low&(3u<<14)) return false; /* This mapper only builds 4KB tables. */
    uint32_t split=(low|((low<<16)&~(1u<<22)))&~((1u<<7)|(1u<<23)|(3u<<30));
    split|=2u<<30;
    w32(g->cb,0,0);
    w64(g->cb,0x28,ttbr);
    w32(g->cb,0x30,split);
    bool synced=tlb_sync(g->cb);
    w32(g->cb,0,ctl);
    bool ok=synced && r32(g->cb,0x30)==split && r64(g->cb,0x28)==ttbr && (r32(g->cb,0)&1);
    log_line("waffle-iommu: GPU split TTBR1 enabled=%u TCR=%08x TTBR=%llx\n",ok,split,ttbr);
    return ok;
}
static bool gpu_context_end(struct gpu_context *g)
{
    if (!g->changed) return true;
    w32(g->smmu,0x800+g->slot*4,0); w32(g->smmu,0xc00+g->slot*4,g->s2cr); w32(g->smmu,0x800+g->slot*4,g->smr);
    uint32_t faults = r32(g->cb,0x58)&FSR_FAULT_MASK;
    if (faults) {
        log_line("waffle-iommu: GPU context%u fault=%08x FAR=%llx\n",g->bank,faults,r64(g->cb,0x60));
        w32(g->cb,0x58,faults);
        if (faults&(1u<<30)) w32(g->cb,8,1);
    }
    w32(g->cb,0,0);
    bool synced = tlb_sync(g->cb);
    w32(g->cb,0x10,g->old[1]); w32(g->cb,0x30,g->old[6]);
    for (unsigned i = 0; i < 9; ++i)
        if (i!=1 && i!=6) w32(g->cb,gpu_cb_offsets[i],g->old[i]);
    uint32_t cbar = g->cbar;
    if (((cbar>>16)&3)==0 && !(r32(g->smmu,0x20)&(1u<<29))) cbar=(cbar&~0x30000u)|(1u<<16);
    w32(g->smmu,g->page+g->bank*4,cbar); w32(g->smmu,g->page+0x800+g->bank*4,g->cba2r);
    w32(g->cb,0,g->ctl); g->changed=false;
    log_line("waffle-iommu: GPU context%u restored TLB=%s faults=%08x\n",g->bank,synced?"done":"TIMEOUT",faults);
    if (!synced) log_line("waffle-gmu: REBOOT REQUIRED: GPU context TLB sync failed; keep pages\n");
    return synced;
}

static bool gpu_secure_context_probe(vm_offset_t,unsigned,unsigned,unsigned,unsigned,vm_offset_t);
#define PROTECTED_POOL_ADDRESS 0xa0000000u
#define PROTECTED_POOL_BYTES 0x00400000u
struct protected_gpu_pool {
    struct table_pool tables;
    struct gpu_context context;
    vm_offset_t data;
    uint64_t address;
    uint64_t phys[PROTECTED_POOL_BYTES/16384];
    unsigned owned;
    bool shared;
};
static struct protected_gpu_pool *protected_pool_prepare(vm_offset_t,unsigned,unsigned,unsigned,unsigned,vm_offset_t,uint64_t);
static void protected_pool_release(struct protected_gpu_pool *);

static const uint32_t smmu_gmu_offsets[]={0x4,0x10,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c};
struct smmu_owner {
    vm_offset_t smmu,qtb,gmu,cc,cb,target;
    unsigned page,pages,contexts,matches,probe,index,lpac_checks;
    uint32_t lpac_map,zap,writeback,ib,session,access_matrix,dynamic_bo,compute_mode,compute_image;
    uint32_t saved_ctl,saved_smr,saved_s2cr,old_cbar,old_cba2r,old[9];
    uint64_t old_fence,old_inputs[3],target_pa;
    struct gpu_context gpu_context,lpac_context;
    struct table_pool pool;
    struct waffle_gmu_plan firmware;
    struct waffle_gmu_region dynamic,data;
    struct waffle_gpu_buffer user_buffer;
    struct waffle_gpu_registry registry;
    struct protected_gpu_pool *protected_pool;
    struct pool_permission_context permission_context;
    struct access_matrix_context matrix;
    struct waffle_gmu_owner *child;
    bool context_changed,stream_changed,safe_free,snapshot_ready,gmu_ok;
};
static void smmu_owner_stop(const char *reason)
{
    log_line("waffle-gmu: REBOOT REQUIRED: %s; retain SMMU owner and all child pages\n",reason);
    loader_return();
    for(;;)__asm__ volatile("wfi");
}
static bool smmu_owner_begin(struct smmu_owner *s)
{
    vm_offset_t smmu=s->smmu;
    unsigned page=s->page,pages=s->pages,contexts=s->contexts,matches=s->matches,probe=s->probe;

    if(PE_parse_boot_argn("waffle_lpac_map",&s->lpac_map,sizeof(s->lpac_map)) &&
        (s->lpac_map!=1 || (probe!=93 && probe!=94))) {
        log_line("waffle-iommu: LPAC mapping requires controlled probe93/94; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_zap",&s->zap,sizeof(s->zap)) &&
        (s->zap!=1 || probe!=94 || s->lpac_map!=1)) {
        log_line("waffle-iommu: ZAP requires controlled94 with LPAC; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_writeback",&s->writeback,sizeof(s->writeback)) &&
        (s->writeback!=1 || probe!=94 || s->lpac_map!=1 || s->zap!=1)) {
        log_line("waffle-iommu: writeback requires controlled94 LPAC/ZAP; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_ib",&s->ib,sizeof(s->ib)) &&
        (s->ib!=1 || probe!=94 || s->lpac_map!=1 || s->zap!=1 || s->writeback!=1)) {
        log_line("waffle-iommu: IB requires controlled94 LPAC/ZAP/writeback; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_session",&s->session,sizeof(s->session)) &&
        (s->session!=1 || probe!=94 || s->lpac_map!=1 || s->zap!=1 || s->writeback!=1 || s->ib!=1)) {
        log_line("waffle-iommu: session requires controlled94 LPAC/ZAP/writeback/IB; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_dynamic_bo",&s->dynamic_bo,sizeof(s->dynamic_bo)) &&
        (s->dynamic_bo!=1 || probe!=94 || s->session!=1)) {
        log_line("waffle-iommu: dynamic BO requires controlled94 session; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_compute",&s->compute_mode,sizeof(s->compute_mode)) &&
        ((s->compute_mode!=1 && s->compute_mode!=2) || probe!=94 || s->dynamic_bo!=1 || s->session!=1)) {
        log_line("waffle-iommu: compute requires controlled94 dynamic BO session; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_image",&s->compute_image,sizeof(s->compute_image)) &&
        ((s->compute_image<1 || s->compute_image>13) || !s->compute_mode || (s->compute_image>=3 && s->compute_image!=9 && s->compute_mode!=2) || (s->compute_image==9 && s->compute_mode!=1) || probe!=94 || s->dynamic_bo!=1)) {
        log_line("waffle-iommu: image requires controlled compute/dynamic session; refused\n");return false;
    }
    if(PE_parse_boot_argn("waffle_ecats_access",&s->access_matrix,sizeof(s->access_matrix)) &&
        (s->access_matrix!=1 || probe!=93)) {
        log_line("waffle-iommu: access matrix requires prepare-only probe93; refused\n");return false;
    }
    log_line("waffle-iommu: map QTB500 @%08x\n", WAFFLE_GPU_QTB_BASE);
    s->qtb = ml_io_map(WAFFLE_GPU_QTB_BASE, WAFFLE_GPU_QTB_SIZE);
    if (!s->qtb) { log_line("waffle-iommu: QTB map failed\n"); return false; }
    log_line("waffle-iommu: SWID=%08x fence=%llx ack=%llx trigger=%llx status=%llx\n",
        r32(s->qtb, 0), r64(s->qtb, 0x410), r64(s->qtb, 0x418), r64(s->qtb, 0x448), r64(s->qtb, 0x450));
    if (probe < 7) return false;
    s->gmu = ml_io_map(WAFFLE_GMU_BASE, WAFFLE_GMU_SIZE);
    s->cc = ml_io_map(WAFFLE_GPUCC_BASE, WAFFLE_GPUCC_SIZE);
    if (!s->gmu || !s->cc || !(r32(s->gmu, WAFFLE_GMU_SYSRESET) & 1) ||
        (r32(s->cc, WAFFLE_GPU_GX_GDSCR) & ((1u << 31) | 1)) != 1) {
        log_line("waffle-iommu: GMU not held in reset or GX not collapsed; no writes\n"); return false;
    }
    s->index=s->lpac_map?3:1;
    const unsigned sid=5;
    if (contexts <= s->index || matches <= s->index || (r64(s->qtb, 0x410) & 1) || r64(s->qtb, 0x448)) {
        log_line("waffle-iommu: QTB/context not idle; no writes\n"); return false;
    }
    s->cb = smmu + (pages + s->index) * page;
    s->saved_ctl = r32(s->cb, 0);
    if ((s->saved_ctl & 1) || (r32(s->cb, 0x58) & FSR_FAULT_MASK)) {
        log_line("waffle-iommu: context%u enabled or faulted; no writes\n",s->index); return false;
    }
    for (unsigned i = 0; i < matches; ++i) {
        uint32_t smr = r32(smmu, 0x800 + i * 4), s2cr = r32(smmu, 0xc00 + i * 4);
        uint32_t mask = (smr >> 16) & 0x7fff;
        if ((smr >> 31) && (((sid ^ smr) & 0x7fff & ~mask) == 0 ||
            ((s2cr & 0x30000) == 0 && (s2cr & 255) == s->index))) {
            log_line("waffle-iommu: stream/context in use at entry%u; no writes\n", i); return false;
        }
    }
    s->saved_smr=r32(smmu,0x800+s->index*4);s->saved_s2cr=r32(smmu,0xc00+s->index*4);
    if (s->saved_smr >> 31) { log_line("waffle-iommu: entry%u occupied; no writes\n",s->index); return false; }
    for (unsigned i = 0; i < sizeof(smmu_gmu_offsets)/sizeof(smmu_gmu_offsets[0]); ++i) s->old[i] = r32(s->cb, smmu_gmu_offsets[i]);
    s->old_cbar = r32(smmu, page + s->index * 4);
    s->old_cba2r = r32(smmu, page + 0x800 + s->index * 4);
    s->old_fence=r64(s->qtb,0x410);
    for (unsigned i = 0; i < 3; ++i) s->old_inputs[i] = r64(s->qtb, 0x430 + 8 * i);
    s->snapshot_ready=true;
    if (probe >= 8 && !waffle_gmu_prepare(&s->firmware, probe)) return false;
    s->firmware.compute_mode=s->compute_mode;
    s->firmware.compute_image=s->compute_image;
    if (!new_table(&s->pool) || kmem_alloc(kernel_map, &s->target, PAGE_SIZE,
            KMA_KOBJECT | KMA_ZERO | KMA_DATA, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) return false;
    s->target_pa = kvtophys(s->target);
    const uint64_t iova = probe >= 9 ? 0x7ff00000 : 0x60010000;
    if (!map_page(&s->pool, iova, s->target_pa, false)) return false;
    if (probe >= 19 && !map_page(&s->pool,0x80000000,s->target_pa,false)) return false;
    if (s->firmware.compact_gpu_va && !map_page(&s->pool,
            waffle_gpu_plan_alias(&s->firmware,0x80000000)-WAFFLE_GPU_GLOBAL_BASE,s->target_pa,false)) return false;
    for (unsigned i = 0; i < s->firmware.count; ++i) {
        struct waffle_gmu_region *r = &s->firmware.regions[i];
        for (uint32_t off = 0; off < r->size; off += 4096)
            /* Native adreno_get_firmware allocates GPUREADONLY|UCODE WITHOUT
             * KGSL_MEMDESC_PRIVILEGED: AP_UNPRIV is required as well as RDONLY.
             * The dedicated command BO also needs AP_UNPRIV; other writable
             * firmware/restore mappings retain privileged-only access. */
            if (!map_page_access(&s->pool,(uint64_t)r->address+off,kvtophys(r->memory+off),
                    r->readonly,waffle_diagnostic_unprivileged(r->address,r->gpu_only,r->readonly))) return false;
    }
    if (s->firmware.compact_gpu_va) {
        for (unsigned i=0;i<s->firmware.count;i++) {
            struct waffle_gmu_region *r=&s->firmware.regions[i];
            if (!r->gpu_only && r->address!=WAFFLE_HWSCHED_POOL_ADDRESS) continue;
            for(uint32_t off=0;off<r->size;off+=4096) {
                uint64_t alias=waffle_gpu_plan_alias(&s->firmware,(uint64_t)r->address+off);
                if (!alias || !map_page_access(&s->pool,alias-WAFFLE_GPU_GLOBAL_BASE,
                    kvtophys(r->memory+off),r->readonly,waffle_diagnostic_unprivileged(r->address,r->gpu_only,r->readonly))) return false;
            }
        }
        log_line("waffle-iommu: compact GPU globals window=20MiB normal_pool=15MiB\n");
    }
    for (unsigned i = 0; i < s->pool.count; ++i) clean(s->pool.memory[i]);
    clean(s->target);
    log_line("waffle-iommu: test IOVA=%llx expected PA=%llx root=%llx tables=%u; halt QTB\n",
        iova, s->target_pa, s->pool.phys[0], s->pool.count);
    w64(s->qtb, 0x410, s->old_fence | 1);
    if (!poll(s->qtb, 0x418, 1, 1, 1000)) {
        log_line("waffle-iommu: QTB halt timeout; no context writes\n"); return false;
    }
    s->context_changed = true;
    w32(s->cb, 0, 0);
    w32(smmu, page + 0x800 + s->index * 4, 1); /* CBA2R VA64 */
    w32(smmu, page + s->index * 4, 0x1f300); /* stage1, stage2 bypass */
    w32(s->cb, 4, 0x32b); /* PJD110 qcom,actlr for SID0..3ff */
    w32(s->cb, 0x10, 1 | (1u << 4) | (7u << 15)); /* PA36, ASID16, SEP upstream */
    w32(s->cb, 0x30, 25 | (1u << 8) | (1u << 10) | (3u << 12) | (1u << 23));
    w64(s->cb, 0x20, s->pool.phys[0] | (1ULL << 48));
    w64(s->cb, 0x28, 0);
    /* Vendor GMU allocations use READ|WRITE|PRIV without IOMMU_CACHE.
     * Use normal NC for the live HFI test, matching io-pgtable-arm.c. */
    w32(s->cb, 0x38, probe >= 11 ? 0x44 : 0xff);
    w32(s->cb, 0x3c, 0);
    if (!tlb_sync(s->cb)) { log_line("waffle-iommu: initial TLB sync timeout\n"); return false; }
    w32(s->cb, 0, 1 | 2 | 4 | (1u << 5) | (1u << 12)); /* CFIE/CFCFG remain off */
    if (!(r32(s->cb, 0) & 1) || r64(s->cb, 0x20) != (s->pool.phys[0] | (1ULL << 48)) ||
        !(r32(smmu, page + 0x800 + s->index * 4) & 1)) {
        log_line("waffle-iommu: context register readback refused; stop\n"); return false;
    }
    s->stream_changed = true;
    w32(smmu, 0xc00 + s->index * 4, s->index);
    w32(smmu, 0x800 + s->index * 4, (1u << 31) | sid);
    if (r32(smmu, 0x800 + s->index * 4) != ((1u << 31) | sid) ||
        (r32(smmu, 0xc00 + s->index * 4) & 0x300ff) != s->index) {
        log_line("waffle-iommu: stream register readback refused; stop\n"); return false;
    }
    if (probe >= 19) {
        if (!gpu_context_begin(&s->gpu_context,smmu,page,pages,contexts,matches,s->pool.phys[0])) return false;
        if (probe>=39) {
            if (!gpu_context_split(&s->gpu_context) ||
                !translate_page(s->qtb,s->gpu_context.cb,waffle_gpu_plan_alias(&s->firmware,0x80000000),s->target_pa,0)) return false;
        }
        if (!translate_page(s->qtb,s->gpu_context.cb,0x80000000,s->target_pa,0)) return false;
        log_line("waffle-iommu: GPU SID0 translation matches allocated PA\n");
    }
    if (s->lpac_map) {
        if (!gpu_context_begin_at(&s->lpac_context,smmu,page,pages,contexts,matches,s->pool.phys[0],1,1,1) ||
            !gpu_context_split(&s->lpac_context)) return false;
        /* Check every mapped SQE page, including BR/BV/LPAC bootstrap and
         * jump tables. No HFI pool translations: permissions change later. */
        bool found=false;
        for (unsigned i=0;i<s->firmware.count;++i) {
            struct waffle_gmu_region *r=&s->firmware.regions[i];
            if (r->address!=WAFFLE_GPU_SQE_ADDRESS) continue;
            if (!r->readonly || !r->gpu_only || !r->size || r->size>0x20000) return false;
            found=true;
            for (uint32_t off=0;off<r->size;off+=4096) {
                for (unsigned instruction=0;instruction<2;++instruction) {
                    ++s->lpac_checks;
                    if (!translate_page_access(s->qtb,s->lpac_context.cb,
                        waffle_gpu_plan_alias(&s->firmware,(uint64_t)r->address+off),
                        kvtophys(r->memory+off),1,instruction?ECATS_INST:0,1)) return false;
                }
            }
        }
        if (!found || !waffle_scm_lpac_aperture()) return false;
        log_line("waffle-iommu: LPAC_MAP routing=1 checks=%u SID1/CB1 GMU_SID5/CB3; translation only\n",s->lpac_checks);
    }
    bool matches_pa = translate_page(s->qtb, s->cb, iova, s->target_pa, 5);
    if (matches_pa) log_line("waffle-iommu: HARDWARE TRANSLATION MATCHES allocated PA\n");
    if (matches_pa && probe>=30) {
        s->protected_pool=protected_pool_prepare(smmu,page,pages,contexts,matches,s->qtb,probe>=56?0x100000000ULL:PROTECTED_POOL_ADDRESS);
        if (!s->protected_pool) matches_pa=false;
        else {s->firmware.protected_address=s->protected_pool->address;s->firmware.protected_size=PROTECTED_POOL_BYTES;}
    }
    if (matches_pa && probe>=37 && !waffle_scm_gpu_aperture()) return false;
    if (matches_pa && (probe==90 || probe==93 || probe==91 || probe==94)) {
        if (!s->protected_pool || !diagnostic_context_stall(s->protected_pool->context.cb)) return false;
        log_line("waffle-iommu: SEC_STALL%u CB2 SCTLR=%08x; CFIE masked\n",probe,r32(s->protected_pool->context.cb,0));
    }
    if (matches_pa && probe==36) {
        /* Only this probe changes fault policy, after translation validation,
         * before CM3/CP start. Normal context teardown disables these banks. */
        if (!s->protected_pool || !diagnostic_context_stall(s->gpu_context.cb) ||
            !diagnostic_context_stall(s->cb) || !diagnostic_context_stall(s->protected_pool->context.cb)) return false;
        s->firmware.fault_smmu=smmu;s->firmware.fault_page=page;s->firmware.fault_pages=pages;
        log_line("waffle-iommu: stall diagnostics armed for CB0/CB1/CB2; CFIE masked\n");
    }
    if (matches_pa && probe == 29) {
        if (gpu_secure_context_probe(smmu,page,pages,contexts,matches,s->qtb))
            log_line("waffle-iommu: protected context test passed\n");
    } else if (matches_pa && probe >= 8) {
        for (unsigned i = 0; i < s->firmware.count; ++i) {
            struct waffle_gmu_region *r = &s->firmware.regions[i];
            uint32_t last = r->size - 4096;
            vm_offset_t region_cb = r->gpu_only ? s->gpu_context.cb : s->cb;
            unsigned region_sid = r->gpu_only ? 0 : 5;
            if (s->firmware.split_gpu_va && (r->gpu_only || r->address==WAFFLE_HWSCHED_POOL_ADDRESS) &&
                (!translate_page(s->qtb,s->gpu_context.cb,waffle_gpu_plan_alias(&s->firmware,r->address),kvtophys(r->memory),0) ||
                 (last && !translate_page(s->qtb,s->gpu_context.cb,waffle_gpu_plan_alias(&s->firmware,(uint64_t)r->address+last),kvtophys(r->memory+last),0)))) {
                matches_pa=false;break;
            }
            if (!translate_page(s->qtb, region_cb, r->address, kvtophys(r->memory), region_sid) ||
                (last && !translate_page(s->qtb, region_cb, (uint64_t)r->address + last, kvtophys(r->memory + last), region_sid))) {
                matches_pa = false; break;
            }
        }
        if (matches_pa && (probe==84 || probe==85 || probe==86 || probe==87 || probe==88 || probe==89 || probe==91 || probe==94 || probe==90 || probe==93) && !gpu_context_fault_continue(s->gpu_context.cb)) return false;
        if (matches_pa && (probe==83 || probe==84 || probe==85 || probe==86 || probe==87 || probe==88 || probe==89 || probe==91 || probe==94 || probe==90 || probe==93)) {
            /* Read-only CB0 snapshot while its clocks and mappings are owned.
             * Compare actual readback, including architectural RES1/RAZ bits,
             * with Android; source write constants alone are insufficient. */
            log_line("waffle-iommu: SMMU%u CB0 SCTLR=%08x ACTLR=%08x TCR2=%08x TCR=%08x CONTEXTIDR=%08x\n",
                probe,r32(s->gpu_context.cb,0),r32(s->gpu_context.cb,4),r32(s->gpu_context.cb,0x10),
                r32(s->gpu_context.cb,0x30),r32(s->gpu_context.cb,0x34));
            log_line("waffle-iommu: SMMU%u TTBR0=%llx TTBR1=%llx MAIR0=%08x MAIR1=%08x CBAR=%08x CBA2R=%08x S2CR=%08x\n",
                probe,r64(s->gpu_context.cb,0x20),r64(s->gpu_context.cb,0x28),r32(s->gpu_context.cb,0x38),r32(s->gpu_context.cb,0x3c),
                r32(smmu,page),r32(smmu,page+0x800),r32(smmu,0xc00));
        }
        if (matches_pa && (probe==85 || probe==86 || probe==89 || probe==91 || probe==94)) {
            s->firmware.fault_smmu=smmu;s->firmware.fault_page=page;s->firmware.fault_pages=pages;
            log_line("waffle-iommu: HUPCF%u RAW fault readback armed; no fault clear/resume\n",probe);
        }
        s->permission_context=(struct pool_permission_context){.tables=&s->pool,.cb=s->gpu_context.cb,
            .lpac_cb=s->lpac_map?s->lpac_context.cb:0};
        if(probe>=72){s->firmware.pool_permissions=pool_permissions;s->firmware.pool_permissions_context=&s->permission_context;}
        s->matrix=(struct access_matrix_context){.permissions=s->permission_context};
        if(s->access_matrix){s->firmware.pool_permissions=access_matrix_capture;s->firmware.pool_permissions_context=&s->matrix;}
        if(matches_pa && s->session) {
            s->child=waffle_gmu_owner_begin(&s->firmware,probe,s->qtb);
            if(s->child)log_line("waffle-iommu: GMU component returned live; parent owns SMMU and firmware\n");
            return s->child!=NULL;
        } else if(matches_pa)s->gmu_ok=waffle_gmu_probe_tcm(&s->firmware,probe,s->qtb);
    }
    return s->gmu_ok;
}
static void smmu_owner_complete(struct smmu_owner *s)
{
    unsigned probe=s->probe;
        if (s->gmu_ok) {
            log_line("waffle-iommu: GMU test passed, boot_test=%u; CM3 held reset again\n", probe >= 9);
            if(s->lpac_map && !(r32(s->lpac_context.cb,0x58)&FSR_FAULT_MASK)) {
                if(probe==93) log_line("waffle-iommu: LPAC_MAP lifecycle=1 checks=%u; no CP RAW\n",s->lpac_checks);
                else log_line("waffle-iommu: LPAC_MAP lifecycle=1 checks=%u; CP control completed\n",s->lpac_checks);
            }
            if(s->access_matrix) (void)access_matrix_run(&s->matrix,&s->firmware,s->qtb,s->gpu_context.cb,s->gmu,s->cc);
        }
}
static bool smmu_owner_finish(struct smmu_owner *s)
{
    if(s->child || s->firmware.submit_session)smmu_owner_stop("live GMU child prevents SMMU detach");
    if(!s->snapshot_ready)return true;
    vm_offset_t smmu=s->smmu;
    unsigned page=s->page;

    if (s->protected_pool) protected_pool_release(s->protected_pool);
    bool lpac_restored=gpu_context_end(&s->lpac_context);
    s->safe_free = gpu_context_end(&s->gpu_context) && lpac_restored;
    if(s->lpac_map) log_line("waffle-iommu: LPAC_MAP restored=%u\n",lpac_restored);
    w64(s->qtb, 0x448, 0);
    if (s->stream_changed) {
        w32(smmu, 0x800 + s->index * 4, 0);
        w32(smmu, 0xc00 + s->index * 4, s->saved_s2cr);
        w32(smmu, 0x800 + s->index * 4, s->saved_smr);
    }
    if (s->context_changed) {
        uint32_t faults = r32(s->cb, 0x58) & FSR_FAULT_MASK;
        if (faults) {
            log_line("waffle-iommu: cleanup fault=%08x FAR=%llx\n", faults, r64(s->cb, 0x60));
            w32(s->cb, 0x58, faults);
            if (faults & (1u << 30)) w32(s->cb, 8, 1);
        }
        w32(s->cb, 0, 0);
        s->safe_free = tlb_sync(s->cb) && s->safe_free;
        /* Restore TCR before TTBR, with translation disabled throughout. */
        w32(s->cb, 0x10, s->old[1]); w32(s->cb, 0x30, s->old[6]);
        for (unsigned i = 0; i < sizeof(smmu_gmu_offsets)/sizeof(smmu_gmu_offsets[0]); ++i)
            if (i != 1 && i != 6) w32(s->cb, smmu_gmu_offsets[i], s->old[i]);
        /* A reset/unassigned CBAR reads zero (stage2), although IDR0.S2TS
         * says this unit has NO stage2. Writing that reset encoding back
         * caused an external abort at 03da1004 on the first hardware test.
         * Leave this disabled, unassigned bank in a supported stage1 mode,
         * as the vendor driver does when releasing a context bank.
         */
        uint32_t restore_cbar = s->old_cbar;
        if (((s->old_cbar >> 16) & 3) == 0 && !(r32(smmu, 0x20) & (1u << 29))) {
            restore_cbar = (s->old_cbar & ~0x30000u) | (1u << 16);
            log_line("waffle-iommu: inactive CBAR reset type0 is not writable; keep supported stage1 type\n");
        }
        w32(smmu, page + s->index * 4, restore_cbar);
        w32(smmu, page + 0x800 + s->index * 4, s->old_cba2r);
        w32(s->cb, 0, s->saved_ctl);
        log_line("waffle-iommu: context/stream restored, TLB sync=%s\n", s->safe_free ? "done" : "TIMEOUT");
    }
    for (unsigned i = 0; i < 3; ++i) w64(s->qtb, 0x430 + 8 * i, s->old_inputs[i]);
    w64(s->qtb, 0x410, s->old_fence);
    (void)r32(s->qtb, 0); barrier();
    if (s->safe_free) {
        if(s->registry.buffers){
            unsigned count=s->registry.count,issued=s->registry.issued,remaining=0;
            for(unsigned i=0;i<count;i++)if(s->registry.buffers[i].object)remaining++;
            if(!waffle_gpu_registry_destroy(&s->registry,true))smmu_owner_stop("general BO reclamation failed after detach");
            log_line("waffle-iommu: GENERAL_BO released after GPU stop and context detach count=%u reclaimed_earlier=%u total=%u\n",remaining,issued-remaining,issued);
        }
        for (unsigned i = 0; i < s->pool.count; ++i) kmem_free(kernel_map, s->pool.memory[i], PAGE_SIZE);
        if (s->target) kmem_free(kernel_map, s->target, PAGE_SIZE);
        waffle_gmu_free(&s->firmware);
        if(s->user_buffer.memory){
            kmem_free(kernel_map,s->user_buffer.memory,PAGE_SIZE);
            log_line("waffle-iommu: USER_BO released after GPU stop and context detach\n");
        }
        if(s->data.memory){
            kmem_free(kernel_map,s->data.memory,PAGE_SIZE);
            log_line("waffle-iommu: DATA_BO released after GPU stop and context detach\n");
        }
        if(s->dynamic.memory) {
            kmem_free(kernel_map,s->dynamic.memory,PAGE_SIZE);
            log_line("waffle-iommu: DYNAMIC_BO released after GPU stop and context detach\n");
        }
    } else log_line("waffle-iommu: keep test pages allocated; reboot Android before retry\n");    return s->safe_free;
}
/* No ATOS/ECATS while GPU is live. A vacant leaf plus explicit cache/TLB
 * publication is checked by subsequent real GPU fetch and CPU readback. */
static bool dynamic_bo_vacant(struct table_pool *pool,uint64_t iova)
{
    uint64_t *root=(uint64_t *)pool->memory[0];
    uint64_t entry=root[(iova>>30)&511];
    if(!entry)return true;
    uint64_t *second=permission_table(pool,entry);
    if(!second)return false;
    entry=second[(iova>>21)&511];
    if(!entry)return true;
    uint64_t *leaf=permission_table(pool,entry);
    return leaf && !leaf[(iova>>12)&511];
}
static bool smmu_registry_idle(void *context)
{
    struct smmu_owner *s=context;
    return s && s->child && s->compute_image==13 && waffle_gmu_owner_memory_idle(s->child);
}
static bool smmu_registry_vacant(void *context,uint64_t address)
{
    struct smmu_owner *s=context;return dynamic_bo_vacant(&s->pool,address);
}
static bool smmu_registry_page(void *context,uint64_t address,uint64_t pa,bool readonly)
{
    struct smmu_owner *s=context;return map_page_access(&s->pool,address,pa,readonly,true);
}
static void smmu_registry_clean(void *context)
{
    struct smmu_owner *s=context;for(unsigned i=0;i<s->pool.count;i++)clean(s->pool.memory[i]);
}
static bool smmu_registry_tlb(void *context)
{
    struct smmu_owner *s=context;return pool_permission_sync(&s->permission_context);
}
static uint64_t *smmu_registry_leaf(struct table_pool *pool,uint64_t address)
{
    if(!pool || !pool->count || !pool->memory[0])return NULL;
    uint64_t *root=(uint64_t *)pool->memory[0];
    uint64_t *middle=permission_table(pool,root[(address>>30)&511]);
    uint64_t *leaf=middle?permission_table(pool,middle[(address>>21)&511]):NULL;
    return leaf?&leaf[(address>>12)&511]:NULL;
}
static bool smmu_registry_owns_page(void *context,uint64_t address,uint64_t pa,bool readonly)
{
    struct smmu_owner *s=context;
    uint64_t *entry=smmu_registry_leaf(&s->pool,address);
    uint64_t expected=pa|3|(2ULL<<8)|(1ULL<<10)|(1ULL<<11)|(1ULL<<6)|(readonly?1ULL<<7:0);
    return entry && *entry==expected;
}
static bool smmu_registry_unmap_page(void *context,uint64_t address,uint64_t pa,bool readonly)
{
    struct smmu_owner *s=context;
    if(!smmu_registry_owns_page(s,address,pa,readonly))return false;
    *smmu_registry_leaf(&s->pool,address)=0;
    return true;
}
/* All leaves and both context-bank TLBs belong to this retained owner. */
static bool smmu_registry_reclaim(struct smmu_owner *s,struct waffle_gpu_memory *bo,bool cpu_unmapped)
{
    if(!s || s->compute_image!=13 || !s->child ||
       !s->permission_context.cb || !s->permission_context.lpac_cb)return false;
    const struct waffle_gpu_registry_ops base={smmu_registry_idle,smmu_registry_vacant,
        smmu_registry_page,smmu_registry_clean,smmu_registry_tlb,s};
    const struct waffle_gpu_reclaim_ops ops={&base,smmu_registry_owns_page,smmu_registry_unmap_page};
    return waffle_gpu_registry_reclaim(&s->registry,&ops,bo,cpu_unmapped);
}
static void smmu_registry_release_storage(uintptr_t address,uint32_t bytes)
{
    kmem_free(kernel_map,address,bytes);
}
static bool smmu_registry_prepare(struct smmu_owner *s)
{
    if(s->registry.buffers)return true;
    const uint32_t bytes=(sizeof(struct waffle_gpu_memory)*WAFFLE_GPU_BO_LIMIT+PAGE_SIZE-1)&~(PAGE_SIZE-1);
    vm_offset_t storage=0;
    if(kmem_alloc(kernel_map,&storage,bytes,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
        VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
    s->registry.buffers=(struct waffle_gpu_memory *)storage;
    s->registry.storage_bytes=bytes;
    s->registry.release_storage=smmu_registry_release_storage;
    log_line("waffle-iommu: GENERAL registry_storage entries=%u bytes=%u GPU_mapped=0\n",WAFFLE_GPU_BO_LIMIT,bytes);
    return true;
}
static struct waffle_gpu_memory *smmu_registry_new(struct smmu_owner *s,uint64_t bytes,uint32_t flags)
{
    if(!s || s->compute_image!=13)return NULL;
    if(!s->registry.buffers && (!waffle_gpu_registry_flags(bytes,flags) ||
        !smmu_registry_idle(s) || !smmu_registry_prepare(s)))return NULL;
    const struct waffle_gpu_registry_ops ops={smmu_registry_idle,smmu_registry_vacant,
        smmu_registry_page,smmu_registry_clean,smmu_registry_tlb,s};
    struct waffle_gpu_memory *bo=waffle_gpu_registry_new(&s->registry,&ops,bytes,flags);
    if(s->registry.poisoned){
        log_line("waffle-iommu: GENERAL_BO publication failed index=%u bytes=%llu tables=%u limit=%u\n",s->registry.issued,bytes,s->pool.count,TABLE_LIMIT);
        smmu_owner_stop("general BO publication incomplete; retain backing and tables");
    }
    if(bo)log_line("waffle-iommu: GENERAL_BO published index=%u VA=%llx bytes=%u allocated=%u flags=%x pages=%u\n",
        bo->serial,bo->gpu_va,bo->bytes,bo->allocation_bytes,bo->flags,bo->allocation_bytes/4096);
    return bo;
}
static struct waffle_gpu_memory *smmu_registry_adopt(struct smmu_owner *s,struct waffle_gpu_memory *prepared)
{
    if(!s || s->compute_image!=13 || !prepared || !prepared->object)return NULL;
    if(!s->registry.buffers && (!smmu_registry_idle(s) || !smmu_registry_prepare(s)))return NULL;
    const struct waffle_gpu_registry_ops ops={smmu_registry_idle,smmu_registry_vacant,
        smmu_registry_page,smmu_registry_clean,smmu_registry_tlb,s};
    struct waffle_gpu_memory *bo=waffle_gpu_registry_adopt(&s->registry,&ops,prepared);
    if(s->registry.poisoned)smmu_owner_stop("surface publication incomplete; retain surface backing and tables");
    if(bo)log_line("waffle-iommu: SURFACE_BO published index=%u VA=%llx bytes=%u cached=1 pages=%u\n",
        bo->serial,bo->gpu_va,bo->allocation_bytes,bo->allocation_bytes/4096);
    return bo;
}
static bool smmu_bo_allocate_map(struct smmu_owner *s,struct waffle_gmu_region *bo,uint32_t address)
{
    const uint32_t bytes=16384;
    uint64_t alias=waffle_gpu_plan_alias(&s->firmware,address);
    if(bo->memory || !s->child || !s->pool.count || !s->firmware.compact_gpu_va ||
        !alias || !waffle_gmu_owner_can_bind_bo(s->child))return false;
    if((address!=WAFFLE_GPU_DYNAMIC_ADDRESS && address!=WAFFLE_GPU_DATA_ADDRESS) ||
        (bo!=&s->dynamic && s->dynamic.memory && address<s->dynamic.address+s->dynamic.size && s->dynamic.address<address+bytes))return false;
    for(unsigned i=0;i<s->firmware.count;i++) {
        struct waffle_gmu_region *r=&s->firmware.regions[i];
        if((uint64_t)address<(uint64_t)r->address+r->size && (uint64_t)r->address<address+bytes)return false;
    }
    for(unsigned off=0;off<bytes;off+=4096)
        if(!dynamic_bo_vacant(&s->pool,(uint64_t)address+off) ||
            !dynamic_bo_vacant(&s->pool,alias-WAFFLE_GPU_GLOBAL_BASE+off))return false;
    vm_offset_t memory=0;
    if(kmem_alloc(kernel_map,&memory,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
        VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
    *bo=(struct waffle_gmu_region){.address=address,.size=bytes,.memory=memory,.gpu_only=true};
    for(unsigned off=0;off<bytes;off+=4096)
        if(!map_page_access(&s->pool,(uint64_t)address+off,kvtophys(memory+off),false,true) ||
            !map_page_access(&s->pool,alias-WAFFLE_GPU_GLOBAL_BASE+off,kvtophys(memory+off),false,true))
            smmu_owner_stop("dynamic BO partial mapping; retain all pages");
    for(unsigned i=0;i<s->pool.count;i++)clean(s->pool.memory[i]);
    if(!pool_permission_sync(&s->permission_context))smmu_owner_stop("dynamic BO TLB publication incomplete");
    return true;
}
static bool smmu_user_buffer_allocate_map(struct smmu_owner *s,uint64_t address)
{
    struct waffle_gpu_buffer *bo=&s->user_buffer;
    if(bo->memory || !s->child || !s->pool.count || !s->dynamic.memory ||
        !waffle_gpu_user_buffer_valid(address,16384) || !waffle_gmu_owner_can_bind_bo(s->child))return false;
    for(unsigned off=0;off<16384;off+=4096)
        if(!dynamic_bo_vacant(&s->pool,address+off))return false;
    vm_offset_t memory=0;
    if(kmem_alloc(kernel_map,&memory,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return false;
    *bo=(struct waffle_gpu_buffer){.gpu_va=address,.memory=memory,.bytes=16384};
    if(kvtophys(memory)==kvtophys(s->dynamic.memory))smmu_owner_stop("user BO backing overlaps command BO");
    for(unsigned off=0;off<16384;off+=4096)
        if(!map_page_access(&s->pool,address+off,kvtophys(memory+off),false,true))
            smmu_owner_stop("user BO partial mapping; retain all pages");
    for(unsigned i=0;i<s->pool.count;i++)clean(s->pool.memory[i]);
    if(!pool_permission_sync(&s->permission_context))smmu_owner_stop("user BO TLB publication incomplete");
    if(!waffle_gmu_owner_bind_user_buffer(s->child,bo))return false;
    log_line("waffle-iommu: USER_BO published VA=%llx pages=4 lower39=1 unprivileged=1\n",address);
    return true;
}
static bool smmu_dynamic_bo_bind(struct smmu_owner *s)
{
    if(!smmu_bo_allocate_map(s,&s->dynamic,WAFFLE_GPU_DYNAMIC_ADDRESS) ||
        !waffle_gmu_owner_bind_bo(s->child,&s->dynamic))return false;
    log_line("waffle-iommu: DYNAMIC_BO published after GPU startup VA=%x pages=4 aliases=2 unprivileged=1\n",WAFFLE_GPU_DYNAMIC_ADDRESS);
    if(s->compute_image==13)return true; /* General BOs are allocated by the client. */
    if(s->compute_image==10 || s->compute_image==11 || s->compute_image==12)return smmu_user_buffer_allocate_map(s,WAFFLE_GPU_USER_TEST_VA);
    if(s->compute_image>=7){
        if(!smmu_bo_allocate_map(s,&s->data,WAFFLE_GPU_DATA_ADDRESS) ||
            kvtophys(s->data.memory)==kvtophys(s->dynamic.memory) ||
            !waffle_gmu_owner_bind_data_bo(s->child,&s->data))return false;
        log_line("waffle-iommu: DATA_BO published separately VA=%x pages=4 aliases=2 unprivileged=1\n",WAFFLE_GPU_DATA_ADDRESS);
    }
    return true;
}
struct waffle_smmu_owner {
    struct smmu_owner state;
    vm_offset_t allocation;
    bool exercised;
};
struct waffle_smmu_owner *waffle_smmu_owner_begin(uintptr_t smmu,uint32_t page,
    uint32_t pages,uint32_t contexts,uint32_t matches,unsigned probe)
{
    vm_offset_t allocation=0;uint32_t requested=0;
    if(probe!=94 || !PE_parse_boot_argn("waffle_session",&requested,sizeof(requested)) || requested!=1)
        return NULL;
    if(sizeof(struct waffle_smmu_owner)>PAGE_SIZE || kmem_alloc(kernel_map,&allocation,PAGE_SIZE,
        KMA_KOBJECT|KMA_ZERO|KMA_DATA,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
    struct waffle_smmu_owner *owner=(struct waffle_smmu_owner *)allocation;
    owner->allocation=allocation;
    struct smmu_owner *s=&owner->state;
    *s=(struct smmu_owner){.smmu=smmu,.page=page,.pages=pages,.contexts=contexts,
        .matches=matches,.probe=probe,.safe_free=true};
    bool begun=smmu_owner_begin(s);
    if(!begun || !s->child) {
        if(!smmu_owner_finish(s))smmu_owner_stop("SMMU constructor detach incomplete");
        kmem_free(kernel_map,allocation,PAGE_SIZE);
        return NULL;
    }
    if(s->firmware.pool_permissions_context!=&s->permission_context || !s->firmware.submit_session)
        smmu_owner_stop("invalid SMMU constructor or callback ownership");
    log_line("waffle-iommu: SMMU_OWNER begin returned heap=1 callback_owned=1 child_live=1\n");
    return owner;
}
bool waffle_smmu_owner_exercise(struct waffle_smmu_owner *owner)
{
    if(!owner || !owner->state.child || owner->exercised)return false;
    owner->exercised=true;
    if(owner->state.dynamic_bo && !smmu_dynamic_bo_bind(&owner->state))return false;
    owner->state.gmu_ok=waffle_gmu_owner_exercise(owner->state.child);
    return owner->state.gmu_ok;
}
bool waffle_smmu_owner_copy(struct waffle_smmu_owner *owner,struct waffle_gpu_copy_job *job)
{
    if(job)job->fence=0;
    if(!owner || !owner->state.child || !job)return false;
    if(!owner->exercised){
        owner->exercised=true;
        if(owner->state.dynamic_bo && !smmu_dynamic_bo_bind(&owner->state))return false;
        owner->state.gmu_ok=true;
    }
    if(!owner->state.gmu_ok)return false;
    bool ok=waffle_gmu_owner_copy(owner->state.child,job);
    owner->state.gmu_ok=owner->state.gmu_ok && ok;
    return ok;
}
bool waffle_smmu_owner_buffers(struct waffle_smmu_owner *owner,struct waffle_gpu_buffer buffers[2])
{
    if(!owner || !owner->state.child || (owner->state.compute_image!=11 && owner->state.compute_image!=12))return false;
    if(!owner->exercised){
        owner->exercised=true;
        owner->state.gmu_ok=owner->state.dynamic_bo && smmu_dynamic_bo_bind(&owner->state);
    }
    return owner->state.gmu_ok && waffle_gmu_owner_buffers(owner->state.child,buffers);
}
struct waffle_gpu_memory *waffle_smmu_owner_memory_new(struct waffle_smmu_owner *owner,uint64_t bytes,uint32_t flags)
{
    if(!owner || !owner->state.child || owner->state.compute_image!=13)return NULL;
    if(!owner->exercised){
        owner->exercised=true;
        owner->state.gmu_ok=owner->state.dynamic_bo && smmu_dynamic_bo_bind(&owner->state);
    }
    return owner->state.gmu_ok?smmu_registry_new(&owner->state,bytes,flags):NULL;
}
struct waffle_gpu_memory *waffle_smmu_owner_memory_adopt(struct waffle_smmu_owner *owner,struct waffle_gpu_memory *prepared)
{
    if(!owner || !owner->state.child || owner->state.compute_image!=13 || !prepared)return NULL;
    if(!owner->exercised){
        owner->exercised=true;
        owner->state.gmu_ok=owner->state.dynamic_bo && smmu_dynamic_bo_bind(&owner->state);
    }
    return owner->state.gmu_ok?smmu_registry_adopt(&owner->state,prepared):NULL;
}
bool waffle_smmu_owner_memory_reclaim(struct waffle_smmu_owner *owner,struct waffle_gpu_memory *bo,bool cpu_unmapped)
{
    if(!owner || !owner->exercised || !owner->state.gmu_ok || !bo)return false;
    struct smmu_owner *s=&owner->state;
    unsigned index=0;
    for(unsigned i=0;i<s->registry.count;i++)if(bo==&s->registry.buffers[i])index=bo->serial;
    if(!index)return false;
    uint64_t va=bo->gpu_va;uint32_t bytes=bo->allocation_bytes;
    bool ok=smmu_registry_reclaim(s,bo,cpu_unmapped);
    if(ok)log_line("waffle-iommu: GENERAL_BO reclaimed index=%u VA=%llx bytes=%u CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used=%u\n",index,va,bytes,s->registry.used);
    else log_line("waffle-iommu: GENERAL_BO reclaim_refused index=%u poisoned=%u backing_retained=1\n",index,s->registry.poisoned);
    return ok;
}
bool waffle_smmu_owner_submit(struct waffle_smmu_owner *owner,struct waffle_gpu_submit_job *job)
{
    if(job)job->fence=0;
    if(!owner || !job || !job->commands || !job->count || job->count>WAFFLE_GPU_SUBMIT_COMMANDS ||
       !owner->state.child || owner->state.compute_image!=13 || !owner->state.gmu_ok || owner->state.registry.poisoned)return false;
    for(unsigned c=0;c<job->count;c++){
        bool owned=false;
        for(unsigned i=0;i<owner->state.registry.count;i++)if(job->commands[c].buffer==&owner->state.registry.buffers[i])owned=true;
        if(!owned || !waffle_gpu_command_valid(&job->commands[c]))return false;
    }
    bool ok=waffle_gmu_owner_submit(owner->state.child,job);
    owner->state.gmu_ok=owner->state.gmu_ok && ok;return ok;
}
bool waffle_smmu_owner_end(struct waffle_smmu_owner *owner)
{
    if(!owner)return false;
    struct smmu_owner *s=&owner->state;
    if(!s->child || !s->firmware.submit_session)
        smmu_owner_stop("GMU child state lost before parent end");
    bool stopped=waffle_gmu_owner_end(s->child);
    s->child=NULL;s->gmu_ok=s->gmu_ok && stopped;
    smmu_owner_complete(s);
    if(!smmu_owner_finish(s))smmu_owner_stop("SMMU detach incomplete; cannot free owner");
    bool ok=s->gmu_ok;
    vm_offset_t allocation=owner->allocation;
    kmem_free(kernel_map,allocation,PAGE_SIZE);
    log_line("waffle-iommu: SMMU_OWNER released after child stop and context detach\n");
    return ok;
}
void waffle_smmu_probe(vm_offset_t smmu,uint32_t page,uint32_t pages,
    uint32_t contexts,uint32_t matches,unsigned probe)
{
    uint32_t requested=0;
    if(PE_parse_boot_argn("waffle_session",&requested,sizeof(requested)) && requested==1) {
        struct waffle_smmu_owner *owner=waffle_smmu_owner_begin(smmu,page,pages,contexts,matches,probe);
        if(owner){(void)waffle_smmu_owner_exercise(owner);(void)waffle_smmu_owner_end(owner);}
        return;
    }
    struct smmu_owner s={.smmu=smmu,.page=page,.pages=pages,.contexts=contexts,
        .matches=matches,.probe=probe,.safe_free=true};
    (void)smmu_owner_begin(&s);
    smmu_owner_complete(&s);
    (void)smmu_owner_finish(&s);
}

static void secure_context_stop(const char *reason)
{
    log_line("waffle-gmu: REBOOT REQUIRED: %s; retain protected context pages\n",reason);
    loader_return();
    for (;;) __asm__ volatile("wfi");
}
static bool gpu_secure_context_probe(vm_offset_t smmu,unsigned page,unsigned pages,
    unsigned contexts,unsigned matches,vm_offset_t qtb)
{
    vm_offset_t gmu=ml_io_map(WAFFLE_GMU_BASE,WAFFLE_GMU_SIZE);
    vm_offset_t cc=ml_io_map(WAFFLE_GPUCC_BASE,WAFFLE_GPUCC_SIZE);
    if (!gmu || !cc || !(r32(gmu,WAFFLE_GMU_SYSRESET)&1) ||
        (r32(cc,WAFFLE_GPU_GX_GDSCR)&(1u<<31))) {
        log_line("waffle-iommu: protected context requires CM3 reset and GXoff\n");return false;
    }
    struct table_pool pool={0};
    struct gpu_context context={0};
    vm_offset_t target=0;
    uint64_t target_pa=0;
    bool shared=false,locked=false,ok=false;
    if (kmem_alloc(kernel_map,&target,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) return false;
    target_pa=kvtophys(target);
    if (!new_table(&pool)) goto done;
    for (unsigned offset=0;offset<PAGE_SIZE;offset+=4096)
        if (!map_page(&pool,0x90000000ULL+offset,target_pa+offset,false)) goto done;
    for (unsigned i=0;i<pool.count;++i) {
        for (vm_offset_t p=pool.memory[i];p<pool.memory[i]+PAGE_SIZE;p+=64)
            __asm__ volatile("dc cvac, %0"::"r"(p):"memory");
    }
    for (vm_offset_t p=target;p<target+PAGE_SIZE;p+=64)
        __asm__ volatile("dc civac, %0"::"r"(p):"memory");
    barrier();
    if (!waffle_scm_assign_pages(pool.phys,pool.count,WAFFLE_SCM_SHARE_TABLE)) goto done;
    shared=true;
    if (!waffle_scm_assign_pages(&target_pa,1,WAFFLE_SCM_LOCK_DATA)) goto done;
    locked=true;
    if (gpu_context_begin_at(&context,smmu,page,pages,contexts,matches,pool.phys[0],2,2,2)) {
        ok=translate_page(qtb,context.cb,0x90000000,target_pa,2) &&
            translate_page(qtb,context.cb,0x90000000+PAGE_SIZE-4096,target_pa+PAGE_SIZE-4096,2);
        log_line("waffle-iommu: GPU protected SID2 translation=%u\n",ok);
    }
done:
    if (!gpu_context_end(&context)) secure_context_stop("protected context TLB sync failed");
    if (locked && !waffle_scm_assign_pages(&target_pa,1,WAFFLE_SCM_RECLAIM_DATA))
        secure_context_stop("cannot reclaim protected data");
    if (shared && !waffle_scm_assign_pages(pool.phys,pool.count,WAFFLE_SCM_RECLAIM_TABLE))
        secure_context_stop("cannot reclaim protected tables");
    for (unsigned i=0;i<pool.count;++i) kmem_free(kernel_map,pool.memory[i],PAGE_SIZE);
    kmem_free(kernel_map,target,PAGE_SIZE);
    log_line("waffle-iommu: protected context result=%u resources_returned=1\n",ok);
    return ok;
}

/* Persistent protected arena for the HWSCHED handshake. It is never mapped
 * through the common GMU/user root and remains owned until CM3 has stopped. */
static void protected_pool_release(struct protected_gpu_pool *p)
{
    if (!p) return;
    if (!gpu_context_end(&p->context)) secure_context_stop("protected pool TLB sync failed");
    while (p->owned) {
        unsigned count=p->owned>32?32:p->owned;
        if (!waffle_scm_assign_pages(p->phys+p->owned-count,count,WAFFLE_SCM_RECLAIM_DATA))
            secure_context_stop("protected pool data reclaim failed");
        p->owned-=count;
    }
    if (p->shared && !waffle_scm_assign_pages(p->tables.phys,p->tables.count,WAFFLE_SCM_RECLAIM_TABLE))
        secure_context_stop("protected pool table reclaim failed");
    if (p->data) {
        bzero((void *)p->data,PROTECTED_POOL_BYTES);
        kmem_free(kernel_map,p->data,PROTECTED_POOL_BYTES);
    }
    for (unsigned i=0;i<p->tables.count;++i) kmem_free(kernel_map,p->tables.memory[i],PAGE_SIZE);
    kmem_free(kernel_map,(vm_offset_t)p,PAGE_SIZE);
    log_line("waffle-iommu: protected pool released, all pages HLOS-owned\n");
}
static struct protected_gpu_pool *protected_pool_prepare(vm_offset_t smmu,unsigned page,
    unsigned pages,unsigned contexts,unsigned matches,vm_offset_t qtb,uint64_t address)
{
    if (address!=PROTECTED_POOL_ADDRESS && address!=0x100000000ULL) return NULL;
    vm_offset_t memory=0;
    if (PAGE_SIZE!=16384 || sizeof(struct protected_gpu_pool)>PAGE_SIZE ||
        kmem_alloc(kernel_map,&memory,PAGE_SIZE,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS) return NULL;
    struct protected_gpu_pool *p=(struct protected_gpu_pool *)memory;
    p->address=address;
    if (kmem_alloc(kernel_map,&p->data,PROTECTED_POOL_BYTES,KMA_KOBJECT|KMA_ZERO|KMA_DATA,
            VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS || !new_table(&p->tables)) goto failed;
    for (unsigned i=0;i<PROTECTED_POOL_BYTES/16384;++i) {
        p->phys[i]=kvtophys(p->data+i*16384);
        if (!p->phys[i] || (p->phys[i]&16383) || p->phys[i]>=(1ULL<<36)) goto failed;
    }
    for (unsigned offset=0;offset<PROTECTED_POOL_BYTES;offset+=4096)
        if (!map_page(&p->tables,p->address+offset,
                kvtophys(p->data+offset),false)) goto failed;
    for (unsigned i=0;i<p->tables.count;++i)
        for (vm_offset_t a=p->tables.memory[i];a<p->tables.memory[i]+PAGE_SIZE;a+=64)
            __asm__ volatile("dc cvac, %0"::"r"(a):"memory");
    for (vm_offset_t a=p->data;a<p->data+PROTECTED_POOL_BYTES;a+=64)
        __asm__ volatile("dc civac, %0"::"r"(a):"memory");
    barrier();
    if (!waffle_scm_assign_pages(p->tables.phys,p->tables.count,WAFFLE_SCM_SHARE_TABLE)) goto failed;
    p->shared=true;
    while (p->owned<PROTECTED_POOL_BYTES/16384) {
        unsigned count=PROTECTED_POOL_BYTES/16384-p->owned;
        if (count>32) count=32;
        if (!waffle_scm_assign_pages(p->phys+p->owned,count,WAFFLE_SCM_LOCK_DATA)) goto failed;
        p->owned+=count;
    }
    if (!gpu_context_begin_at(&p->context,smmu,page,pages,contexts,matches,p->tables.phys[0],2,2,2)) goto failed;
    if (!translate_page(qtb,p->context.cb,p->address,p->phys[0],2) ||
        !translate_page(qtb,p->context.cb,p->address+PROTECTED_POOL_BYTES-4096,
            p->phys[PROTECTED_POOL_BYTES/16384-1]+12288,2)) goto failed;
    log_line("waffle-iommu: protected pool ready VA=%llx bytes=%u pages=%u SID2\n",
        (unsigned long long)p->address,PROTECTED_POOL_BYTES,p->owned);
    return p;
failed:
    protected_pool_release(p);
    return NULL;
}
