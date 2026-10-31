# Waffle graphics integration after CP/ZAP/memory bring-up

This is an implementation inventory, not an acceleration claim. References below
are existing local source interfaces; no new user/kernel ABI is proposed here.

| Component | Status | Evidence or remaining contract |
|---|---|---|
| GMU/HFI/CP bootstrap | Implemented and hardware verified | E08 two CP_INIT ACK0/idle/full-collapse runs |
| Authenticated ZAP/security transition | Implemented and hardware verified | E09 PAS13 auth0, native switch ACK0, TRUST0 |
| GPU write / CPU observation | Implemented and hardware verified for NC diagnostic BO | E10 four-word result and all4096-word guard validation |
| GPU fetch of indirect PM4 buffer | Hardware pending E11 | Same known memory-write stream staged separately in existingBO |
| Persistent power and firmware lifetime | Missing for waffle production | waffle_adreno_init always returns to loader; smmu_probe and GMU paths always stop/free |
| Dynamic BO/VA/page-table lifetime | Missing waffle backend | Current tables are diagnostic local objects, not persistent per-service resources |
| Submission completion / reclamation | Partial | RAW ACK plus bounded idle/readback works; no waffle user fence implementation |
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
