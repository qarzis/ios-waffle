/* Pineapple debug mux/4.8MHz counter, from pinned debugcc-pineapple.c and
 * clk-debug.c. Diagnostic only: caller owns powered CX/GX and config clocks.
 * Does not change GPU frequency. Every poll is bounded and fields restored.
 */
#ifndef WAFFLE_GPU_MEASURE_H
#define WAFFLE_GPU_MEASURE_H
#include <stdint.h>
#include <stdbool.h>
struct waffle_measure_io {
    void *context;
    uint32_t (*read)(void *,unsigned,uint32_t);
    void (*write)(void *,unsigned,uint32_t,uint32_t);
    void (*delay_us)(void *,unsigned);
};
struct waffle_measure_result {
    uint32_t short_count,full_count;
    uint64_t hz;
    bool complete,restored;
};
static inline void waffle_measure_update(const struct waffle_measure_io *io,
    unsigned bank,uint32_t off,uint32_t mask,uint32_t value)
{
    uint32_t old=io->read(io->context,bank,off);
    io->write(io->context,bank,off,(old&~mask)|(value&mask));
}
static inline bool waffle_measure_sample(const struct waffle_measure_io *io,
    uint32_t ticks,uint32_t *count)
{
    waffle_measure_update(io,0,0x62048,1u<<20,0);
    waffle_measure_update(io,0,0x62048,1u<<21,1u<<21);
    io->delay_us(io->context,1);
    waffle_measure_update(io,0,0x62048,1u<<21,0);
    waffle_measure_update(io,0,0x62048,0xfffffu,ticks);
    waffle_measure_update(io,0,0x62048,1u<<20,1u<<20);
    bool done=false;
    for(unsigned us=0;us<40000;us+=10) {
        if(io->read(io->context,0,0x6204c)&(1u<<25)){done=true;break;}
        io->delay_us(io->context,10);
    }
    waffle_measure_update(io,0,0x62048,1u<<20,0);
    *count=io->read(io->context,0,0x6204c)&0x1ffffffu;
    return done;
}
static inline bool waffle_measure_clock(const struct waffle_measure_io *io,
    unsigned selector,struct waffle_measure_result *result)
{
    if(!io || !io->read || !io->write || !io->delay_us || !result ||
        (selector!=0xf && selector!=0x1f)) return false;
    *result=(struct waffle_measure_result){0};
    /* Refuse a measurement already owned by another client. */
    if(io->read(io->context,0,0x62048)&((1u<<20)|(1u<<21))) return false;
    static const struct {unsigned bank;uint32_t off,mask;} regs[]={
        {0,0x62024,0x3ff},{0,0x62000,0xf},{0,0x62004,1},
        {0,0x62008,1},{0,0x62048,0x3fffff},
        {1,0x9564,0xff},{1,0x9270,0xf},{1,0x9274,1}
    };
    uint32_t saved[8];
    for(unsigned i=0;i<8;++i)saved[i]=io->read(io->context,regs[i].bank,regs[i].off);
    waffle_measure_update(io,1,0x9564,0xff,selector);
    waffle_measure_update(io,1,0x9270,0xf,1); /* GPU mux /2 */
    waffle_measure_update(io,0,0x62024,0x3ff,0x18d); /* GPU debug mux */
    waffle_measure_update(io,0,0x62000,0xf,1); /* GCC mux /2 */
    waffle_measure_update(io,1,0x9274,1,1);
    waffle_measure_update(io,0,0x62004,1,1);
    waffle_measure_update(io,0,0x62008,1,1);
    bool configured=(io->read(io->context,1,0x9564)&0xff)==selector &&
        (io->read(io->context,0,0x62024)&0x3ff)==0x18d &&
        (io->read(io->context,1,0x9270)&0xf)==1 &&
        (io->read(io->context,0,0x62000)&0xf)==1 &&
        (io->read(io->context,1,0x9274)&1) &&
        (io->read(io->context,0,0x62004)&1) &&
        (io->read(io->context,0,0x62008)&1);
    if(configured) result->complete=waffle_measure_sample(io,0x1000,&result->short_count) &&
        waffle_measure_sample(io,0x20000,&result->full_count);
    if(result->complete && result->full_count!=result->short_count)
        result->hz=(((uint64_t)result->full_count*10+15)*4800000/
            (0x20000u*10+35))*4;
    result->restored=true;
    for(unsigned n=8;n>0;--n) {
        unsigned i=n-1;
        waffle_measure_update(io,regs[i].bank,regs[i].off,regs[i].mask,saved[i]);
        if((io->read(io->context,regs[i].bank,regs[i].off)&regs[i].mask)!=
            (saved[i]&regs[i].mask)) result->restored=false;
    }
    return result->complete && result->restored;
}
#endif
