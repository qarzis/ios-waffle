# Native IOSurface import: staged implementation

S01 hardware result (2026-11-04): the existing Darwin Mesa selector0x7e now reaches a read-only Waffle handler. The caller and kernel agree on sid1,4898816bytes,offset0,stride3008,width750,height1624,BGRA,one non-planar image. The fallback render checked all1218000pixels with zero errors, zero padding damage and no GL error; GPU close and Android return passed. This is metadata integration, not zero-copy or a measured FPS gain. `S01-result.json` preserves source hashes of the compiled artifact rather than attributing later edits to that test.

The original40-byte Darwin surface ABI is retained. Metadata is opt-in under `WAFFLE_GPU_SURFACE_AUDIT=1`. Import requests still return unsupported and never create a fake GEM handle. The endpoint remains owned by its admitted process; negative tests cover foreign PIDs, missing surfaces, malformed backing, unsupported client memory and import refusal.

## Explicit layout correction

The initial generic-pitch concern was too broad. In the actual `fd6_layout.c`, explicit linear layouts with four bytes per pixel use64-byte pitch alignment. The extra256-byte alignment applies when Mesa chooses its own layout. Thus both observed pitches3008 and3072 satisfy the explicit alignment rule. The last linear level may overfetch rows rounded to a multiple of four; offset plus this footprint must fit the retained allocation. No global IOSurface stride change is needed or included.

## S02 retained backing, not yet a GPU import

Internal helpers hold the actual MiniIOSurface so its table identity and backing cannot be freed while referenced. They validate native cached backing, exclude its16KiB shared header, check supported BGRA/plane/element/offset/pitch/range rules and validate every4KiB physical page. The surface descriptor remains the owner of the allocation. They do not call the existing WC BO allocator, create a second CPU cache alias, publish a GPU PTE, or change any IOSurface pixels.

A publication flag blocks release until the caller proves GPU detach. Failure before publication balances the retained reference. Host tests execute the actual helper bodies, including noncontiguous physical pages, physical limits, short segments, offset/overfetch/overflow/capacity failures and1000balanced lifetimes. Kernel lookup and page-query implementations are modeled in those tests. These helpers are not wired to a userspace GPU import request yet.

## Remaining integration requirements

1. Refactor the registry publication boundary to accept already-retained storage while enforcing the existing residency/VA budgets. Mark publication before any PTE write. Uncertain partial mapping/TLB failure must retain backing until detach, as with current BOs.
2. Preserve the native cached CPU mapping. `WaffleGPUMemory` currently maps WC storage; it must not be reused unchanged for imported cached surfaces. Surface/header offsets and descriptor ownership must be explicit.
3. Implement CPU/GPU handoff and cache maintenance before enabling render-target use. Existing ordinary WC CPU_PREP/CPU_FINI checks do not implement cached-surface coherency. Source seed updates and framebuffer consumption need to agree with Waffle completion; donor fence callbacks alone are insufficient.
4. Deduplicate surface imports into generational handles, preserving held references across command submission and rejecting stale handles. Never import header pages or client-wrapped/multiplanar memory without a separate validated path.
5. Qualify one imported surface with independent pixel readback, padding/guard checks, CPU-to-GPU and GPU-to-CPU ownership transitions and final detached release. Only then enable it for the compositor. Preserve unsupported-surface fallback.
6. The80–100fps target also requires a proven display-completion protocol above the current two-MDP-frame guard and a separately qualified higher-rate iOS mode. Surface import alone does not establish that target.
