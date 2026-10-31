#include <assert.h>
#include "../../kernel/files/bsd/sys/waffle_gpu_va.h"
int main(void) {
    assert(waffle_gpu_compact_alias(0x80010000)==WAFFLE_GPU_GLOBAL_BASE+0x410000);
    assert(waffle_gpu_compact_alias(0x80070000)==WAFFLE_GPU_GLOBAL_BASE+0x470000);
    assert(waffle_gpu_compact_alias(0x61000000)==WAFFLE_GPU_GLOBAL_BASE+0x500000);
    assert(!waffle_gpu_compact_alias(0x61f00000));
    assert(!waffle_gpu_compact_alias(0x80080000));
    assert(!waffle_gpu_compact_alias(UINT64_MAX));
    assert(!waffle_gpu_compact_alias(0x60014000));
    assert(!waffle_gpu_compact_alias(0xa0000000));
    for(uint64_t address=0x61000000;address<0x61f00000;address+=4096) {
        uint64_t a=waffle_gpu_compact_alias(address);
        assert(waffle_gpu_va_valid(a));
        assert(a>=WAFFLE_GPU_GLOBAL_BASE+0x500000);
        assert(a+4096<=WAFFLE_GPU_GLOBAL_BASE+WAFFLE_GPU_NATIVE_GLOBAL_BYTES);
        assert(a==waffle_gpu_compact_alias(address+4095)-4095);
    }
    for(uint64_t address=0x80000000;address<0x80080000;address+=4096) {
        uint64_t a=waffle_gpu_compact_alias(address);
        assert(a+4096<WAFFLE_GPU_GLOBAL_BASE+0x500000);
        assert(waffle_gpu_va_valid(a));
    }
    return 0;
}
