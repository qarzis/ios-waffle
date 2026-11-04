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

## S03 registry publication candidate

The internal BO now distinguishes owned WC storage from a retained cached surface token. Ordinary GEM allocation still rejects cached-coherent flags; a cached surface is prepared through a separate internal path, without clearing pixels or creating a WC CPU alias. The WC user mapper refuses surface storage. Destruction releases the retained surface token rather than treating it as an IOBuffer allocation.

`waffle_gpu_registry_adopt` checks ownership state, slot/residency/VA limits, idle and vacancy before transferring the prepared object. A pre-transfer failure leaves the object with its caller. After transfer the registry marks publication before the first PTE; uncertain mapping or TLB failure retains the object and poisons further work. Existing reclaim verifies owned leaves, removes mappings and synchronizes GPU/LPAC ASIDs before permitting surface release.

An isolated diagnostic operation, W/0x55, is intentionally separate from Darwin Mesa selector0x7e. It admits only the owning PID1, publishes one retained surface and immediately revokes it. It creates no GEM handle, no CPU mapping and no GPU commands referencing that memory. Host tests execute actual storage, registry, SMMU and cdev adapter code. Physical I/O is modeled there, so native execution remains a separate requirement.

## Next data-access experiment, after native S03 qualification

The first GPU data access should use the already-qualified `waffle_writeback_packet` CP_MEM_WRITE payload, restricted to four words inside the held surface. It must not invent a new packet or enable arbitrary user commands.

* Preserve the original words, admit no concurrent CPU writer in the isolated test, and clean cached CPU data to the point of coherency before GPU ownership.
* Submit through the existing owned context and qualified completion tail. Cache maintenance is not a substitute for GPU completion.
* Invalidate/resolve CPU cache state only after confirmed GPU completion, then independently compare actual CPU-read values with the GPU pattern. Do not populate expected values from CPU.
* Restore original words, make the restoration visible, and verify the full surface/padding through the existing independent pixel control before releasing mappings.
* Private submissions must update the cdev's fence accounting consistently with the same context. The ioctl may not report a completion fence that was never executed or leave future ordinary Mesa submissions expecting a stale sequence.
* Any uncertain post-publication failure retains backing until safe context detach/reset. Only after bidirectional cache/data evidence should normal Mesa imports, deduplicated handles, cached CPU mapping and compositor completion integration be enabled.

This plan is not an implemented GPU data-access or zero-copy result.

## S04 qualified hardware result
Run `20261104T194715Z` passed the original strict runner and returned Android. GPU command fence 3 wrote four expected words directly to the retained cached native IOSurface. CPU read all four correctly after cache invalidation; original words were restored and cleaned before both command and surface mappings were revoked. The following 1,218,000-pixel check reported zero errors. Normal Mesa surface import remains disabled.

Next gate: CPU-initialized native surface data must be read by the GPU into a separate owned result buffer and independently checked after completion. After that, define GEM handle ownership, CPU_PREP/FINI synchronization, resource destruction and failure retention before enabling Mesa imports. Neither this isolated write test nor a future command-copy read test establishes shader resource correctness or higher UI FPS.

## S05 experiment and the remaining ownership gap
S05 reads four CPU-initialized words from native cached IOSurface pages into a different owned WC buffer using `CP_MEM_TO_MEM` (0x73). The packet's five-word payload (32-bit flags, destination64, source64) is derived from local Mesa `adreno_pm4.xml` and `tu_query_pool.cc::copy_query_value_gpu`, with header parity independently checked. A final `CP_WAIT_MEM_WRITES` and the normal completed submission fence precede CPU inspection. CPU fills only source with expected values and destination with poison. After independently checking destination and unchanged source, it restores the original source words and revokes both allocations. Hardware run `20261104T195742Z` passed the original strict runner: all four destination words matched, originals were restored, both allocations retired, the full 1,218,000-pixel check passed, and Android returned. This qualifies only the isolated command-processor read.

Source audit before enabling ordinary imports:

