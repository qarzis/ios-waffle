#include <cassert>
#include <cstring>
#include <cstdio>
#include "../../vendor/unixnu/adreno740/NativeAdrenoABI.h"
#include "../../kernel/files/bsd/sys/waffle_unixnu_gpu.h"
int main(){
 static_assert(NativeAdrenoAbiVersion==2 && NativeAdrenoMethodQuery==1,"pinned upstream protocol");
 static_assert(sizeof(NativeAdrenoAbiBoAlloc)==sizeof(waffle_unixnu_alloc),"alloc wire size");
 static_assert(offsetof(NativeAdrenoAbiBoAlloc,contiguous)==offsetof(waffle_unixnu_alloc,contiguous),"alloc field layout");
 static_assert(sizeof(NativeAdrenoAbiParams)==sizeof(waffle_unixnu_params),"wire size");
 waffle_unixnu_call c{};c.version=NativeAdrenoAbiVersion;c.method=NativeAdrenoMethodQuery;c.output_bytes=sizeof(NativeAdrenoAbiParams);
 assert(!waffle_unixnu_query(&c,192ULL*1024*1024));
 NativeAdrenoAbiParams p;std::memcpy(&p,c.payload,sizeof(p));assert(p.abi_version==2&&p.input_bits==39&&p.output_bits==36&&!p.flags&&p.max_bo_bytes==192ULL*1024*1024);
 for(unsigned method=0;method<256;method++)if(method!=NativeAdrenoMethodQuery){auto copy=c;copy.method=method;assert(waffle_unixnu_query(&copy,192ULL*1024*1024)==WAFFLE_UNIXNU_UNSUPPORTED);assert(!std::memcmp(copy.payload,c.payload,sizeof(c.payload)));}
 for(unsigned size=0;size<=WAFFLE_UNIXNU_ABI_BYTES+1;size++)if(size!=sizeof(p)){auto copy=c;copy.output_bytes=size;assert(waffle_unixnu_query(&copy,1)==WAFFLE_UNIXNU_INVALID);}
 for(unsigned v:{0u,1u,3u,~0u}){auto copy=c;copy.version=v;assert(waffle_unixnu_query(&copy,1)==WAFFLE_UNIXNU_INVALID);}
 c.input_bytes=1;assert(waffle_unixnu_query(&c,1)==WAFFLE_UNIXNU_INVALID);
 puts("PASS exact upstream UniXNU ABI2 Query -> existing A750 limits; unsupported methods/capabilities refused; host only, no Metal/IOKit/hardware claim.");
}
