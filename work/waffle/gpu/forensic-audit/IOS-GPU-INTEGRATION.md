# Waffle graphics integration after CP/ZAP/memory bring-up

This is an implementation inventory, not an acceleration claim. References below
are existing local source interfaces; no new user/kernel ABI is proposed here.

| Component | Status | Evidence or remaining contract |
|---|---|---|
| GMU/HFI/CP bootstrap | Implemented and hardware verified | E08 two CP_INIT ACK0/idle/full-collapse runs |
| Authenticated ZAP/security transition | Implemented and hardware verified | E09 PAS13 auth0, native switch ACK0, TRUST0 |
| GPU write / CPU observation | Implemented and hardware verified for NC diagnostic BO | E10 four-word result and all4096-word guard validation |
| GPU fetch of indirect PM4 buffer | Implemented and hardware verified | E11-r2 reads8wordIB and verifies actual result/all4096words after scoped AP_UNPRIV fix |
| Persistent power and firmware lifetime | Component ownership verified; production parent missing | E14 GMU/TCM and E15 SMMU parent ownership verified with three IBs and end; boardclock/AOP still enclose the bounded diagnostic |
| Dynamic BO/VA/page-table lifetime | Heap parent verified; dynamic user BO backend missing | E15 parent owns tables, plan, contexts and callbacks; per-service allocation/map/unmap remains unfinished |
| Submission completion / reclamation | Partial, bounded prototype verified | E12/E13/E14 three unique IB sequences/results, heap session + GMU/TCM component owner, close/stop/free ordering verified; no user fence backend |
| GPU interrupts | Not verified for normal work | Current execution uses polled ACK/idle; no normal waffle IRQ recovery path |
| IOKit service and IOUserClient | Existing shared implementation | kernel/files/iokit/Kernel/MacanGPU.cpp RedwoodGPUUserClient |
| Darwin Mesa transport | Existing implementation | Mesa src/redwood-drm/drm_shim.c: msm ioctl selectors through IOConnectCallStructMethod |
| Adreno750 userspace device profile | Present | Mesa freedreno_devices.py FD750 exact0x43051401 + no-speedbin fallback |
| IOSurface transport | Existing shared implementation, unverified waffle GPU path | MacanGPU.cpp MiniIOSurface / selector0x7e, drm_shim.c redwood_drm_surface |
| GL/OSMesa integration | Existing software path | userland/src/gl_osmesa.c explicitly recognizes softpipe/llvmpipe |
| Rasterization / offscreen pixels | Not verified on waffle | No shader/draw has been submitted by these diagnostics |
| CoreAnimation hardware composition | Not implemented/verified waffle backend | Needs BO/submit/fence/presentation path, not a README toggle |
| Metal | Missing | No Metal ABI implementation established |

The existing ABI can be reused only after a real waffle backend implements:
redwood_gpu_ready/parameter/address/address_free/map/mapped/unmap/submit/done/last,
and matching cache publication, resource accounting and stop behavior.
Today adreno_a6xx.c routes to macan_gpu_* only when macan_gpu_kept; otherwise
it uses its older a6xx globals. Setting gpu_kept or macan_gpu_kept for waffle
would route operations to the wrong hardware state and is not an integration.

MacanGPU::submit validates BO ranges and resolves addresses, then passes an
array of GPU addresses and dword counts to redwood_gpu_submit. Waffle's future
backend must fetch those IBs while all mapped BOs/power/HFI queues remain owned,
issue a real monotonically identified completion, and retain busy memory on
client close/timeouts. Existing optional-off HWSCHED RAW diagnostics establish
a small contract only; unrestricted production submissions require native
context/HFI scheduling and protection semantics to be reviewed separately.

Next implementation boundary after E11: an explicitly owned persistent waffle
session, first exercised by a bounded multi-submit kernel test and a verified
stop. No broad refactor of the passing diagnostics or userspace service is
justified until its ownership/lifetime contract is specified and checked.

E14 follow-up ownership boundary: the GMU component's begin/exercise/end API is
implemented and hardware verified while its SMMU parent remains alive. The next
parent object must capture table_pool, firmware plan, user/LPAC/GMU context
snapshots, protected_pool and pool_permission_context. Callback pointers must
refer to owner fields, not constructor stack locals. Detach and free only after
child end and TLB sync. Board clock saved[]/CX collapse and the enclosing AOP
transaction must then acquire independent lifetime: the current transaction
holds its mutex around the whole callback and sends ACDoff on exit.

No unrestricted userspace queue or actual draw was introduced by this work.
Cold-open/end with Androidreset between attempts is verified; a second open
after RSCsleep in the same boot remains untested.

E15 update: the SMMU parent object described above is now implemented and
hardware verified. Default ACCESS27/LPAC42 and the heap-owner three-IB session
both passed. Context snapshots, tables, plan and callback/matrix storage survive
constructor return. The next outer boundary is board-clock/CX/AOP ownership;
there is still no persistent per-service GPU backend or renderer switch.