| Component | Current evidence | Remaining work |
|---|---|---|
| Native allocation, SMMU publication and dual-ASID revoke | S03/S04 hardware qualified | Keep the surface retained for each live imported GEM lifetime |
| GPU write to cached surface and CPU read | S04 isolated four-word write passed | Shader render-target writes and full-frame reuse unverified |
| CPU writes read by GPU | S05 isolated four-word command-processor read passed | Shader texture sampling unverified even if command-processor read passes |
| Mesa import entry points | Existing `osmesa_surface_resource` calls `resource_from_handle`; Darwin `fd_bo_from_dmabuf_drm` uses IOSurface ID and `drmPrimeFDToHandle` | Implement a real GEM handle, describe/import consistency and repeated-ID handle reuse; preserve generation limits and failure cleanup |
| CPU_PREP/FINI | cdev validates only ordinary handle/op; existing WC BO path has no cache transitions | Imported cached BOs need completion and cache ownership transitions; maintain ordinary WC behavior |
| IOSurface Lock/Unlock | `MiniIOSurface::lockCommon` updates content seed on writer unlock | No GPU completion/cache action exists here. Do not treat the API lock as a GPU fence or kernel-wide exclusive writer lock. Isolated S04/S05 own their private surface by construction |
| Imported CPU mappings | `waffle_gpu_memory_map` rejects surface storage | Preserve native cached mapping, exclude shared header, retain proper lifetime; never create a WC alias |
| Resource destruction and reclaim | Existing regular GEM close/reclaim is tested | Imported object must retain backing until all GEM references, CPU maps and GPU use are retired; uncertain completion retains backing |

The next implementation should first expose a bounded isolated import/close test with no rendering, including duplicate import and stale-handle refusals. Only after that should a controlled shader sample/render test enable the native texture path. The GPU test result must remain distinct from UI FPS and display-refresh changes.

## S06 isolated imported GEM lifetime
A private PID1-only opcode creates a real generation-checked GEM descriptor from retained native IOSurface storage. Repeated imports of a live SID return its existing handle with no extra hold, matching PRIME handle-table semantics. After GEM_CLOSE revokes the mapping and drops the hold, reimport obtains the next generation; the old handle remains invalid. Ordinary surface import remains ENOTSUP.

This experiment explicitly refuses imported buffers in SUBMIT, MAP, CPU_PREP and CPU_FINI, so lifetime qualification cannot accidentally enable unsynchronized cached rendering. The phone control imports twice, checks duplicate reuse and GPU VA, checks CPU-map refusal, closes, checks stale INFO refusal, reimports and repeats close. The complete source image is then checked. Host tests additionally cover foreign PID, reserved inputs, adoption failure cleanup, descriptor exhaustion, failed-revoke retention, stale close, submission and CPU access refusal. Hardware run `20261104T210531Z` passed the original strict runner and returned Android. It reused handle 27, closed it, reimported as 8219, refused stale handle access and CPU mapping, and closed both native imports. The subsequent 1,218,000-pixel check had zero errors.

The following independent gate should import a native surface into an actual Mesa `pipe_resource` and destroy it without drawing. Darwin's existing path already calls `drmPrimeFDToHandle` then `resource_from_handle`, so this can exercise format/stride/layout and fd_bo reference ownership before enabling SUBMIT. Its shim opt-in must route only isolated diagnostic imports; ordinary UI stays on the qualified fallback until cache and completion ownership are implemented.

## S07 actual Mesa resource lifetime qualified
Hardware run `20261104T211254Z` passed the original strict runner and returned Android. Two actual `glEGLImageTargetTexture2DOES` calls created 750×1624 textures from SID 1 through the existing Mesa resource-import path. They shared GEM handle 27. Deleting both textures retired that handle and revoked its native mapping in both ASIDs. The following 1,218,000-pixel check had zero errors. This used the exact qualified S06 kernel and a separately rebuilt opt-in Mesa library.

Imported GPU submissions remain refused. The next experiment must qualify shader sampling of a CPU-initialized native texture with explicit cache ownership before enabling UI imports or imported render targets. There is no measured FPS improvement from these resource-lifetime tests.
