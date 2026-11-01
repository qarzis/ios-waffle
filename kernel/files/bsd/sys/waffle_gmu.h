#ifndef WAFFLE_GMU_H
#define WAFFLE_GMU_H
#include <mach/mach_types.h>
#include <sys/waffle_gmu_firmware.h>
#include <sys/waffle_gpu_va.h>
#define WAFFLE_GMU_REGIONS 16
#define WAFFLE_GPU_SQE_ADDRESS 0x80010000u
#define WAFFLE_GPU_AQE_ADDRESS 0x80030000u
#define WAFFLE_GPU_RING_ADDRESS 0x80050000u
#define WAFFLE_GPU_SCRATCH_ADDRESS 0x80060000u
#define WAFFLE_GPU_PWRUP_ADDRESS 0x80070000u
#define WAFFLE_HWSCHED_POOL_ADDRESS 0x61000000u
#define WAFFLE_HWSCHED_POOL_SIZE 0x02000000u
#define WAFFLE_GMU_LOG_ADDRESS 0x60004000u
#define WAFFLE_GMU_LOG_SIZE    0x10000u
#define WAFFLE_GMU_HFI_ADDRESS 0x60014000u
#define WAFFLE_GMU_HFI_SIZE    0x12000u
struct waffle_gmu_region {
    uint32_t address, size;
    vm_offset_t memory;
    bool gpu_only, readonly;
};
struct waffle_submit_session;
struct waffle_gmu_plan {
    const uint8_t *firmware;
    size_t length;
    unsigned count;
    bool split_gpu_va,compact_gpu_va;
    bool raw_stage_pause;
    struct waffle_submit_session *submit_session;
    unsigned session_slumber_sequence;
    unsigned compute_mode;
    bool (*pool_permissions)(void *,uint64_t,uint32_t,uint32_t);
    void *pool_permissions_context;
    vm_offset_t fault_smmu;
    uint32_t fault_page,fault_pages;
    uint64_t protected_address;
    uint32_t protected_size;
    struct waffle_gmu_region regions[WAFFLE_GMU_REGIONS];
};
static inline uint64_t waffle_gpu_plan_alias(const struct waffle_gmu_plan *plan,uint64_t address)
{
    return plan->compact_gpu_va ? waffle_gpu_compact_alias(address) : waffle_gpu_global_alias(address);
}
bool waffle_gmu_prepare(struct waffle_gmu_plan *, unsigned);
bool waffle_gmu_probe_tcm(struct waffle_gmu_plan *, unsigned, vm_offset_t);
void waffle_gmu_free(struct waffle_gmu_plan *);
/* Parent retains SMMU/plan/clock ownership across these calls. */
struct waffle_gmu_owner;
struct waffle_gmu_owner *waffle_gmu_owner_begin(struct waffle_gmu_plan *,unsigned,vm_offset_t);
bool waffle_gmu_owner_exercise(struct waffle_gmu_owner *);
bool waffle_gmu_owner_can_bind_bo(struct waffle_gmu_owner *);
bool waffle_gmu_owner_bind_bo(struct waffle_gmu_owner *,struct waffle_gmu_region *);
bool waffle_gmu_owner_end(struct waffle_gmu_owner *);
#endif
