# Review after the next three UI attempts

E49 removed the measured live-working-set failure by moving the bounded heap
from32 to64MiB. E50 removed the measured1382-word submission refusal with a
1536-word bound that preserves the existing private command allocation and
completion guard. E51 separated64 per-job references from128 context records.
E51 still exhausted the context record array:126 live records and2 retired,
with46,972,928 allocated bytes under the64MiB physical budget.

Do not repeat another arbitrary128->256 array increase. The inline metadata
array and its small fixed bound are an architectural assumption from diagnostic
bring-up. They are not a hardware or MSM ABI limit.

For the current retain-until-detach policy, every record consumes at least16KiB
of the64MiB GPU heap. Therefore4096 is a strict budget-derived upper bound on
record count, including retired backing. Allocate the descriptor storage
separately from the16KiB SMMU parent object, once per context, keep all record
pointers stable, and release descriptors only after every BO is destroyed after
GPU detach. Allocation failure must leave no BO/PTE publication and must be
reclaimable even if no BO was created.

Keep64 references per submission,64MiB physical backing,8MiB per BO,1536 root
words,1024 jobs and the qualified initialization unchanged. Use a bounded
512-byte duplicate bitmap for4096 validated handles; do not place4096 byte
arrays or descriptor storage on the kernel stack.

This fixes premature descriptor exhaustion without claiming production BO
retirement/reuse. Before hardware: test descriptor allocation failure, empty
and partial-publication cleanup, retain-before-detach, full-budget/minimum-BO
counts, high-handle duplicate checks, and real ARM64 stack/container builds.
No fourth UI experiment until these ownership checks and source binding pass.
