/* Pinned OnePlus SCM64 MP_ASSIGN wire format. Metadata stays HLOS-owned. */
#ifndef WAFFLE_SCM_H
#define WAFFLE_SCM_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_SCM_ASSIGN_FUNCTION 0x42000c16u
#define WAFFLE_SCM_ASSIGN_ARGINFO 0x1117u
#define WAFFLE_SCM_METADATA_SIZE 16384u
enum waffle_scm_assignment {
    WAFFLE_SCM_LOCK_DATA, WAFFLE_SCM_RECLAIM_DATA,
    WAFFLE_SCM_SHARE_TABLE, WAFFLE_SCM_RECLAIM_TABLE
};
/* Native secure_buffer batches at most32 segments per call.
 * Caller owns whole pages and cleans them before a transfer. Returns false
 * only before submission; uncertain post-submission ownership stops the test. */
bool waffle_scm_gpu_aperture(void);
bool waffle_scm_assign_pages(const uint64_t *,unsigned,unsigned);
static inline void waffle_scm_put32(volatile uint8_t *p,uint32_t value)
{
    for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(value>>(i*8));
}
static inline void waffle_scm_put64(volatile uint8_t *p,uint64_t value)
{
    for (unsigned i=0;i<8;++i) p[i]=(uint8_t)(value>>(i*8));
}
/* Each entry owns a whole16KiB XNU page. Native mem_map_info is16bytes,
 * current_perm_info24bytes. x5 points to seven LE64 extended arguments,
 * starting at argument3 (not4); unused arguments must be zero. */
static inline bool waffle_scm_assign_encode_mode(volatile uint8_t *metadata,
    unsigned bytes,uint64_t metadata_pa,const uint64_t *pages,unsigned count,
    unsigned mode,uint64_t registers[4])
{
    if (mode>WAFFLE_SCM_RECLAIM_TABLE || bytes<WAFFLE_SCM_METADATA_SIZE || !metadata_pa || (metadata_pa&16383) ||
        metadata_pa+16384>(1ULL<<36) || metadata_pa>=(1ULL<<36) || !count || count>256)
        return false;
    for (unsigned i=0;i<count;++i) {
        if (!pages[i] || (pages[i]&16383) || pages[i]>=(1ULL<<36) ||
            pages[i]+16384>(1ULL<<36) || pages[i]==metadata_pa) return false;
        for (unsigned j=0;j<i;++j) if (pages[i]==pages[j]) return false;
    }
    for (unsigned i=0;i<WAFFLE_SCM_METADATA_SIZE;++i) metadata[i]=0;
    for (unsigned i=0;i<count;++i) {
        waffle_scm_put64(metadata+16*i,pages[i]);
        waffle_scm_put64(metadata+16*i+8,16384);
    }
    waffle_scm_put32(metadata+4096,mode==WAFFLE_SCM_RECLAIM_DATA?10:3);
    if (mode==WAFFLE_SCM_RECLAIM_TABLE) waffle_scm_put32(metadata+4100,10);
    waffle_scm_put32(metadata+8192,mode==WAFFLE_SCM_LOCK_DATA?10:3);
    waffle_scm_put32(metadata+8196,(mode==WAFFLE_SCM_RECLAIM_DATA || mode==WAFFLE_SCM_RECLAIM_TABLE)?7:6);
    if (mode==WAFFLE_SCM_SHARE_TABLE) {
        waffle_scm_put32(metadata+8216,10);
        waffle_scm_put32(metadata+8220,4); /* CP_PIXEL may read tables only */
    }
    waffle_scm_put64(metadata+12288,mode==WAFFLE_SCM_RECLAIM_TABLE?8:4);
    waffle_scm_put64(metadata+12296,metadata_pa+8192);
    waffle_scm_put64(metadata+12304,mode==WAFFLE_SCM_SHARE_TABLE?48:24);
    registers[0]=metadata_pa;
    registers[1]=count*16;
    registers[2]=metadata_pa+4096;
    registers[3]=metadata_pa+12288;
    return true;
}
static inline bool waffle_scm_assign_encode(volatile uint8_t *metadata,
    unsigned bytes,uint64_t metadata_pa,const uint64_t *pages,unsigned count,
    bool reclaim,uint64_t registers[4])
{
    return waffle_scm_assign_encode_mode(metadata,bytes,metadata_pa,pages,count,
        reclaim?WAFFLE_SCM_RECLAIM_DATA:WAFFLE_SCM_LOCK_DATA,registers);
}
#endif
