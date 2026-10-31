# GPU forensic audit — OnePlus 12 / Adreno 750

Forensic baseline and architecture review are recorded below and in the audit dossier. The next phase implements only the scoped H1 diagnostic experiment; no CP RAW retry is queued. The reset root cause remains unknown. Builds and register readback are not proof of command execution.

## Evidence baseline

- Frozen source inventory: `work/waffle/gpu/forensic-audit/code-freeze.json`.
- Structured hardware history: `work/waffle/gpu/forensic-audit/hardware-history.json` (reports, not a count of independent experiments).
- Test 93: `work/waffle/runs/20261031T073848Z`; preparation/lifecycle control passed.
- Test 94: `work/waffle/diagnostic-gpu-native94/hardware-result-94.json`; RAW experiment failed, crashdump collected in `work/waffle/gpu/crashdumps/20261031T074728Z`, Android recovery confirmed. No successful CP_INIT acknowledgement or rendered frame established.
- Current blocker: CP command execution remains unproven; failing RAW experiment enters 900e. The reset root cause has not been established. Last saved prepublication checkpoint does not establish whether publication occurred.

## 2026-10-31 — offline allocation-contract check

Question: does the port incorrectly echo the requested allocation size, while the native host replies with the rounded allocation size?

Inspection: pinned native `work/waffle/gpu/vendor/adreno_gen7_hwsched_hfi.c`, `get_mem_alloc_entry`, `process_mem_alloc`, `mem_alloc_reply` (approximately lines 1577–1748).

Result: this proposed mismatch is refuted by the source. Native `get_mem_alloc_entry` records the rounded size in its internal `entry->desc`, but `process_mem_alloc` copies only GPU address, GMU address and host handle into the request descriptor. `mem_alloc_reply` sends that request descriptor, preserving its original size. Do not change reply sizes on this premise. No driver code or hardware state changed.

This check does not prove that the port's backing allocation, permissions or contents match the native implementation. Those remain separate audit questions.

## Measurement limitations

- The existing ECATS request tests nonsecure privileged data-read translation. It does not prove successful CP instruction fetch, unprivileged access, writes, or actual memory contents as seen by GPU DMA.
- No saved postpublication SMMU fault is not evidence of no fault if the CPU/reset path prevented capture.
- Source history must include untracked working files and diagnostic snapshots; the current Git history alone does not describe the GPU experiments.

## Next audit work

Finish source/dependency review, reconstruct failed experiment variants, compare native and port allocation/mapping contracts, and publish the component status matrix. Select at most three blocker hypotheses after this review, with one discriminating experiment and explicit expected outcomes. The phone is not required for this work.

## 2026-10-31 — audit dossier and independent trace comparison

Detailed findings, component status matrix, history, three bounded blocker hypotheses and the proposed first hardware experiment are now in `work/waffle/gpu/forensic-audit/AUDIT.md`. Structured report chronology is rendered in `HISTORY.md` in the same directory. Scope limitations and unavailable primary reset evidence are explicit.

E01 (offline, no driver changes): compare the actual eleven logged words of test94 CP_INIT against independent native `gen7_hfi_cmdq_write` captures. Expected: a mismatched non-address payload word would justify investigating encoding. Observed: 10 complete native CP_INIT records, zero mismatches after normalizing only header sequence and restore VA. Disposition: reject a simple payload-word mismatch for these records; this does not validate restore contents or actual memory access. Do not repeat packet editing without new evidence. This is forensic confirmation, not a new hardware milestone.

E02 (offline, no driver changes): scan every saved test94 kernel log rather than one selected snapshot. Observed: 88 files, four unique checkpoints (0–3), no saved RAW ACK. Disposition: last observable boundary confirmed; reset location remains ambiguous. No claim that absence of a captured fault means absence of a fault.

Compared build source snapshots93/94: 12 differing files, full diff saved in `source93-vs94.diff`. This prevents assuming the pair differs by a single CPU write. Freeze recheck: zero changes among 31 production files. No kernel build was needed because production code was unchanged.

Hypotheses: H1 required access-type translation/permission failure (provisional priority); H2 an unidentified native GX/CP startup prerequisite; H3 reset at RAW publication/handling with incomplete phase capture. Evidence, falsification criteria and remaining uncertainty are in AUDIT.md. Existing results already reject simple delay-only, sequence-only, TG1-only, AP-only and clock-profile-only explanations as sufficient fixes.

