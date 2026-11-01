#ifndef WAFFLE_GPU_WRITEBACK_H
#define WAFFLE_GPU_WRITEBACK_H
#include "waffle_gpu_va.h"
#define WAFFLE_GPU_WRITEBACK_ADDRESS 0x80074000u
#define WAFFLE_GPU_WRITEBACK_BYTES 16384u
#define WAFFLE_GPU_WRITEBACK_OFFSET 256u
#define WAFFLE_GPU_DYNAMIC_ADDRESS 0x80078000u
/* Native user command buffers need AP_UNPRIV. Limit the diagnostic exception
 * to this dedicated region; other writable firmware/restore buffers stay PRIV. */
static inline bool waffle_diagnostic_unprivileged(uint32_t address,bool gpu_only,bool readonly)
{
    return gpu_only && (readonly || address==WAFFLE_GPU_WRITEBACK_ADDRESS);
}
static const uint32_t waffle_writeback_values[]={0x57414646u,0x4c454750u,0x13579bdfu,0x2468ace0u};
/* One independent GPU result, never populated with expected values by CPU. */
static inline unsigned waffle_writeback_packet(uint32_t *out,unsigned capacity,
    unsigned seq,uint64_t va)
{
    if(!out || capacity<9 || !seq || seq>4095 || (va&3) ||
        !waffle_gpu_va_valid(va) || !waffle_gpu_va_valid(va+15) || va+15<va)return 0;
    out[0]=(seq<<20)|(9u<<8)|131u;
    out[1]=0x703d8006u; /* Native CP_MEM_WRITE, six payload dwords. */
    out[2]=(uint32_t)va;out[3]=(uint32_t)(va>>32);
    for(unsigned i=0;i<4;++i)out[4+i]=waffle_writeback_values[i];
    out[8]=0x70928000u; /* Native CP_WAIT_MEM_WRITES, zero payload. */
    return 9;
}
/* Native CP_INDIRECT_BUFFER_PFE(0x3f), address and size in dwords. */
static inline unsigned waffle_writeback_ib_packet(uint32_t *out,unsigned capacity,
    unsigned seq,uint64_t va,unsigned words)
{
    if(!out || capacity<5 || !seq || seq>4095 || (va&3) || !words || words>0xfffff ||
        !waffle_gpu_va_valid(va) || !waffle_gpu_va_valid(va+(uint64_t)words*4-1) ||
        va+(uint64_t)words*4<va)return 0;
    out[0]=(seq<<20)|(5u<<8)|131u;out[1]=0x70bf8003u;
    out[2]=(uint32_t)va;out[3]=(uint32_t)(va>>32);out[4]=words;
    return 5;
}
static inline uint32_t waffle_writeback_initial(unsigned index)
{
    return index==63 || index==68 ? 0xc0decafeu : 0;
}
static inline uint32_t waffle_writeback_expected(unsigned index)
{
    return index>=64 && index<68 ? waffle_writeback_values[index-64] : waffle_writeback_initial(index);
}
#endif
