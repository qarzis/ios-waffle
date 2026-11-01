#ifndef WAFFLE_GPU_PRESENT_H
#define WAFFLE_GPU_PRESENT_H
#include <stdint.h>
#include <stdbool.h>
#define WAFFLE_PRESENT_SIDE 256u
#define WAFFLE_PRESENT_WORDS (WAFFLE_PRESENT_SIDE*WAFFLE_PRESENT_SIDE)
#define WAFFLE_PRESENT_BYTES (WAFFLE_PRESENT_WORDS*4u)
/* Only the loader-verified PJD110 BGRA boot framebuffer is accepted. */
static inline bool waffle_present_valid(uintptr_t base,uint64_t physical,unsigned width,unsigned height,unsigned depth,unsigned stride)
{
    uint64_t bytes=(uint64_t)stride*height;
    return base && !(base&3) && width==1440 && height==3168 && depth==32 &&
        stride>=width*4 && stride<=16384 && !(stride&3) &&
        physical>=0xd5100000ULL && physical<0xd7c00000ULL &&
        bytes<=0xd7c00000ULL-physical && base<=UINTPTR_MAX-bytes;
}
static inline uint32_t waffle_present_bgra(uint32_t rgba)
{
    return (rgba&0xff00ff00u)|((rgba&0xffu)<<16)|((rgba>>16)&0xffu);
}
/* Operations: 0=save+draw; 1=check draw; 2=restore; 3=check restore.
 * Caller supplies a 65536-word backup, validated framebuffer and barriers. */
static inline unsigned waffle_present_transfer(volatile uint32_t *fb,unsigned stride,const volatile uint32_t *pixels,uint32_t *backup,unsigned operation)
{
    unsigned wrong=0;
    for(unsigned y=0;y<256;y++)for(unsigned x=0;x<256;x++) {
        unsigned i=y*256+x;
        volatile uint32_t *at=fb+(1456+y)*(stride/4)+592+x;
        if(operation==0){backup[i]=*at;*at=waffle_present_bgra(pixels[(y/16)*16+x/16]);}
        else if(operation==1){if(*at!=waffle_present_bgra(pixels[(y/16)*16+x/16]))++wrong;}
        else if(operation==2)*at=backup[i];
        else if(operation==3 && *at!=backup[i])++wrong;
    }
    return wrong;
}
#endif