First proposed hardware experiment: prepare-only cycle with access-mode ECATS matrix for real mapped buffers, no CP RAW. Exact native access metadata review remains necessary before implementation. Offline review proves the old preflight tests only privileged nonsecure data reads; it does not prove H1 caused the reset. This experiment is not implemented, built or run yet. Phone remains unnecessary for the current review.

Reviewed native crashdumper source at the pinned OnePlus commit as a potential independent DMA route. It uses GPU VA and has no established pre-CP guarantee in the available evidence; do not replace the blocker with an unvalidated crashdumper launch.

No new failed hardware experiments during this audit: 0. The earlier many unsuccessful RAW variants require architectural review before another RAW attempt; a fresh session does not erase their negative evidence.

## Anti-loop rules

Record each experiment with evidence, expected result, observed result and disposition. Do not repeat a refuted change without new evidence. After three inconclusive hardware experiments, stop hardware iteration and revisit architectural assumptions. Compilation alone cannot mark a hardware stage complete.

## 2026-10-31 — E03 implementation, hardware pending

User requested continuous work and confirmed that phone access is available. Audit baseline is preserved on `waffle/gpu-forensic-baseline-20261031` (baseline `441a407`, debug-log follow-up `94bd0fc`). No production files were changed before the forensic review and initial plan were presented.

The selected H1 experiment now has a bounded implementation: optional `waffle_ecats_access=1`, accepted only with prepare-only probe93. Ordinary probe93 retains its previous selection. RAW paths and CP payloads are unchanged. The callback records actual successful nonsecure GPU START allocations while preserving their existing permission updates. The access matrix runs only after successful GMU stop/TCM restoration, with CM3 reset, GX off and QTB halted, while GPU page tables and allocations are still retained. It does not halt QTB while GMU queues are live.

It checks the first/last pages of SQE/AQE using unprivileged data/instruction reads, restore using privileged data read/write, and real HFI allocations using their requested privilege/write flags. Instruction mode is additional coverage, not an assertion about the closed firmware's actual transaction classification. No secure access requests and no actual memory transfers are added. The first failed translation ends the matrix, with OUT/FSR/FAR recorded before the existing cleanup.

Host test executes actual production code against pinned native ECATS encoding and simulated faults. Passed checks include encoding, real allocation modes, missing readiness, wrong PA, timeout, first-failure stop, range rejection, descriptor capacity and original privileged-read encoding. A pre-existing host extractor needed a boundary update after introducing the parameterized helper; its actual permission tests pass again. These are software results only. Full XNU/EFI/container build is in progress under `diagnostic-gpu-ecats-access`; hardware result is still pending.

Frozen pre-audit source hashes are intentionally retained as the immutable historical baseline. After this entry, changes in the scoped SMMU diagnostic, loader token policy, runner and build/test integration are expected; rerunning the original freeze assertion is not a hardware verification.

## 2026-10-31 — E03 hardware PASS, H1 narrowed and rejected

Run `work/waffle/runs/20261031T083550Z`, variant E03 on prepare-only probe93. Actual result: `ACCESS_MATRIX result=1 checks=27 allocations=8`; every recorded PA matched, every fault mask was zero, unprivileged instruction/data reads and privileged writes included. No RAW checkpoint/CP_INIT_RAW occurred. Full stop/PLL restoration completed. Runner exit0 and Android boot completion confirmed, independently rechecked with ADB `sys.boot_completed=1`. Detailed parsed evidence: `work/waffle/gpu/forensic-audit/E03-result.json`. Implementation commit `71061fc`; verified pretest archive SHA256 `da223b9042354572ca8ac3086d6e68cd7a6234c9b2b651b2b13fbb8b0527201b`.

Disposition: reject H1 for the tested nonsecure page edges/access modes after GMU stop. Do not repeat an AP/TG1/ECATS permissions fix without a new counterexample. This does not prove live GPU DMA, coherency, secure access or CP execution. No failed hardware experiments in the new audit series. H2 (native CP prerequisites) and H3 (publication/firmware failure boundary) remain active. Phone returned to Android; no new RAW test queued.

