/* AudioReach shared-memory ABI, Linux v6.12 audioreach.c/q6apm.c.
 * Serialization only: does NOT allocate, own, map, cache-clean or hand DMA to DSP.
 * Caller must establish a native SMMU domain before transmitting this packet.
 * Restricted first step: one contiguous 4KiB-aligned region in live-DT audio pool.
 * Unlike GRAPH_OPEN/CLOSE, these commands have NO 16-byte APM command header. */
#ifndef WAFFLE_APM_MEMORY_H
#define WAFFLE_APM_MEMORY_H
#include <stdint.h>
#include <stddef.h>
#define WAFFLE_APM_MEM_MAP 0x0100100cu
#define WAFFLE_APM_MEM_UNMAP 0x0100100du
#define WAFFLE_APM_MEM_MAP_RSP 0x02001001u
static inline size_t
waffle_apm_memory_map(uint32_t *out,size_t capacity,uint32_t token,
                      uint32_t sid,uint32_t iova,uint32_t bytes)
{
 if(!out || capacity<44 || !token || (sid!=0x1001 && sid!=0x1061) ||
    (iova&4095) || (bytes&4095) || !bytes || iova<0x10000000 ||
    (uint64_t)iova+bytes>0x20000000)return 0;
 uint64_t dsp=(uint64_t)iova|((uint64_t)(sid&15)<<32);
 out[0]=(44u<<8)|(6u<<4);out[1]=0x0302;out[2]=1;out[3]=1;
 out[4]=token;out[5]=WAFFLE_APM_MEM_MAP;
 out[6]=(1u<<16)|3u; /* u16 pool=SHMEM8_4K, u16 num_regions=1 */
 out[7]=0; /* physical-address mode, no Linux file descriptor/offset fixup */
 out[8]=(uint32_t)dsp;out[9]=(uint32_t)(dsp>>32);out[10]=bytes;
 return 44;
}
static inline size_t
waffle_apm_memory_unmap(uint32_t *out,size_t capacity,uint32_t token,uint32_t handle)
{
 if(!out || capacity<28 || !token || !handle)return 0;
 out[0]=(28u<<8)|(6u<<4);out[1]=0x0302;out[2]=1;out[3]=1;
 out[4]=token;out[5]=WAFFLE_APM_MEM_UNMAP;out[6]=handle;return 28;
}
#endif
