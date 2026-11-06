/* Experimental UniXNU wire ABI ingress for the existing A750 backend.
 * This is NOT an IOKit service or a Metal device. Stage1 exposes only the
 * version/limits query; the cdev adapter also translates owned allocation/free.
 * Mapping is limited to owned RW/noncacheable/outer-shareable 16KiB addresses;
 * submission remains refused until translated
 * with per-client lifetime and fence semantics. Do not advertise imports or
 * coherence merely because upstream understands those capability flags. */
#ifndef WAFFLE_UNIXNU_GPU_H
#define WAFFLE_UNIXNU_GPU_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define WAFFLE_UNIXNU_ABI_BYTES 4096
struct waffle_unixnu_call {
 uint32_t version,method,input_bytes,output_bytes;
 uint8_t payload[WAFFLE_UNIXNU_ABI_BYTES];
};
/* NativeAdrenoAbiParams exact upstream layout, verified by upstream-header
 * fixture. Kept as a byte protocol here to avoid user C++/IOKit dependencies. */
struct waffle_unixnu_map {uint64_t handle,iova;uint32_t permissions,writeback,shareability,reserved;};
struct waffle_unixnu_alloc {uint64_t bytes;uint32_t align_log2,contiguous;};
struct waffle_unixnu_params {uint32_t version,input_bits,output_bits,flags;uint64_t max_bo_bytes;};
enum {WAFFLE_UNIXNU_OK=0,WAFFLE_UNIXNU_INVALID=1,WAFFLE_UNIXNU_UNSUPPORTED=2};
static inline unsigned waffle_unixnu_query(struct waffle_unixnu_call *r,uint64_t max_bytes)
{
 if(!r || r->version!=2 || r->input_bytes>WAFFLE_UNIXNU_ABI_BYTES ||
    r->output_bytes>WAFFLE_UNIXNU_ABI_BYTES)return WAFFLE_UNIXNU_INVALID;
 if(r->method!=1)return WAFFLE_UNIXNU_UNSUPPORTED;
 if(r->input_bytes || r->output_bytes!=sizeof(struct waffle_unixnu_params) || !max_bytes)return WAFFLE_UNIXNU_INVALID;
 struct waffle_unixnu_params p={2,39,36,0,max_bytes};
 const uint8_t *s=(const uint8_t *)&p;for(size_t n=0;n<sizeof(p);n++)r->payload[n]=s[n];
 return WAFFLE_UNIXNU_OK;
}
#endif