## E04 — native cold HFI trace; touch regression reported

RAM-booted the preserved native boot image with only tracing cmdline changed (kernel/ramdisk unchanged). Captured 272 HFI writes, 15 allocation replies and first native CP_INIT return0 with TRUST1/zap_loaded0. Android boot_completed1; wfc probes removed after collection. Artifacts: forensic-audit/E04-native-cold-hfi. This is default native preemption-on profile, not the port optional-off profile. No inference that allocation-count differences are bugs.

User then reported nonworking touch. Root cause is unknown; do not declare this RAM image a fully working phone baseline. Immediately issued ordinary adb reboot to restore the installed Android boot path. No flash/write of boot partitions occurred. Recovery and touch confirmation pending; pause GPU experiments until phone usability is restored.

E04 recovery: ordinary Android boot_completed1, temporary kprobe cmdline absent, touchpanel input node registered. User explicitly confirmed touch works again. Do not repeat the E04 temporary boot image until its touch regression is understood. Continue analysis of saved trace without further phone reboot.

## E04 comparison completed — no allocation fix justified

The actual cold native replies now independently confirm the earlier source reading: kind3 size remains24 and host_handle echoes gmu_handle. Across ten common allocation kinds, flags and alignment agree with the port. Kind4/5 context records are14630912 native vs3657728 port, kind7 counter16384 vs4096, native has five kind1 rings and additional kind25 AQE sandbox. Native preemption/LPAC/DMS/IFPC are enabled in this capture, so these differences do not establish a bug in the optional-off port. Parsed comparison: E04-native-cold-hfi/allocation-comparison.json. No new code change justified.

Read-only comparison of installed active boot_b prefix (38293504 bytes) matches the preserved original image SHA256984fbe6ab6f3971487e6e5f7351e0cbd89c9ff213437c9b8d3a25e9964a15129. A stale saved boot image does not explain the touch regression. The exact regression cause remains unknown; no repeat boot planned.

Next H2 measurement must distinguish translated addresses from actual DMA. Native crashdumper CD_READ/CD_FINISH use GPU VAs and writeback markers, but available source does not establish that the engine operates before CP_INIT; a timeout would therefore be ambiguous. Do not implement a speculative crashdumper launch as if it were an established independent memory test. H2/H3 remain open, no RAW queued, phone in ordinary Android with user-confirmed working touch.

## Further H2/H3 source review and available diagnostics

Pinned Linux reference downloaded with provenance: linux-a6xx_gpu_state.c, linux-msm_gpu.c (linux-next2506121f625586726f593dc5e726248cdcf5e7fe). Snapshot does halt SQE before crashdumper, but additionally requires !gpu->needs_hw_init. msm_gpu_hw_init clears needs_hw_init only after funcs->hw_init succeeds. Therefore halting SQE is not sufficient evidence of crashdumper support before first CP init. Do not treat this route as a qualified pre-CP DMA test. No diagnostic hardware experiment added.

Read-only live Android inspection found /proc/tzdbg (not the assumed debugfs path). Saved general/reset/boot/hyp_general/vmid and hashes under forensic-audit/live-tz-readonly. General/reset/boot/vmid explicitly return New Encrypted TZ Dialog, magic0x73d71034/version1. Pinned target-tz_log.c calls qcom_scm_request_encrypted_log and prints encrypted AES key material, nonce, tag and ciphertext. The printed Key field is not evidence of an available plaintext decryption key. No decoder/decryption capability for this device is established in the available sources. Current hyp S2 counter0 applies only to the current Android boot and must not be used to exclude a historical XNU fault. This does not independently establish the encoding of all older Sahara segments.

No further driver changes or phone reboots in this review. CP execution remains unproven. Current missing evidence is either a readable reset/fault record from the failing run, or an independently qualified GPU read/write probe before CP init. Do not compensate with another ungrounded RAW retry.

## E05 native physical clock measurement qualification

No XNU RAW launched. Qualcomm debug mux source and clk-debug.c at pinned kernel revision were inspected. Idle native clk_rate reported260MHz while hardware measurements returned0; these readings cannot establish running clock domains. The generic gpu_cc_gx_gfx3d_clk measurement returnedEINVAL; the actual selectable measurement target is measure_only_gpu_cc_gx_gfx3d_clk. Original and failed reads preserved under forensic-audit/E05-clock-qualification.

