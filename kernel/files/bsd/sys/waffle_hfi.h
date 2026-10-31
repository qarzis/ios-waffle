/* Bounded Gen7 HFI ring operations. Caller supplies uncached shared memory
 * and ordering barriers; firmware owns the opposite queue index. */
#ifndef WAFFLE_HFI_H
#define WAFFLE_HFI_H
#include <stdint.h>
#include <stdbool.h>
#include "waffle_gpu_va.h"
#define WAFFLE_HFI_RING_WORDS 1024u
/* Captured twice from native PJD110 H2F_MSG_ACD_TBL (ID7, 276 bytes).
 * Encoding only: native first notifies AOP of ACD state through its mailbox.
 * Do not publish this packet from the port until that prerequisite is ported. */
static inline unsigned waffle_hfi_acd_table_packet(uint32_t *out,unsigned capacity,
    unsigned sequence)
{
    if (!out || capacity<69 || !sequence || sequence>4095) return 0;
    static const uint32_t levels[12]={
        0xc82f5ffdu,0xc82c5ffdu,0xc02e5ffdu,0xc02d5ffdu,
        0xc02a5ffdu,0x882c5ffdu,0x882a5ffdu,0x882a5ffdu,
        0x882a5ffdu,0x882a5ffdu,0x882a5ffdu,0x882a5ffdu
    };
    for (unsigned i=0;i<69;++i) out[i]=0;
    out[0]=(sequence<<20)|(69u<<8)|7u;
    out[1]=1;out[2]=0x1ffe;out[3]=1;out[4]=12;
    for (unsigned i=0;i<12;++i) out[5+i]=levels[i];
    return 69;
}
/* Native Gen7.9 HWSCHED cp_init: HFI ISSUE_CMD_RAW131 contains the ten
 * gen7_cp_init_cmds words. DMS/concurrent binning remain disabled.
 * Encoding only: caller must prepare the persistent normal GPU restore list,
 * complete native gen7_start, and keep all mappings alive through CM3 stop.
 * Full init is experimental probe33; first-command isolation is probe35. */
static inline unsigned waffle_hfi_cp_init_packet(uint32_t *out, unsigned capacity,
    unsigned sequence, uint64_t restore_address)
{
    if (!out || capacity<11 || !sequence || sequence>4095 ||
        !restore_address || (restore_address&4095) || !waffle_gpu_va_valid(restore_address))
        return 0;
    const uint32_t words[11]={
        (sequence<<20)|(11u<<8)|131u,
        0x70970001u,1u<<27, /* CP_THREAD_CONTROL, one payload word */
        0x70c80007u,0x94bu,3u,0x20000000u,2u, /* CP_ME_INIT, seven payload words */
        (uint32_t)restore_address,(uint32_t)(restore_address>>32),1u<<31
    };
    for (unsigned i=0;i<11;++i) out[i]=words[i];
    return 11;
}
/* Exact first PM4 command of native gen7_cp_init_cmds, in a valid short RAW
 * envelope. No ME_INIT payload or restore-list access is requested. Native
 * RAW also carries three-word HFI packets (send_switch_to_unsecure); this is
 * only a diagnostic split of the native CP-init stream, not a complete init. */
static inline unsigned waffle_hfi_cp_thread_packet(uint32_t *out,unsigned capacity,unsigned sequence)
{
    if (!out || capacity<3 || !sequence || sequence>4095) return 0;
    out[0]=(sequence<<20)|(3u<<8)|131u;
    out[1]=0x70970001u;out[2]=1u<<27;
    return 3;
}
/* Pinned OnePlus adreno_hfi.h: legacy request has8descriptor words;
 * version1 adds packed VA/size alignment exponents. No allocation implied. */
struct waffle_hfi_mem_request {
    uint64_t gpu_address;
    uint32_t flags, kind, host_handle, gmu_handle, gmu_address, size, alignment;
};
static inline int waffle_hfi_mem_request_decode(const uint32_t *p, unsigned words,
    struct waffle_hfi_mem_request *out)
{
    if (words < 2 || (p[0]&255)!=20 || ((p[0]>>16)&15)!=0 ||
        ((p[0]>>8)&255)!=words || p[1]>1 || words!=(p[1]?11u:10u)) return 0;
    struct waffle_hfi_mem_request r = {
        (uint64_t)p[2]|((uint64_t)p[3]<<32),p[4],p[5],p[6],p[7],p[8],p[9],p[1]?p[10]:0
    };
    if (!r.size || r.kind>=26 || (r.flags&~0x13ffu) ||
        (r.alignment&0xffff0000u) || (r.alignment&255)>31 ||
        ((r.alignment>>8)&255)>31) return 0;
    *out=r;
    return 1;
}
/* Bring-up only: pre-mapped privileged normal-NC RAM shared by both contexts.
 * Separate GPU/GMU permissions and secure/MMIO/cacheable allocations require
 * separate backends. No live page-table edits or CPU access to firmware data. */
