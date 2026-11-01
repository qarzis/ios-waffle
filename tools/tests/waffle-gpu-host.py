#!/usr/bin/env python3
"""Exercise the real early GPU probe with simulated MMIO and XNU glue.

Checks rollback and denied-access paths; this cannot establish hardware safety
or that an SM8650 clock/power block answers as the vendor documents describe.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMMON = r"""
#ifndef MOCK_XNU_H
#define MOCK_XNU_H
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
#define __printflike(a,b) __attribute__((format(printf,a,b)))
#define NSEC_PER_USEC 1000
#define VM_WIMG_IO 7u
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 5
#define KERN_SUCCESS 0
#define kernel_map 7
int kmem_alloc(unsigned,uintptr_t *,unsigned,unsigned,unsigned);
void kmem_free(unsigned,uintptr_t,unsigned);
typedef unsigned lck_mtx_t;
static inline bool lck_mtx_try_lock(lck_mtx_t *p) { (void)p; return false; }
static inline void lck_mtx_unlock(lck_mtx_t *p) { (void)p; }
int PE_parse_boot_argn(const char *, void *, int);
void delay_for_interval(unsigned, unsigned);
#endif
"""
HARNESS = r"""
#include "mock_xnu.h"
#include <sys/waffle_gpu.h>
#include <sys/waffle_aop.h>
#include <sys/waffle_smmu.h>
static uint32_t gcc[WAFFLE_GCC_SIZE / 4], cc[WAFFLE_GPUCC_SIZE / 4];
static uint32_t aop[WAFFLE_AOP_QMP_MAP_SIZE / 4];
static uint32_t saved_gcc[WAFFLE_GCC_SIZE / 4];
static uint32_t saved_cc[WAFFLE_GPUCC_SIZE / 4];
static unsigned waffle, probe, gcc_maps, cc_maps, aop_maps, aop_unmaps, returned, waits, map_failure;
lck_mtx_t macan_aop_mailbox_lock;
static unsigned cx_response;
int PE_parse_boot_argn(const char *name, void *value, int size) {
    assert(size == 4);
    if (!strcmp(name,"waffle")) { *(uint32_t *)value=waffle; return 1; }
    if (!strcmp(name,"waffle_gpu")) { *(uint32_t *)value=probe; return 1; }
    return 0;
}
void delay_for_interval(unsigned time, unsigned unit) {
    assert(time == 100 && unit == 1000); waits++;
    if (probe>=3 && cx_response) {
        if (cc[WAFFLE_GPU_CX_GDSCR/4]&1) cc[WAFFLE_GPU_CX_HW_CTRL/4]&=~(1u<<31);
        else cc[WAFFLE_GPU_CX_HW_CTRL/4]|=1u<<31;
    }
}
vm_offset_t ml_io_map(vm_offset_t physical, vm_size_t size) {
    if (physical == WAFFLE_GCC_BASE) {
        assert(size == WAFFLE_GCC_SIZE); gcc_maps++;
        return map_failure ? 0 : (vm_offset_t)gcc;
    }
    assert(physical == WAFFLE_GPUCC_BASE && size == WAFFLE_GPUCC_SIZE);
    cc_maps++; return (vm_offset_t)cc;
}
vm_offset_t ml_io_map_unmappable(vm_offset_t physical, vm_size_t size, unsigned int flags) {
    assert(physical == WAFFLE_AOP_QMP_BASE && size == WAFFLE_AOP_QMP_MAP_SIZE && flags == VM_WIMG_IO);
    aop_maps++;
    return map_failure ? 0 : (vm_offset_t)aop;
}
void ml_io_unmap(vm_offset_t base, vm_size_t size) {
    assert(base == (vm_offset_t)aop && size == WAFFLE_AOP_QMP_MAP_SIZE);
    aop_unmaps++;
}
void loader_log_putc(char c) { (void)c; }
void loader_return(void) { returned++; }
void waffle_smmu_probe(vm_offset_t base, uint32_t page, uint32_t pages,
        uint32_t contexts, uint32_t matches, unsigned translate) {
    (void)base; (void)page; (void)pages; (void)contexts; (void)matches; (void)translate;
    assert(!"SMMU must remain inaccessible in the denied/busy host scenarios");
}
struct waffle_smmu_owner *waffle_smmu_owner_begin(uintptr_t b,uint32_t p,uint32_t ps,uint32_t c,uint32_t m,unsigned n) {
    (void)b;(void)p;(void)ps;(void)c;(void)m;(void)n;assert(0);return NULL;
}
bool waffle_smmu_owner_exercise(struct waffle_smmu_owner *o) {(void)o;assert(0);return false;}
struct waffle_gpu_copy_job;
struct waffle_gpu_memory *waffle_smmu_owner_memory_new(struct waffle_smmu_owner *s,uint64_t b,uint32_t f){(void)s;(void)b;(void)f;assert(0);return NULL;}
bool waffle_smmu_owner_memory_reclaim(struct waffle_smmu_owner *s,struct waffle_gpu_memory *b,bool u){(void)s;(void)b;(void)u;assert(0);return false;}
bool waffle_smmu_owner_submit(struct waffle_smmu_owner *s,struct waffle_gpu_submit_job *j){(void)s;(void)j;assert(0);return false;}
bool waffle_gpu_drm_register(void){return true;}
bool waffle_gpu_msm_register(void){return true;}
bool waffle_smmu_owner_buffers(struct waffle_smmu_owner *o,struct waffle_gpu_buffer b[2]){(void)o;(void)b;return false;}
bool waffle_smmu_owner_copy(struct waffle_smmu_owner *o,struct waffle_gpu_copy_job *j) {(void)o;(void)j;assert(0);return false;}
bool waffle_gpu_user_register(void) {assert(0);return false;}
bool waffle_gpu_service_probe(void) {assert(0);return false;}
bool waffle_smmu_owner_end(struct waffle_smmu_owner *o) {(void)o;assert(0);return false;}
int kmem_alloc(unsigned m,uintptr_t *p,unsigned n,unsigned f,unsigned t){(void)m;(void)p;(void)n;(void)f;(void)t;assert(0);return 1;}
void kmem_free(unsigned m,uintptr_t p,unsigned n){(void)m;(void)p;(void)n;assert(0);}
void waffle_adreno_init(void);
static void reset(unsigned mode, unsigned board, uint32_t cfg) {
    memset(gcc,0,sizeof(gcc)); memset(cc,0xa5,sizeof(cc));
    memset(aop,0,sizeof(aop));
    cc[WAFFLE_GPU_CX_GDSCR/4]=0x22f801;
    cc[WAFFLE_GPU_CX_HW_CTRL/4]=0x2800010a;
    gcc[WAFFLE_GPU_CFG_AHB/4]=cfg;
    gcc[WAFFLE_GPU_MEMNOC/4]=0x80000003;
    memcpy(saved_gcc,gcc,sizeof(gcc));
    memcpy(saved_cc,cc,sizeof(cc));
    waffle=board; probe=mode;
    gcc_maps=cc_maps=aop_maps=aop_unmaps=returned=waits=map_failure=cx_response=0;
}
static void unchanged(void) {
    assert(!memcmp(gcc,saved_gcc,sizeof(gcc)));
    assert(!memcmp(cc,saved_cc,sizeof(cc)));
}
int main(void) {
    reset(0,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && !returned); unchanged();
    reset(2,0,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && !returned); unchanged();
    reset(94,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && returned==1); unchanged();
    reset(93,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && returned==1); unchanged();
    reset(92,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && returned==1); unchanged();
    reset(79,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && returned==1); unchanged();
    reset(45,1,0); waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && aop_maps==1 && aop_unmaps==1 && returned==1); unchanged();
    reset(45,1,0); map_failure=1; waffle_adreno_init();
    assert(!gcc_maps && !cc_maps && aop_maps==1 && !aop_unmaps && returned==1); unchanged();
    reset(1,1,0x80000020); waffle_adreno_init();
    assert(gcc_maps==1 && !cc_maps && returned==1 && !waits); unchanged();
    reset(2,1,0x20); waffle_adreno_init();
    assert(gcc_maps==1 && cc_maps==1 && returned==1 && !waits); unchanged();
    reset(2,1,0x21); waffle_adreno_init();
    assert(gcc_maps==1 && cc_maps==1 && returned==1 && !waits); unchanged();
    reset(2,1,0x23); waffle_adreno_init();
    assert(gcc_maps==1 && cc_maps==1 && returned==1 && !waits); unchanged();
    reset(2,1,0x80000023); waffle_adreno_init();
    assert(gcc_maps==1 && !cc_maps && returned==1 && waits==100); unchanged();
    reset(2,1,0x80000020); waffle_adreno_init();
    assert(gcc_maps==1 && !cc_maps && returned==1 && waits==100); unchanged();
    reset(2,1,0); map_failure=1; waffle_adreno_init();
    assert(gcc_maps==1 && !cc_maps && returned==1 && !waits); unchanged();
    reset(3,1,0x23); cx_response=1; waffle_adreno_init();
    assert(cc_maps==1 && returned==1 && waits==2); unchanged();
    reset(3,1,0x23); waffle_adreno_init();
    assert(cc_maps==1 && returned==1 && waits==501); unchanged();
    reset(3,1,0x23); cc[WAFFLE_GPU_CX_HW_CTRL/4]|=1u<<31;
    memcpy(saved_cc,cc,sizeof(cc)); waffle_adreno_init();
    assert(cc_maps==1 && returned==1 && !waits); unchanged();
    reset(4,1,0x23); waffle_adreno_init();
    assert(cc_maps==1 && returned==1 && waits==501); unchanged();
    /* RCG update busy before entry: PLL/always-on votes must still roll back,
     * while the busy source and GMU register block remain untouched. */
    reset(4,1,0x23); cx_response=1; waffle_adreno_init();
    assert(cc_maps==1 && returned==1 && waits==102); unchanged();
    puts("15 probe scenarios passed");
}
"""


def main():
    with tempfile.TemporaryDirectory(prefix="waffle-gpu-test-") as directory:
        d = Path(directory)
        (d / "mock_xnu.h").write_text(COMMON)
        for name in ("kern/clock.h", "kern/locks.h", "vm/memory_types.h", "vm/vm_kern.h", "arm/memory_types.h", "libkern/libkern.h", "mach/mach_types.h",
                     "pexpert/pexpert.h", "sys/systm.h"):
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#include "mock_xnu.h"\n')
        (d / "test.c").write_text(HARNESS)
        # The target barrier is the sole instruction with no host equivalent.
        # The remaining C body is the production source without substitutions.
        source = (ROOT / "kernel/files/bsd/dev/waffle_adreno.c").read_text()
        barrier = '__asm__ volatile("dsb sy" ::: "memory");'
        assert source.count(barrier) == 2
        (d / "driver.c").write_text(source.replace(barrier, '__asm__ volatile("" ::: "memory");'))
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-g", "-I", str(d),
                        "-I", str(ROOT / "kernel/files/bsd"), str(d / "driver.c"),
                        str(d / "test.c"), "-o", str(d / "test")], check=True)
        result = subprocess.run([str(d / "test")], check=True, capture_output=True, text=True)
        print(result.stdout.splitlines()[-1])


if __name__ == "__main__":
    main()