A bounded native measurement session temporarily set idle_timer1000000 and ifpc0, using stock sysfs paths and restoring originals via shell trap plus a separate host recovery. Native force_clk_on was NOT used: source rejects it under GMU. Three physical measurements: GFX3D230999764/230999908/230999468Hz, GMU260000552/260000256/259999232Hz. GX FF measured0, so no positive FF-clock conclusion. Original idle_timer80/ifpc1 restored, temporary debugfs mount removed, Androidboot_completed1. No reboot, no GPU-driver source changes. This establishes a native hardware-counter reference only, not actual XNU core frequency.

User additionally requested rebuilding https://github.com/oosexgang/hakios-uefi for waffle. Current pinned upstream HEAD687fa6c6a5a70f43184de92980e0a76eea5f2c4b, same as saved checkout. Its redwood diagnostic loader writes logdump and uses fixed payload placement; do not boot it unchanged on PJD110. Work continues in isolated work/waffle/mu-hakios, preserving original Mu tree.

## HakiOS UEFI for waffle — build completed, hardware pending

At user request, adapted current HakiOS UEFI HEAD687fa6c onto a separate copy of the already verified waffle Mu tree42fe563 plus existing platform fixes. This is an adaptation, not a pristine upstream e51cd base build. Original tree retained. Upstream stage0 redwood disk logger replaced with FV launch of existing RAM/USB loader; tested Boot iOS menu retained. HakiOS vendor/boot log/branding imported.

Build exit0; Androidbootv4/container/EFI/stockDTBs/XNU payload validation passed. Loader55808bytes byte-identical to prior E03. Board memory/config/DTB hashes preserved. BootShim machine code identical to original because no PAYLOAD_BASE is defined. Artifact work/waffle/hakios-uefi/HakiOS-waffle-PJD110-RAM.img; raw FD andSHA256SUMS alongside. Not hardware tested, phone not rebooted for this rebuild. Reproducible overlay source under uefi/waffle-hakios. No claim of GPU improvement from UEFI branding/boot changes.

## Automatic UEFI entry validated, E06 scoped clock experiment prepared

User explicitly requested operation without physical Boot iOS confirmations and authorized continued work while away. HakiOS waffle BootManager now calls the existing RAM/USB loader automatically unless the existing VolumeUp menu flag is set; loader return falls through to menu. Automatic entry was hardware verified, then the actual tools/run-waffle-auto.py boot/reboot cycle passed under auto-runs/20261031T093745Z: no physical selection, platformwaffle, Androidboot_completed1. No GPU commands in that validation. Existing pinned Sahara collector is used for prepare-test failures. No guarantee of recovery from every future fault, no flash operations.

E06 targets H2 actual running clocks, distinct from the passed E03 access translations. Native E05 measured GFX3D~231MHz andGMU~260MHz. E06 opts into waffle_gpu_measure=1 on preparation-only probe93. It reads the physical 4.8MHz debug counter via the native GPU/GCC mux chain. It changes debug selectors/dividers/enables only, not GPU frequency, power votes or CP packets. Native selectors GFX0xf/GMU0x1f, GCCGPU0x18d, divider2x2, samples0x1000/0x20000 are source-backed. All polls bounded40ms per sample; pre-existing active counter refused. Every touched writable field saved/restored with readback; unknown restoration stops with mappings/power retained for Android reset.

Expected discriminating result: running XNU GFX/GMU frequencies near native231/260MHz weaken a missing-clock explanation at this point; zero/unexpected GFX is a new concrete observation to investigate, not grounds for an arbitrary PLL write. A measurement failure alone does not establish clock failure. This does not test DMA or CP. Host tests passed units, valid selectors, zero clock, timeout and dropped writes/rollback. Full build pending under diagnostic-gpu-clock-measure. No hardware E06 outcome yet.

## E06 attempt1: physical clocks measured; overall test failed, Android recovered

Automatic run auto-runs/20261031T094238Z launched run20261031T094301Z without physical selection. Actual positive measurements: GFX231000348Hz (short49328/full1577003), GMU260000696Hz (short55509/full1774984), complete1/restored1. No RAW. Overall runner_exit1 retained because lifecycle markers missing from fetched log. Android independently boot_completed1. Do not label the whole experiment passed.

