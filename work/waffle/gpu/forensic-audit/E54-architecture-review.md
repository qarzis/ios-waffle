# E54 mandatory architecture review before further GPU experiments

Review after three UI observations since E51 (E52/E53/E54). No new hardware run until a revised lifetime model is tested.

E52 descriptor ownership fix passed 121 GPU fences/640 BOs to its planned30-second stop, but only4.64 seconds of GL work; Apple-logo screenshot did not qualify UI. E53 longer observation uncovered first233-reference/57-root/7492-word packet rejection; later heap failure secondary. E54 cdev snapshot/whole-root partition passed real variable-sized UI packets:342 logical requests/358 physical completions,13 multiwindow requests, including184BO/41roots/5780words in4 windows. No submit EINVAL observed before first failure. Small known-pixel GL control on this same kernel passed all256 pixels. This is command-path progress, not a working GPU desktop. Screenshot30 is black while GPU-active.

## First proven current blocker

Raw kernel138:16KiB GEM_NEW ENOMEM at800 records (capacity4096). Live790 BOs=60,080,128B; retired10=7,028,736B; total67,108,864B exactly64MiB. Live+next16KiB remains under64MiB; releasing eligible closed backing could admit the failed allocation. This differs from E48: at that time even live+next exceeded old32MiB, so retirement was not its primary cause. Do not repeat that refuted diagnosis without this new evidence. Full358-fence/800BO parent teardown passed in139, Android independently1.

## Architecture gap

| Component | Evidence/status |
|---|---|
| GPU initialization/firmware/MMIO/power/clocks | Implemented, hardware-qualified controls and full parent teardown |
| IOMMU publication | Implemented pagewise permissions/TLBI for CB1/CB2; no live BO removal path |
| CPU mapping revoke | Implemented on GEM_CLOSE; backing intentionally retained |
| Physical BO reclamation | Missing before full GPU detach; current destroy rejects published BO |
| GPU VA allocator | Append-only BASE+used; same used value accounts physical budget and VA frontier |
| Request submission | CPU snapshot/ordered windows hardware tested; prior packet limits no longer first blocker |
| Synchronization | Synchronous completion tokens+idle checks; interrupts/async recovery not implemented |
| CoreAnimation/EAGL | Actual backboardd draws/IOSurface copies; correct desktop output unverified |
| Metal | Not implemented |

## At most three hypotheses

H1 selected: retained closed BOs exhaust the physical budget. Directly supported by10 closed BOs/7,028,736B and live+next fitting. Minimal experiment must model GEM_CLOSE after synchronous GPU completion and CPU mapping revoke, validate owned PTEs, clear leaves, clean tables and invalidate/synchronize BOTH CB ASIDs, then and only then free backing. Any uncertain partial clear/TLB failure retains backing and poisons the context until parent stop. Reuse a completely revoked VA hole within the SAME64MiB window; do not extend VA/table/heap budgets. Separate physical in-use accounting from placement; count/handles remain monotonic for this bounded diagnostic. Show exact measured800-allocation timeline can admit the failed16KiB request after eligible closes.

H2: surviving live working set may later exceed64MiB. Not the current first failure:60,080,128B live plus16KiB fits. Re-measure only after H1 is tested. No heap growth now.

H3: presentation/shader or iOS startup issue may remain after memory stability. Black GPU-phase screenshot is insufficient to identify one. Do not claim UI correctness from GPU fences or investigate speculative shader changes before resolving the measured allocation failure.

No runtime reclamation changes have been made yet. Required models: no reclaim while busy/CPU-mapped; validate ownership before any PTE change; successful two-CB TLB sync before release/reuse; partial failure retains all memory; stale handles rejected; live neighbors and all page permissions unchanged; exact measured allocation replay and full teardown once. Existing immutable qualification stays unchanged.