struct waffle_hfi_allocation {
    struct waffle_hfi_mem_request request;
    uint64_t address;
};
struct waffle_hfi_pool {
    uint64_t base;
    uint32_t size, used, count;
    struct waffle_hfi_allocation allocations[32];
};
static inline int waffle_hfi_pool_reserve_impl(struct waffle_hfi_pool *pool,
    const struct waffle_hfi_mem_request *r, struct waffle_hfi_mem_request *reply,bool secure)
{
    if (!r->size || r->kind>=26 || (r->flags&~0x13ffu) ||
        (r->alignment&0xffff0000u) || (r->alignment&255)>31 ||
        ((r->alignment>>8)&255)>31 || r->gpu_address || r->gmu_address || r->host_handle)
        return -1;
    if (secure) {
        if (r->flags!=0x1007 || r->kind!=5) return -2;
    } else if ((r->flags&((1u<<12)|(1u<<7))) || r->kind==5 ||
            (r->kind>=11 && r->kind<=13) || r->kind==19 || r->kind==20 || r->kind==23)
            return -2;
    uint64_t limit=secure ? (1ULL<<39) : (1ULL<<32);
    if (!(r->flags&9u) || pool->count>32 || pool->used>pool->size ||
        pool->base>limit || pool->size>limit-pool->base) return -1;
    uint64_t address=0;
    for (unsigned i=0;i<pool->count;++i) {
        struct waffle_hfi_allocation *a=&pool->allocations[i];
        if (a->request.kind!=r->kind || a->request.gmu_handle!=r->gmu_handle) continue;
        if (a->request.flags!=r->flags || a->request.size!=r->size ||
            a->request.alignment!=r->alignment) return -3;
        address=a->address;
        goto found;
    }
    if (pool->count==32) return -4;
    unsigned va_exp=r->alignment&255, size_exp=(r->alignment>>8)&255;
    uint64_t va_align=1ULL<<(va_exp<12?12:va_exp);
    uint64_t size_align=1ULL<<(size_exp<12?12:size_exp);
    uint64_t start=((uint64_t)pool->base+pool->used+va_align-1)&~(va_align-1);
    uint64_t length=((uint64_t)r->size+size_align-1)&~(size_align-1);
    uint64_t end=start+length;
    if (start<pool->base || end>(uint64_t)pool->base+pool->size || end>limit) return -4;
    address=start;
    pool->allocations[pool->count].request=*r;
    pool->allocations[pool->count++].address=address;
    pool->used=(uint32_t)(end-pool->base);
found:
    *reply=*r;
    reply->gpu_address=(r->flags&1u)?address:0;
    reply->gmu_address=(r->flags&8u)?(uint32_t)address:0;
    reply->host_handle=r->gmu_handle;
    return 0;
}
static inline int waffle_hfi_pool_reserve(struct waffle_hfi_pool *pool,
    const struct waffle_hfi_mem_request *r,struct waffle_hfi_mem_request *reply)
{
    return waffle_hfi_pool_reserve_impl(pool,r,reply,false);
}
static inline int waffle_hfi_pool_reserve_secure(struct waffle_hfi_pool *pool,
    const struct waffle_hfi_mem_request *r,struct waffle_hfi_mem_request *reply)
{
    return waffle_hfi_pool_reserve_impl(pool,r,reply,true);
}
static inline int waffle_hfi_indices(volatile uint32_t *q, uint32_t *r, uint32_t *w)
{
    *r = q[10]; *w = q[11];
    return q[0] == 1 && q[3] == WAFFLE_HFI_RING_WORDS &&
        *r < WAFFLE_HFI_RING_WORDS && *w < WAFFLE_HFI_RING_WORDS &&
        !((*r | *w) & 3);
}
/* Does not publish write_index: caller must order packet stores first. */
static inline int waffle_hfi_write(volatile uint32_t *q, volatile uint32_t *ring,
    const uint32_t *packet, unsigned count, uint32_t *next)
{
    uint32_t r, w;
    if (!count || count > 255 || !waffle_hfi_indices(q, &r, &w) ||
        ((packet[0] >> 8) & 255) != count) return -1;
    unsigned aligned = (count + 3) & ~3u;
    unsigned free_words = w >= r ? 1024 - (w - r) : r - w;
    if (free_words <= aligned) return -2;
    for (unsigned i = 0; i < aligned; ++i)
        ring[(w + i) & 1023] = i < count ? packet[i] : 0xfafafafa;
    *next = (w + aligned) & 1023;
    return (int)count;
}
/* Does not publish read_index: caller must order packet loads first. */
static inline int waffle_hfi_read(volatile uint32_t *q, volatile uint32_t *ring,
    uint32_t *packet, unsigned capacity, uint32_t *next)
{
    uint32_t r, w;
    if (!waffle_hfi_indices(q, &r, &w)) return -1;
    if (r == w) return 0;
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    unsigned count = (ring[r] >> 8) & 255;
    unsigned aligned = (count + 3) & ~3u;
    if (!count || count > capacity || aligned > ((w - r) & 1023)) return -2;
    for (unsigned i = 0; i < count; ++i) packet[i] = ring[(r + i) & 1023];
    *next = (r + aligned) & 1023;
    return (int)count;
}
#endif