Two concrete diagnostic defects found: (1) new helper incorrectly paired ml_io_map with ml_io_unmap. XNU arm/io_map.c uses KMA_PERMANENT/io_submap for ml_io_map, versus KMA_DATA/kernel_map for ml_io_map_unmappable; machine_routines.c ml_io_unmap frees from kernel_map. Changed only these temporary mappings to ml_io_map_unmappable(VM_WIMG_IO) with round_page sizes. This source defect is consistent with stopping after the measurement output, but the first run's full panic/cleanup record was not retrieved, so do not assert a decoded panic cause. (2) completed kernel log was71702bytes, fetched kernel-final.log exactly32767bytes. oem log discarded the composed full kernel log and recreated it from the32KB console buffer. Loader now retains the completed kernel pointer/length until write_logs resets them and uses it for non-live oem log. Host test reproduces the actual71KB/32KB case and confirms final marker survives.

E06-r2 is a new diagnostic repair/validation, not a new CP hypothesis: separate artifact diagnostic-gpu-clock-measure-r2, original failed run preserved. Expected: same physical frequency result plus complete verified shutdown/PLL restoration in untruncated log. No GPU clock reprogramming or RAW added. Build in progress.

## E06-r2 hardware PASS: clocks and complete lifecycle verified

Run20261031T094701Z, automatic cycle20261031T094637Z. GFX231000200Hz andGMU260001136Hz, both complete1/restored1. Full shutdown markers now available: slumber/RSCsleep/GXoff/CM3reset/TCMrestore/context cleanup/PLLrestore and clockcontrolpassed1. Full log102404bytes retrieved instead of truncated32767bytes. Runnerexit0 and independentAndroidboot_completed1. NoRAW. Parsed result forensic-audit/E06-r2-result.json. Previous E06failure remains recorded.

Disposition: missing/misclocked GFX3D orGMU at this preparation point is not supported; do not repeat PLL frequency guesses without new evidence. This does not test clock transitions afterRAW, actualDMA, orCPexecution. One diagnostic attempt failed before the successful repair; no string of three unsuccessful experiments.

Next offline work: build Mesa QRisc disassembler from existing pinned local Mesa26.3.0-rc1 sources and inspect vendorSQE handlers THREAD_CONTROL/ME_INIT. No firmware modification or device execution planned by this tool build. Native tracing image with touch regression remains excluded.

## E07 plan — H2 missing LPAC bootstrap mapping (new source evidence)

Qualified local Mesa QRisc decoder matches its A7xx reference byte-for-byte. Vendor SQE SHA256 f756bafe5f69a87161c7c53385386374a791861a574c244e845baba677993842 was decoded without modification. BR bootstrap programs BV base=SQE+0xa800 and LPAC base=SQE+0x121c0, enables both, and waits THREAD_SYNC before its first PM4. LPAC bootstrap fetches its jump table at LPAC+0x29a0. This establishes a bootstrap dependency; the decoded instruction stream alone does not prove which stream SID actual fetches use.

Pinned kgsl_iommu.c iommu_probe_user_context sets up gfx3d_lpac and its TTBRs/aperture independently of workload lpac_enabled. Global mappings are mirrored into that domain. Native saved routing is SID0/CB0, SID1/CB1, SID2/CB2, SID5/CB3. Port instead uses CB1 for GMU and has no SID1 route. This is a new H2 prerequisite candidate, not a repetition of E03's SID0 access tests and not a proven reset cause. H1's tested SID0 modes remain rejected; H3 remains open (maximum three hypotheses unchanged).

Minimal experiment: optional waffle_lpac_map=1 on prepare-only93. Move GMU SID5 to native CB3, add SID1/CB1 with the existing normal table root and native split TTBR geometry, configure source-backed LPAC SCM aperture selector1/bank1. With QTB halted and engines reset, translate both ends of BR/BV/LPAC code and jump tables through SID1, checking actual PA and fault registers. Keep LPAC mapping through ordinary GMU preparation/shutdown, then restore all owned contexts. Never submit RAW or enable LPAC workloads. Expected pass: routing and all translations match, GMU full lifecycle and Android recovery pass. Such a pass validates the missing mapping's implementation only; confirming causality requires a separately justified CP experiment.

