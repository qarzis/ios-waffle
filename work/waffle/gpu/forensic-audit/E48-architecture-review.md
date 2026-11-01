# Architecture review after three UI experiments

E46 reached actual mobile backboardd / FD750 CoreAnimation context and failed
at the diagnostic32BO limit before submission. E47 changed only that bound to64,
passed the mapped control and reached three real GPU completions, then failed
at the unchanged32MiB heap. E48 changed only telemetry and reproduced the same
failure, preserving live/retired memory counts. All devices returned to Android.

## Proven first memory blocker

At the first5MiB refusal,34 live BOs occupy28,884,992 bytes and one retired BO
occupies16,384 bytes. The next request requires34,127,872 live bytes. Even full
retired-backing reclamation leaves a573,440-byte deficit against32MiB.
Therefore the assumption that the diagnostic32MiB heap fits the live UI working
set is false. Retired backing is not the primary cause of this first failure.

Exact allocation/SMMU host replay excludes PTE capacity or physical allocation
as the cause: the heap check refuses before those operations. Later slot and
submission errors follow the first allocation failure. Increasing slot count
again would not fix that first error.

## Revised next experiment

Keep64 BO records,8MiB per BO,32 queues,1024 root words and the qualified GPU
initialization unchanged. Evaluate a finite64MiB physical heap; this is a
hypothesis for one bounded UI workload, not a production memory policy.
Before changing runtime policy, replay the exact measured35BO prefix and the
refused5MiB request with candidate64MiB. Also exhaustively fill the entire64MiB
window through the actual SMMU code after25 bootstrap tables and prove it fits
the existing64-table pool. Keep old32MiB refusal as a regression case.

If that model passes, change only the heap bound and related bound reporting
and validation, build the kernel, run the existing mapped control, then attempt
one UI workload with the identical userspace root. Any new first failure must
be preserved. Do not raise BO slots, roots or heap again speculatively.

## Remaining production gaps

Physical backing and GPU VA are retained until context detach; close/reuse is
not production ready. The bounded1024-submit session, synchronous submission,
CPU row readback, singleton process, root diagnostic model and recovery still
need work. Actual UI pixel correctness and visual success are not established.
Three completed GPU commands do not prove an accelerated SpringBoard frame.
