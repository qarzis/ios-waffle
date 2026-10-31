/* Native KGSL PAS13 sequence. Signature authentication is performed by PAS. */
#ifndef WAFFLE_ZAP_LOAD_H
#define WAFFLE_ZAP_LOAD_H
#include "waffle_zap.h"
#define WAFFLE_ZAP_RESERVED_BASE 0x9b09a000ULL
#define WAFFLE_ZAP_RESERVED_SIZE 8192u
struct waffle_zap_io {
    void *context;
    bool (*call)(void *,uint32_t,uint32_t,const uint64_t *,uint64_t *);
    bool (*copy_payload)(void *,const uint8_t *,unsigned,unsigned);
};
struct waffle_zap_state {unsigned stage;bool retain,authenticated;};
/* Once INIT_IMAGE may have been observed, callers retain all mapped memory on
 * failure, including unsupported WAITQ returns, until a normal Android reset.
 * Never attempt an invented PAS rollback on an unknown secure-world state. */
static inline bool waffle_zap_load(const struct waffle_zap_io *io,
    const uint8_t *image,size_t size,uint64_t metadata_pa,struct waffle_zap_state *state)
{
    struct waffle_zap_image p;
    if(!state)return false;
    *state=(struct waffle_zap_state){0};
    if(!io || !io->call || !io->copy_payload ||
        !metadata_pa || (metadata_pa&16383) || metadata_pa>=(1ULL<<36) ||
        !waffle_zap_parse(image,size,&p) || p.memory_bytes>WAFFLE_ZAP_RESERVED_SIZE)
        return false;
    const uint32_t commands[]={7,1,2,5};
    for(unsigned i=0;i<4;++i) {
        uint64_t args[4]={13,0,0,0},answer=0;
        uint32_t arginfo=1;
        if(i==1){args[1]=metadata_pa;arginfo=0x82;state->retain=true;}
        if(i==2){args[1]=WAFFLE_ZAP_RESERVED_BASE;args[2]=p.memory_bytes;arginfo=3;}
        state->stage=i+1;
        if(!io->call(io->context,0x42000200|commands[i],arginfo,args,&answer) ||
            (i==0 ? !answer : answer!=0)) return false;
        if(i==2 && !io->copy_payload(io->context,image+p.payload_offset,p.payload_bytes,p.memory_bytes))
            return false;
    }
    state->authenticated=true;
    return true;
}
#endif