E07 implementation complete: actual context host tests now cover SID1 refusal when legacy GMU owns CB1, native relocated GMU isolation, distinct LPAC ASID2, native split TCR, and rollback. SCM harness compares both user and LPAC descriptors to pinned native C, including busy/failure cleanup. Full existing host suite, XNU/EFI/container build and embedded-loader/DTB/payload validation passed. Artifact diagnostic-gpu-lpac-map-e07; source snapshots agree with source and compiled XNU tree. Still no E07 hardware result. The LPAC translations exercise only immutable SQE pages; HFI pool AP changes have no cached LPAC entries in this preparation-only test. Future LPAC DMA would need invalidation for its ASID on shared-table changes before any such execution.

## E07 hardware control passed; runner classification defect retained

Run20261031T100057Z, automatic cycle20261031T100034Z: SID1/CB1 enabled, all42 SQE-page unprivileged data/instruction ECATS checks match PA without faults, LPAC SCM selector1/CB1 status0, user selector0/CB0 status0. GMU full lifecycle passed, LPAC restored1, NATIVE93 clock control passed1. No RAW. Android independently confirmed sys.boot_completed1. Original runner_exit1 remains because old literal CB0 text matcher rejected the added selector field, not because hardware validation failed. Fixed matcher accepts both explicit selector0 and legacy CB0, never selector1. Re-executed the actual entire final-result validation block offline on the complete saved log: passed. Evidence forensic-audit/E07-result.json. No hardware rerun justified solely for text matching.

E08 proposed causal test (H2 LPAC bootstrap): same known94 full native CP_INIT packet/clock lifecycle, with only the now-validated LPAC mapping/aperture and native GMU bank placement. First add LPAC-ASID invalidation for shared HFI page permission changes; otherwise a running LPAC engine could observe stale shared-table entries. Host test must cover both ASIDs and failure at either invalidation. The E07 translation control does not establish CP execution. Expected confirmation: actual CP_INIT_RAW ACK plus native idle/full collapse, not merely successful publication. Expected rejection of sufficiency: another900e/noACK despite established mapping. Do not repeat this combination unchanged if rejected. Arm standard collector, RAM-only, return Android and verify. No arbitrary PLL, firmware patch, packet or HFI feature changes.

E08 implementation/build: native LPAC mapping/aperture is unchanged from passing E07. Added guarded LPAC ASID2 TLBI alongside user ASID1 during shared HFI page permission updates, tested user/LPAC failures leave invalid PTE and stop. Default flag-absent path unchanged. CP94 packet, HFI features and frequency settings unchanged. Full host suite/XNU/EFI/container validation and current source binding passed diagnostic-gpu-lpac-cp-e08. Dedicated automatic option --lpac-cp-init requires --lpac-map and excludes prepare/matrix/clock modes. No E08 hardware result yet.

## E08 hardware PASS — first XNU CP_INIT ACK

Run20261031T100500Z, auto20261031T100436Z. Same existing94 full CP_INIT packet now reaches checkpoint4-doorbell-sent and5-first-poll-done. Actual response: CP_INIT_RAW ACK matched seq42 value00000000 valid1; Gen7 polled CP start result0/detail0/phase3/ACK1, polls1. LPAC42 translations passed, slumber43 ACK0, RSCsleep/GXcollapse/CM3reset/TCMrestore/LPACcontextrestore1/PLLrestore and NATIVE94 clockcontrolpassed1. Runnerexit0, automatic cycle success, Android independently boot_completed1. No900e, no draw, no ZAP or frame claim. Evidence E08-result.json.

H2 supported: the missing LPAC bootstrap mapping/aperture, native GMU bank placement and required second-ASID invalidation together remove the previously reproducible CP_INIT failure. This run does not isolate which member of that prerequisite set is individually necessary; do not claim a directly decoded SMMU fault or exact single-register cause. This is the first successful XNU CP initialization, not a complete GPU driver. Preserve this exact working image/source before any follow-on experiment. Next: one unchanged positive reproduction after Android reset, then independently verified GPU memory writeback before drawing/iOS integration.
