#ifndef WAFFLE_SMMU_H
#define WAFFLE_SMMU_H
#include <stdint.h>
#include <stdbool.h>

/* Bounded session API. The caller must retain board clocks, CX and AOP
 * until end returns. Calls are serialized; this is not a userspace queue.
 * A failed stop retains resources and returns to the loader for reset. */
struct waffle_smmu_owner;
struct waffle_smmu_owner *waffle_smmu_owner_begin(uintptr_t smmu,
    uint32_t page, uint32_t pages, uint32_t contexts, uint32_t matches, unsigned probe);
bool waffle_smmu_owner_exercise(struct waffle_smmu_owner *owner);
bool waffle_smmu_owner_end(struct waffle_smmu_owner *owner);
#endif
