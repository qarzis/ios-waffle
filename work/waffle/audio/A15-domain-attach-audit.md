# Native audio DMA domain audit after A14

A14 establishes only no valid SMR match for audio1001/1081/1061. It does not establish all71 context banks free, writable or owned by XNU. Do not choose bank0 from absent audio matches.

Pinned OnePlus kernel e39bf7032e38c547d588372a11a5dd55eb714860, drivers/iommu/arm/arm-smmu/arm-smmu.c:
- arm_smmu_attach_dev at2045 initializes the domain then adds only this device master.
- __arm_smmu_alloc_cb at390 reuses a pinned bank only when its device stream entry is pinned; otherwise reserves from tracked bitmap. A14 has no such audio entry.
- Stage1 domain at1380 uses CBAR S1_TRANS_S2_BYPASS and allocation start num_s2_context_banks, not a fixed arbitrary CB number.
- arm_smmu_init_context_bank/arm_smmu_write_context_bank configure page tables, TCR/MAIR/TTBR and SCTLR before stream attachment.
- arm_smmu_domain_add_master at1880 binds its stream indexes to the allocated bank, default privilege, translation type; no audio-specific bank constant.
- arm_smmu_write_s2cr at1663 has implementation override; copying generic register literals before selecting the native implementation is unqualified.
- Initial driver reset and SMR-mask selftest are global operations and cannot be copied into a live UEFI display environment.

Live audio DT: coherent DMA; pool10000000+10000000, native SID maskf, stream1001/ignore-mask80 and1061/mask0. Buffer IOVA plus tagged lowSIDbits<<32 is DSP protocol address; raw physical address is not a replacement.

Next minimal experiment must remain read-only: inventory all valid stream routes and referenced CBs, NUMS2CB, and SCTLR of potential unreferenced banks; preserve global/stream configuration. Decode ambiguous/overlapping routes and enabled unreferenced banks as unavailable. This provides candidates, not proof of secure ownership; qualify native implementation/secure access before first writes. After ownership, use one bounded page table and unmapped guards, then DSP memory-map ACK, then period completion; no amp/iOS sink claims before actual PCM.

No new hardware run for audio during E109 GPU USB ownership. No DMA/CB/reset writes implemented by this audit.

## A15 read-only inventory candidate, 2026-11-05
Live DT compatible qcom,qsmmu-v500 selects qsmmuv500_impl (native arm-smmu-qcom.c:3144,3270 onward), not the Adreno override. This implementation has no write_s2cr callback; generic stream writes apply only after native domain ownership is established. Global reset remains prohibited.

New inventory reads all SMR/S2CR pairs and all SCTLRs twice, and verifies ID registers again. Any read failure, observed change, reserved route type or translated out-of-range CB rejects the entire result. A candidate must be outside NUMS2CB, unreferenced by every valid translated route and SCTLR.M=0. Enabled unreferenced banks are excluded. Even stable disabled candidates do not establish secure ownership, global exclusion or writability; no allocation or attach is implemented. The two passes cannot exclude ABA or later firmware changes.

Actual helper sanitizer tests pass legacy/EXID validity, all read failures and changes at every read position, geometry, reserved/out-of-range routes, stage2 and enabled-orphan exclusion. Existing isolated --audio-preflight --audio-iommu path adds heap-backed inventory with matching free/unmap, prints all routes/banks only after a complete stable inventory. Mandatory build test and source snapshot list updated. Dedicated diagnostic-audio-inventory-a15 building; no A15 hardware result yet.

## A15 actual hardware result
Run20261105T111402Z / auto20261105T111338Z original exit0/success1/Android confirmed. Inventory passed: 107 routes,71 banks, NUMS2CB0; valid translation routes reference banks0–5. Remaining65 observed M=0/unreferenced, but SCTLR is nonzero (e.g CB6=05c9a71a, CB7=3fcc6308). These are not free-bank or ownership proofs. No CB/SMR/S2CR/reset/TLB writes, no DSP startup, no DMA/PCM. Full trace validated from immutable kernel-1.log with SHA in A15-inventory-analysis.json; final snapshot contains a truncated trailing repeated route prefix and is strictly refused, not repaired. Original overall success retained.
First pre-USB attempt failed missing audio-probe root; preserved auto-a15-preflight-missing-root.log, built dedicated root and retried only after the missing artifact was supplied. Dedicated root now binds inventory header too.
Next: qualify context ownership/secure access and explain nonzero disabled register state using pinned native implementation; do not allocate CB6 merely because M=0.

## A16 global access hypothesis
A15 per-bank state does not establish global client access. Selected hypothesis: inherited CR0.CLIENTPD or global cache lock prerequisites prevent using an otherwise unreferenced bank. Minimal experiment adds stable double-read CR0(0)/ACR(10), with exact native bit decoding; no writes or DSP. Host all-read-failure/mutation tests and full XNU/EFI/container build pass. Separate bound A16 firmware root and paired validator pass. This does not establish bank ownership even if CLIENTPD=0. Native cfg_probe modifies sACR cache lock only with secure permission; do not copy the global reset into this live environment.
GPU D19C fresh-event-to-delta2 interval was1154.38/1177.76/1184.27us, not a whole extra frame in these sparse samples; preserve guard and investigate output readback as a separate throughput cost.
