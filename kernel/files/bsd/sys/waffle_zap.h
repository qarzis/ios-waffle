#ifndef WAFFLE_ZAP_H
#define WAFFLE_ZAP_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
/* Offline decoder only. Signature validation belongs to the native PAS13 service.
 * This does not authenticate, map, load or execute an image. */
struct waffle_zap_image {
    uint32_t header_bytes,hash_offset,hash_bytes;
    uint32_t payload_offset,payload_bytes,memory_bytes,relocation;
};
static inline uint32_t waffle_zap_u32(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool waffle_zap_span(size_t size,uint32_t off,uint32_t bytes)
{
    return off<=size && bytes<=size-off;
}
static inline bool waffle_zap_parse(const uint8_t *data,size_t size,struct waffle_zap_image *out)
{
    if(!data || !out || size<52 || size>0x100000 ||
        data[0]!=0x7f || data[1]!='E' || data[2]!='L' || data[3]!='F' ||
        data[4]!=1 || data[5]!=1 || data[6]!=1 || data[16]!=2 || data[17] ||
        data[18]!=164 || data[19] || waffle_zap_u32(data+20)!=1 ||
        waffle_zap_u32(data+28)!=52 || data[40]!=52 || data[41] ||
        data[42]!=32 || data[43] || data[45]) return false;
    unsigned count=data[44];
    if(count<2 || count>8 || !waffle_zap_span(size,52,count*32)) return false;
    const uint8_t *first=data+52;
    struct waffle_zap_image p={0};
    p.header_bytes=waffle_zap_u32(first+16);
    if(waffle_zap_u32(first)!=0 || waffle_zap_u32(first+4)!=0 ||
        p.header_bytes<52+count*32 || p.header_bytes>4096 || p.header_bytes>size) return false;
    unsigned loads=0,hashes=0;
    uint32_t code_end=0;
    for(unsigned i=1;i<count;i++) {
        const uint8_t *h=data+52+32*i;
        uint32_t type=waffle_zap_u32(h),off=waffle_zap_u32(h+4),
            pa=waffle_zap_u32(h+12),bytes=waffle_zap_u32(h+16),
            mem=waffle_zap_u32(h+20),flags=waffle_zap_u32(h+24);
        if((flags&0x07000000u)==0x02000000u) {
            if(type || ++hashes!=1 || !bytes || !waffle_zap_span(size,off,bytes) ||
                p.header_bytes+bytes>16384 || off<p.header_bytes) return false;
            p.hash_offset=off;p.hash_bytes=bytes;
        } else if(type==1) {
            if(++loads!=1 || flags!=0x08000007u || !bytes || bytes>mem ||
                !mem || mem>8192 || (pa&4095) || pa>UINT32_MAX-mem ||
                !waffle_zap_span(size,off,bytes) || off<p.header_bytes) return false;
            code_end=pa+mem;
            p.payload_offset=off;p.payload_bytes=bytes;p.memory_bytes=(mem+4095)&~4095u;p.relocation=pa;
        } else return false;
    }
    uint32_t entry=waffle_zap_u32(data+24);
    if(loads!=1 || hashes!=1 || entry<p.relocation || entry>=code_end ||
        (p.payload_offset<p.hash_offset+p.hash_bytes && p.hash_offset<p.payload_offset+p.payload_bytes)) return false;
    *out=p;return true;
}
#endif
