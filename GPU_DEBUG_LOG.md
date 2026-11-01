# Current verified result: E21 compute shader

Adreno 750 executed an eight-invocation compute shader under XNU and wrote 0–7 to the output buffer. All 4,096 words, including commands and guards, matched. The prepare-only control passed separately; both runs shut down cleanly and returned to Android. This does not establish an image or GPU rendering of iOS. See [E21 evidence](work/waffle/gpu/forensic-audit/E21-result.json).

Historical audit and experiment records follow.

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

## E08 unchanged reproduction PASS

Second run20261031T100701Z, auto20261031T100636Z, separate copy diagnostic-gpu-lpac-cp-e08-repeat preserves original artifacts. Kernel/EFI/boot image byte-identical. Again CP_INIT_RAW seq42 ACK0 valid1, Gen7result0, LPAC42 translations, full shutdown/PLL restoration. Runnerexit0/autosuccess/independentAndroid1. Two successful CP initializations across separate Android resets. This checks unresolved reproducibility of the first-ever positive execution result; no extra negative variant was run. Evidence E08-repeat-result.json. Exact working source/evidence checkpoint c81360d before this reproduction.

Next prerequisite review: pinned kgsl_util.c GPU_PASID13 -> reserved zap-shader DT region, qcom_mdt_load -> qcom_scm_pas_auth_and_reset -> native CP_SET_SECURE_MODE(0) for loaded ZAP. Existing waffle_zap.h is an offline ELF/metadata parser only; no runtime PAS loader exists. Saved vendor gen70900_zap.mbn is present (SHA8e454000fd86f74818917d34d46baa70a31360d81d9617015a02de4e00c0e397), 1072byte payload/4044byte metadata/reloc4096, reserved DT8192bytes at0x9b09a000. Do not write that physical reservation until loader memory ownership and map attributes are established. Do not switch TRUST directly as a guessed bypass: native direct path is only for !zap_loaded. GPU memorywriteback remains untested, and the precise security/access contract must precede it.

## E09 plan — authenticated ZAP and native unsecure transition

Current blocker is a missing implementation after now-confirmed CP_INIT, not a new failed-hardware hypothesis. Three DTBs agree reserved no-map ZAP0x9b09a000/8192bytes; UEFI PIL_Reserved and loader reserved subtraction exclude it from XNU allocation. Map only its containing16KiB IO page as WC; write exact1072byte payload at offset0x2000. Native metadata is ELF148+hash3896=4044bytes, physically contiguous aligned NC buffer. Live SCM node has no explicit clocks/interconnects, matching optional-null platform resources.

Scoped E09 option on94 with mandatory LPAC: repeat proven CP_INIT, PAS13supported query, native INIT_IMAGE0x42000201/arginfo0x82, MEM_SETUP0x42000202/3 forreservedbase/4096, payload copy, AUTH0x42000205/1, then native3word RAW CP_SET_SECURE_MODE0 seq43 and poll idle/read TRUST0; slumber uses44. No drawing or memorywriteback yet. Exact binary signature is validated by PAS, not by the offline ELF parser. On unexpected SCM/WAITQ or post-init failure, retain metadata/mappings and all live GPU resources until Android reset. This port has no WAITQ continuation support; do not treat such an outcome as signature failure. Expected success: explicit transport/service0, secure-switch ACK and TRUST0, full shutdown/Android1. No change to E08 absent the option.

User paused work («стопай пока что»). E09 remains plan only, no runtime source changes/build/phone commands for E09, no experiment queued. Preserve E08 and await explicit resume.

## E09 implementation and build complete — hardware pending

User explicitly resumed after pause. Added waffle_zap=1 only with94+LPAC, rejected missing/duplicate/wrong-value tokens. Existing E08 absent flag unchanged. Header waffle_zap_load.h executes native PAS13 order with INIT_IMAGE arginfo0x82, MEM_SETUP4096, exact payload copy, AUTH; retained state after INIT submission. Runtime uses contiguous16KiB metadata NC/WC alias, native reserved ZAP region mapped within containing16KiB, copies only after MEM_SETUP, native CP_SET_SECURE_MODE0 packet seq43; slumber44. No draw/writeback commands. Signature auth is PAS-owned. PAS uncertain/WAITQ or switch failure retains resources and returns to loader. On success metadata16KiB intentionally retained until Android reset (no speculative reuse).

Actual host orchestration tested all transport/service failure stages, payload ordering, invalid input, and secure-switch PM4 parity against pinned native encoder. ELF truncation/header tests and entire existing suite passed. Full XNU/EFI/container validation and compiled-source binding passed diagnostic-gpu-zap-e09. No E09 hardware outcome yet.

## E09 hardware PASS — signed ZAP and native secure transition

Run20261031T102106Z/autocycle20261031T102042Z. CP_INIT42 ACK0; PAS13 supported1; INIT_IMAGE/MEM_SETUP/AUTH transport0 service0;1072byte reserved payload readback1. ZAP signature authenticated by PAS. CP_SET_SECURE_MODE seq43 ACK0 valid1, actual TRUST0. Slumber44 ACK0, fullGX/CM3/TCM/context/PLLcleanup and NATIVE94pass. Runner0/autosuccess/Androidboot_completed1. No900e; no draw/writeback tested. EvidenceE09-result.json. Keep exact successful artifact immutable.

E10 planned independent execution result: optional dedicated16KiB GPU-only writable BO at unused lowVA0x80074000 (compactalias offset0x474000, inside existing20MiB layout). Before firmware start initialize/clean allocation; later use NC alias, sentinel guards and initiallyzero marker. After verifiedCP_INIT+ZAP/TRUST0 send native CP_MEM_WRITE four patterned dwords plus CP_WAIT_MEM_WRITES viaRAWseq44, require ACK0/idle and CPUactualmemorymarker with allotherwords unchanged. Slumber45. No shader/draw, no userspace integration. Never declare ACK alone a memorywriteback pass.

E10 implementation: dedicated16KiB writable GPU-only region at0x80074000, inside existing compact alias window with no address policy expansion. CP_MEM_WRITE4dwords+WAIT_MEM_WRITES seq44, slumber45. CPU writes only zeros/guards beforehand, confirms initial contents, polls NC marker and compares all4096words afterwards. Unsafe ACK/idle failure retains alias/resources. Actual helper host test simulates transfer absent despite ACK, guard corruption, unrelated-word corruption, ACK/idle failures and preflight refusals; native packet parity matches pinned encoder. Initial host harness lacked the region.address field and correctly blocked build before XNU; repaired harness and preserved failed build transcript. No E10hardwareyet; full build in progress.

E10 fullhost/XNU/EFI/container/current-source-binding passed. Corrected hostharness field, no production workaround. Original E09 option remains accepted alongside E08/E10. User reconnected phone, AndroidADBvisible. Next E10hardware; no result yet.

## E10 hardware PASS — first independent GPU memory result

Run20261031T102517Z/auto20261031T102453Z. CP_INIT42/ZAP43 passed; dedicatedBO VA1ff8000474100 PA8d15ac100 initiallyzero marker/two guards. GPU_WRITEBACK44 ACK0, CPU NC reads57414646/4c454750/13579bdf/2468ace0. All4096words checked, wrong0:4092other words unchanged. This establishes actual CP memory execution and GPU->CPU visibility for this NC buffer, beyond ACK/ECATS. Slumber45/fullshutdown/PLLrestore passed, runner0/autosuccess/independentAndroid1. No900e. No rasterization/shader/frame yet. Exactimage kept diagnostic-gpu-writeback-e10; evidenceE10-result.json.

Next E11 narrow contract: GPU command-buffer fetch via native CP_INDIRECT_BUFFER_PFE0x3f, containing exactly the already-proven memorywrite+wait stream at offset0x400 of the sameBO, with marker at0x100. This adds GPU read of a CPU-populated PM4 buffer; all output and command words/guards must match. Native PM4 header encoder/source and existing macan ring submit confirm3word IB addresslo/hi/count. No IOKit ready flag or Mesa switch until this contract and persistent power/map/fence lifetime exist.

## E11 implementation — command-buffer fetch, hardware pending

Optional waffle_ib=1 requires94+LPAC+ZAP+writeback. SameBO/initialmarker/guards, exact E10 PM4eightword stream staged atBO+0x400 (GPU VA1ff8000474400); RAW44 carries only native CP_INDIRECT_BUFFER_PFE addresslo/hi/count8. Existing direct E10 selected without option. Full4096word check includes unchanged staged command words. Host test exercises actual production helper both modes; simulated GPU in IB case fetches actual staged commands, native encoder verifies opcode0x3f/count3, all transfer/guard/ACK/idle negative cases retained. No Mesa/IOKit-ready flags changed.

E11 fullhost/XNU/EFI/container/current-sourcebinding passed diagnostic-gpu-ib-e11. Native0x3f/3 PM4encoder verified; preservedE10 andE09 options. NoE11hardwareyet.

## E11 FAIL with first precise actual IB permission fault, Android recovered

Run20261031T102838Z/auto20261031T102814Z: CP_INIT/ZAP passed; after IB44 doorbell, SMMU bank0 FSR00000408 FAR1ff8000474400 FSYNR000190003/0 stream0. Pinned arm-smmu.h FSR_PF bit3 is set; FSYNR0_WNRbit4/PNUbit5 are clear: unprivileged read at exact IB VA. Port diagnosticBO PTE AP_UNPRIVbit6 was absent. Readonly microcode has that bit, but this new writable BO was inadvertently still privileged-only. Actualread fails before memorywriteback; no900e, resourcesretained and Android1/runner1. EvidenceE11-result.json. This is a new observed transaction on a new BO, outside E03's rejected SID0microcode/oldallocations scope; not a speculative repetition of old permission fixes.

E11-r2 minimal fix: only the dedicated writable diagnosticBO receives native AP_UNPRIV in both low and compact aliases. Restore/HFI/default writable mappings stay privileged-only; SQEreadonlypermissions unchanged. Same packet, VA, clocks, ZAP, IB contents and guards. Host actualmapper compares full native read/write unpriv PTE and verifies other roles. Expected: same IB44 now writes marker, all4096wordsguardsmatch; if not, inspectnewfault and do not expand permissions blindly. One failed currenthardwareexperiment.

## E11-r2 hardware PASS — exact IB permission cause confirmed

Run20261031T103147Z/auto20261031T103122Z: unchanged CP/ZAP/IB packets and identical GMU implementation; only dedicatedBO AP_UNPRIV changed in both aliases. GPU_IBresult1 command_words8, GPUactualmemoryfourwords matched, all4096wordsincludingcommandbuffer unchangedexceptexpectedresult, wrong0. No SMMUfault/unsafe marker. Slumber45/fullshutdown/PLLrestore; runner0/autosuccess/independentAndroid1. No900e. This confirms E11 failure cause for the new IB BO: missing AP_UNPRIV for actual unprivileged command fetch. Original E11failure remains preserved; unrelated mappings were not relaxed.

Current verified chain: native clocks/GMU -> CP_INIT -> signed ZAP/PAS13 -> native secure switch/TRUST0 -> actual GPU PM4-buffer fetch -> GPU result write -> CPU coherent NC readback -> complete shutdown. This is not a rasterization or iOS acceleration claim. IOS-GPU-INTEGRATION.md maps existing service/Mesa APIs and remaining persistent-resource/fence/backend work. No further hardware test queued after E11-r2, phone ordinaryAndroid.

## E12 plan — owned submission session, bounded lifetime across init return

Current next blocker is ownership, not failed boot: existing stack plan/page tables and AOP mutex scope cannot survive a naive keep flag. Scope E12 to a heap-owned submission session while the outer verified diagnostic still owns all GMU/SMMU allocations. At authenticated ZAP/TRUST0 create session+NC BO mapping, transfer the currently-held OOB to it, return from gpu_power_probe WITHOUT OOB release, then submit three uniquely numbered IBs from a different caller. Each writes a distinct fourword token and verifies all4096words; sequence44/45/46 and completionfences1/2/3. Two bounded pauses check power ownership across calls. Close requires all completions and idle before releasingOOB, slumber47 follows, destroy only after all six existing stop-evidence bits. Any uncertain publication poisons session and retains resources until Android reset.

This is a necessary bounded ownership prototype, not persistence through iOS startup or a production user queue. Existing E08/E09/E10/E11 options retain their behavior absent waffle_session=1. No IOKit/Mesa-ready flags change. Host actual-code tests will cover ownership transfer, outstanding/poisoned-close refusal, stale/missing results, distinct fence tokens, partial init cleanup and destruction-before-stop denial. Hardware expected result: three independent GPU markers/ACKs, no reinit between calls, OOB released once, full shutdown and Android1. No new failed hypothesis loop.

E12 implementation/fullhost/XNU/EFI/container/current-sourcebinding passed. Actual-code tests cover all18 scenarios including stalefence token, missing transfer, guard damage, ACK/idle/powerfailure, safe deadline refusal and all6 destruction gates. NormalGX ownership test nowalso verifies intentional OOBhandoff withoutrelease. No E12 hardware result yet. Session isheapowned but still borrows the live outerdiagnosticplan; it is not valid to expose to iOS after that owner returns.

## E12 hardware PASS — owned OOB/BO across init return and three submissions

Run20261031T104031Z/auto20261031T104007Z. Heapowned session opened afterCP42/ZAP43, OOB transferred to session as gpu_power_probe returned. SESSION_IB44/45/46 ACK0, fences1/2/3 each produce distinct expected4wordmarkers, all4096wordsverified percall wrong0;1s pauses between calls. OOBreleaseonce afterallcompletion, slumber47 ACK0, six stop-evidence gates thenalias/heapfree; fullGMU/TCM/SMMU/PLLrestore. Runner0/autosuccess/independentAndroid1. No900e/faults. Still bounded insideouterdiagnosticowner, not iOSpersistence. EvidenceE12-result.json.

Next E13 justified ownership refactor: saved GMU register/RSCPDC/liveboot state remains in boot_probe stack. Extract begin/finish using an explicit context, heapowned for E12 session path, preserving the same setup constants, command sequence, stop gates and failurecleanup. No new hardware programming/commands or service exposure. This is necessary to let init return with a valid GMU owner; outerTCM/SMMU/AOP lifetimes remain subsequent boundaries. Validate fullhostsuite, actual ownership/failure-order hostchecks, then unchangedE12hardware control on newcode. PreserveE12original.

E13 implementation scoped to oldboot_probe only: explicitcontext captures savedregisters/RSCstate/liveCPstate/stop-evidence/aliases and inputs. gmu_boot_begin returns before session's three IBs; gmu_boot_finish performs identical slumber/reset/drain/restore. Sessionpath storescontext inheap, default93stackcontext remains supported. Initialization flag marks savedstate before setup writes; QTB resume refusal restores without releasingCM3. Early pre-setup failures retain old cleanup paths; unknown post-start failures keepowner/aliases. Code beforeoldboot_probe and fromTCMfunction onwards byteidentical toE12; setupconstants exactmatch (scopeauditJSON).

Actual begin/finish/wrapper host test covers19 startup/cleanup/failure scenarios each in stack93 and heap94 modes, with snapshot read in a separate finishcall, partial failurecleanup, sessionreturn sequencing, and unsafe-stop ownership retention. Harness corrections were prototype linkage and the expected pre-session slumbersequence45 vs post-session47; no production workaround. RSC/session/previoushosttests passed. Fullbuild pending diagnostic-gpu-gmu-owner-e13, noE13hardwareyet.

E13 fullhost/XNU/EFI/container/current-source-binding passed. First hardware control: stack/default prepare93+LPAC (noRAW), then only after Android recovery heap/session94 with unchanged threeIBs. This covers both affected lifetimes of the scoped refactor. No E13hardware outcome yet.

E13 defaultstack93 controlPASS run20261031T104701Z/auto20261031T104637Z: LPAC42/noRAW/fullGMUstop/context/PLLrestore, runner0/autosuccess/Android1. No regression seen in default prepare-only path. Next heapowner94sessioncontrol, sameartifact/IBsequence; no resultyet.

## E13 hardware PASS — explicit GMU begin/finish owner

Default93control run20261031T104701Z passed. Heap94session run20261031T104800Z/auto20261031T104736Z: gmu_boot_begin returnedwithheapowner retained, sameIB44/45/46 uniquefences/markers all4096wordswrong0, slumber47/fullstop, ownerreleasedafterfinishresult1, TCM/context/PLLrestore. Runner0/autosuccess/independentAndroid1. No900e. Confirms relocated GMU state survives beginreturn without breaking stop or defaults. EvidenceE13-result.json; no new commands/clockchanges. Next unresolved owner boundary: TCMbackup/lifetime and outerplan/SMMU/clock/AOP roots, so no productionready claim.

## E14 component ownership — TCM and GMU start return to parent

Next documented E13 boundary was TCM lifetime. Implementation now adds opaque waffle_gmu_owner begin/exercise/end, called directly from SMMU parent for the existing session option. Begin owns heap GMUcontext plus32KiB TCMsnapshot and returns live with OOB/BO; parent then invokes exercise/end as separate APIcalls. End verifies childcompletion, slumber/reset/drain, restoresTCM and onlythenfrees snapshot/rootowner. Existing defaultTCMdiagnostic uses extracted load/restore helpers and oldbootwrapper. CM3reset is explicitly checked before restoring TCM; failed restoration retains snapshot rather than freeing uncertain ownership. No new PM4/HFI packets or power writes beyond alreadyverified E12sequence.

ActualTCM/component API host tests cover overlapping firmwareblocks, partial/fullsnapshotrestore, malformedinput/map/allocationfailure, parenthandoff and constructorrollback, liveCM3/failedstop/failedrestoration retention. Removed unused local leftover from extraction; no behavioral workaround. ExistingGMU/session/RSCactualtests pass. NoE14hardwareyet. Outerplan/SMMU/clock/AOP ownership is still a live parent requirement; no iOS/userqueue exposure.

E14 fullhost/XNU/EFI/container/current-source-binding passed. New TCMhost tests execute actual helper and publicowner API; default/full snapshots, constructorfailures, separateparentcalls and failure retention allpass. Firstdefault93control (noRAW), then session94afterAndroidconfirmation. NoE14hardwareyet.

E14 default93controlPASS run20261031T105523Z/auto20261031T105459Z: newTCMhelpers restoreall32KiB/readbackmatches, noRAW/fullGMU/SMMU/PLLcleanup, runner0/autosuccess/Android1. Next fullcomponentowner94 returnedtoSMMUparent, sameartifact/3IBs.

## E14 hardware PASS — GMU/TCM component returns live to SMMU parent

Default93control run20261031T105523Z passed. Fullsession run20261031T105658Z/auto20261031T105634Z: beginreturnsheapGMU+32KiBTCMownerlive intoSMMUparent; parentcalls exercise/end. SameIB44/45/46 uniqueexpectedmarkers/all4096wordswrong0 each, slumber47/allstopgates, full32KiB TCMrestorereadbackmatches thenownerfree. SMMUroots/pools/PLLrestored, runner0/autosuccess/independentAndroid1. No900e/fault. E14-result.json and scopeaudit preserveproof; preceding/succeeding GMUcode/CP/ZAP/IB implementations unchanged fromE13.

Verified boundary now includes a live GMU/TCM component owner returned across the parent API call, not just a local boot function stack. Still NO persistent iOS GPU backend, shader/draw, dynamic user BO mappings or IRQ recovery. Completion numbers are bounded kernel-test tokens after actual GPU readback, not an advertised userspace fence API.

Next E15 plan (not implemented): move SMMU parent plan/table/context/saved-route state and pool-permission callback storage into an explicit owner with begin/end before returning it to the board clock layer. Existing firmware_regions and protected_pool allocations stay retained until GMU component end plus context detach/TLBsync. Preserve constructor rollback and first-failure retention; do not expose an IOKit-ready flag. Then boardclock/CX/AOP ownership must be separated: current AOP transaction holds macan_aop_mailbox_lock around the GPU callback and sends ACDoff after it, so a naive keep flag is invalid. A single cold session per Androidreset is the only tested lifetime; reopening after RSCsleep without Androidreset remains unqualified. No new hardware run queued after E14; phone ordinaryAndroid.

## E15 plan — SMMU parent ownership across constructor return

Verified E14 leaf component still borrows the parent firmware plan, tables and allocation-permission callback from waffle_smmu_probe's stack. Scope E15 only to that parent: explicit owner contains the plan/table pool, user/LPAC context snapshots, GMU route saved fields, protected pool pointer, callback/matrix storage and live GMU child. Begin returns with child live; separate caller exercises and closes child before SMMU detach/TLB/pool cleanup. Heap owner for existing session mode, caller-owned fallback for default controls. No new packets, clocks, access rights or mappings. Missing child or uncertain detach retains ownership; never free parent while child can fetch.

Actual-code host checks must cover callback storage after begin returns, constructor failures/partial context rollback, child-before-parent stop order and TLB failure retention. Full build, default93/noRAW control then same three-IB94 session after Android confirmation. This is the next lifetime boundary, not an iOS-ready flag. Board clock/CX/AOP remain outside this scope.

E15 implementation: oldwaffle_smmu_probe onlysplit intoparentowner/begin/complete/finish/wrapper; allpage/context/ECATS/TLB/securehelpers and completeGMUimplementation unchangedfromE14 (scopeaudit). Ownerholds plan/pool/user+LPACsnapshots/GMUsavedroute/permission+matrixstorage/GMUchild. Constructorreturns beforeexercise; callbackpointer verifiedowned and realhostcallbackcalledagain afterreturn. Childendbeforeanydetach/free; lostchild/unknownstate or heapownerTLBfailure retainsrootmetadataandpages. Defaultcallerownedstackpath and accessmatrix remainavailable.

Host actualparentcode covered42 default/heap scenarios: constructorfailures, partialcontextsetup, callbacklifetime, livechilddetachmentrefusal, safe childexercise failure, unknownstop, corruptedcallback pointer and TLBtimeoutretention. Draft mechanical transformation was corrected to preserve struct/member identifiers; hostharness indentation warnings fixed beforefullbuild. No hardware attempts during draft. Relevantmapper/context/access/permissions tests passed. Fullbuild pending diagnostic-gpu-smmu-owner-e15. Nexthardware control93+LPAC+accessmatrix (testsnewmatrixcallbacklifetime), then same3IBsession94afterAndroid1.

E15 fullhost/XNU/EFI/container/current-source-binding passed. Firsthardware93+LPAC+accessmatrix noRAW exercises both parent-owned callback variants; full94session onlyafterAndroid1. NoE15hardware resultyet.

E15 default93controlPASS run20261031T111053Z/auto20261031T111029Z: accessmatrix27checks/8realHFIallocations, LPAC42checks, noRAW, fullTCM/SMMU/PLLstop; runner0/autosuccess/Android1. This exercises matrix callback data after SMMU constructorreturn. Next94heapowner/3IBsession only after confirmedAndroid.

## E15 hardware PASS — SMMU parent owner and callback survive begin return

Control93 run20261031T111053Z ACCESS27/alloc8/LPAC42 passed. Heap94session run20261031T111210Z/auto20261031T111146Z: SMMUbeginreturnedheap1/callback_owned1/livechild1, same3IB44/45/46 uniquemarkers/all4096wordswrong0, childGMU/TCMendedbeforecontextsdetach, rootownerreleased, PLLrestored. Runner0/autosuccess/independentAndroid1. No900e/fault. This removes constructorstack dependence for plan/table/context/callback storage within the bounded root wrapper; actual boardclock/AOP owners remain outside it. EvidenceE15-result.json. No shader/draw/iOS acceleration claim.

Publication completed at explicituserrequest: forkdefaultwaffle/gpu-bringup commit2558c8e126ab2d92f854fcf2239f7b90778ba664 includesverifiedE15code/evidence andEnglishcurrentstatus/milestonetable. BothREADMEintroparagraphs shownbyuserremoved. RemoteSHA/defaultREADME contentsverifiedviaGitHubAPI. Publishedsource matches E15snapshot; fourownershiphosttests also passed inpublicationworktree. MainGPUworkcontinueslocally; noE16implementationyet.

## E16 plan — live SMMU component returned to board clock caller

E15 source checkpoint86a7909 preserved. Current blocker: heap SMMU parent is closed inside waffle_smmu_probe; board code has no live component handle to retain. Hypothesis: an opaque begin/exercise/end handoff can preserve the verified child-first stop with callback/table storage intact after probe_smmu returns. Minimal experiment: expose existing session94 owner to probe_clocks, execute unchanged three IBs there, end before any PLL/clock/CX/AOP restore. No new GPU commands, mappings, permissions or frequencies. Default93 control plus accessmatrix/LPAC first, then session94 after Android confirmation. Host tests must exercise actual public API and clock caller order, duplicate-exercise denial, early-close cleanup, constructor rollback and uncertainty retention. This is not persistent board ownership or iOS rendering. No hardware E16 result yet.

E16 implementation scoped to public SMMU begin/exercise/end plus board caller handoff; internal SMMU begin/finish/mapper/context/permissions and entire GMU file byte-identical to E15 (scope audit). API returns live before exercise, denies repeated exercise, can close an unexercised owner; caller ends child before any PLL/clock restore. Existing42 parent scenarios plus direct public API and actual clock caller success/failure order checks pass with ASan/UBSan. Audit script initially matched the forward declaration instead of the function definition; corrected matcher confirms unchanged helper prefix. No hardware result yet. Full build running.

E16 full host suite/XNU/EFI/container and compiled-source binding passed. Prepared diagnostic-gpu-smmu-api-e16; next default93 LPAC/accessmatrix control before session94. Compilation is not hardware proof.

E16 default93 control PASS run20261031T200441Z/auto20261031T200417Z: ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/AOP restore, runner0/autosuccess/Android1. Next publicAPI session94 on same artifact.

## E16 hardware PASS — public SMMU owner returned live to board clock caller

Control93 run20261031T200441Z ACCESS27/alloc8/LPAC42 passed. Session94 run20261031T200543Z/auto20261031T200519Z: publicbegin returnslive through probe_smmu to probe_clocks; sameIB44/45/46 each all4096wordswrong0/distincttokens, endstopsGMU/TCM thenSMMUdetach/free beforePLL/clocks/CX/AOPrestore. Runner0/autosuccess/independentAndroid1; no900e. Scope unchangedGMU/internalSMMUhelpers. EvidenceE16-result.json. Next unresolved boundary: saved boardclock changes remain local to probe_clocks; CX/GCC/AOP transaction remains caller-scoped. No persistent iOS backend or draw claim.

## E17 plan — explicit board clock owner across begin return

Verified E16 checkpoint60a17c0 preserved. Remaining blocker: probe_clocks saved[16] rollback journal/count/flags are caller-local, even though child SMMU can return live. Hypothesis: moving that journal and child pointer into an explicit board clock owner allows begin to return live to CX caller and still stop child before PLL/clock restoration. Keep existing static native-clock callbacks/state (module-lifetime, serialized by one active owner); no claim of full board lifetime yet. Scope: split only probe_clocks into begin/exercise/finish plus wrapper, heap mode for existing94session, default caller-owned context, single-active-owner guard before writes. Unknown child/PLL/clock restoration must retain owner through reset. Same default93 control and threeIB94 hardware test. CX/GCC/AOP lifetime remains subsequent boundary. No E17 code/hardware pass claimed yet.

E17 implementation: explicit board_clock_owner owns14-entry clock journal/flags and SMMUchild; heap94 beginreturns live toCXcaller, defaultstackowner. One active owner guards existing module-lifetime native callbacks. Childend beforePLL/reversejournalrestore; unsafePLL/RCG restoration retainsowner/reset. No SMMU/GMU changes, no new programming constants; surroundingboardcode unchanged except two call names (scopeaudit). Actualhost tests pass legacyrollback, heapjournal afterconstructorreturn, duplicatebegin/exercise denial, allocationfailurebeforewrites, safechildfailure, and unsafePLLretention. Removed unused local from extracted finish before fullbuild. NoE17hardwareyet.

E17 full host suite/XNU/EFI/container/sourcebinding passed. Added explicit failed-RCG-restore retention case to actualclockhost (rerunPASS after fullsuite invocation, snapshottedcurrenttestedtest); both PLL and RCG unknownrestore retain metadata/reset. Next default93+LPAC+accessmatrix then94session afterAndroid1. NoE17hardwareyet.

E17 default93 control PASS run20261031T201004Z/auto20261031T200940Z: ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Next94heapclockowner session on sameartifact.

## E17 hardware PASS — board clock journal survives begin return to CX caller

Control93 run20261031T201004Z ACCESS27/alloc8/LPAC42 passed. Session94 run20261031T201108Z/auto20261031T201045Z: CLOCK_OWNER beginreturnedheap1/livechild1/journal14 toCXcaller; sameIB44/45/46 each all4096wordswrong0/distincttokens, SMMUchildendedbeforePLL/reverseclockjournalrestore, CLOCK_OWNERreleasedbeforeCXrestore, AOPcleanup. Runner0/autosuccess/independentAndroid1; no900e. No SMMU/GMU/commandchanges. EvidenceE17-result.json. NextCX/CFGowner thenAOPtransport/ACDlifetime perE18-board-lifetime-plan.md (planonly, notimplemented). No persistent iOS backend/draw claim.

## E18 plan — board power parent across return to AOP callback

E17verified8e138d9 preserved. Implement only existing94session heapparent for savedCFG gating/CXcollapse ownership and liveclockchild. Reuse existing power/cfg programming paths, optionalparent argument forCXpath; defaultcontrolsretain immediatecleanup. Parent returnslive throughprobe_gpu_body toAOPcallback; separateexercise/end closesclock/SMMU/GMU beforeacquiredCX/CFGrestore. IfCXalreadyon, do notcollapseit. Hostchecks coverpartialconstruction/defaultandborrowedCX/exactrestoredCFG/unknownchildretention. Same93controlthen3IB94. AOPstillscopedsharedmutex transaction; no persistentiOSreadiness. SeeE18-board-lifetime-plan.md.

E18 implementation: optionalheap powerparent onlysession94 captures CFGsavedbits/CXacquired flag/clockchild, existingCX/body paths reused. Returnslive toAOPtask; childfinishfree beforeacquiredCX+CFGrestore/rootfree. Already-poweredCX remainsborrowed and isnotcollapsed. Activeparent rejectsduplicatebegin beforewrites. EntireGMU/SMMU andE17clockhelpers/dispatch unchanged. Actualhost14scenariospassed mapping/allocation/powerfail/borrowedCX/CFGunchanged/duplicatebegin/childerror+unknownstopretention/AOPcallbackhandoff. Initialtest incorrectlyexpectedzeroallwrites whenCXunavailable despitelegitimateCFGacquire/restore; fixedexpectation,productionunchanged. Fullbuildnext; noE18hardwareyet.

E18 fullhost/XNU/EFI/container/sourcebinding passed diagnostic-gpu-power-owner-e18. Default93 control first then94session afterAndroid1. NoE18hardwareyet.

E18 default93control PASS run20261031T201618Z/auto20261031T201554Z ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Next94heappowerparent session on sameartifact.

## E18 hardware PASS — power parent retains CX/CFG across return to AOP caller

Control93 run20261031T201618Z ACCESS27/alloc8/LPAC42 passed. Session94 run20261031T201717Z/auto20261031T201653Z: POWER_OWNER beginreturnedheap1/clocklive1/acquiredCX1/CFGchanged1 toAOPcaller; sameIB44/45/46 all4096wordswrong0/distincttokens. SMMU/GMUstopped beforePLL/clockjournalrestore, clockownerfree beforeCXcollapse+CFGrestore, powerparentfree afterrestore beforeAOPoff/cleanup. Runner0/autosuccess/independentAndroid1; no900e. EntireSMMU/GMU/E17clockhelpersunchanged. EvidenceE18-result.json. BorrowedCXbehavior verifiedhostonly; hardware used acquiredCX1. NoiOSGPUrendering claim.

Next E19 planonly: explicitAOP/QMP/ACDowner withheapcallbackstorage and boundedper-message sharedmutexholds. Existingtransaction sendsACDoff aftercallback, so cannot retainboard byflag. Split channelbegin/end preserving existingguard/payload/restorebehavior; release sharedlock duringliveGPUwork, reacquire forvalidatedoff/channelrestore onlyafterpowerchildend. Hosttestswillneed constructorrollback/on-offreceiptfailures/busyforeignmessage/channelidentity/shortlockhandoff and sourceparity; then samecontrol93/3IB94. NoE19implementation/hardwareyet. No userspace readiness or renderer switch.

## E19 resumed — AOP channel/ACD ownership and short shared lock scope

Userresumed afterbriefpause; E18verifiedeaed2c9 preserved, phoneAndroidvisible. Firstprovenlifetimeblocker: transaction_run holds sharedAOPmutex around entireGPUcallback thenunconditionally sendsACDoff/closeschannel. Heapboardparent alonecannot survive callbackreturn. Hypothesis: explicitQMPbegin/end +heapcallbackstate, lockonlyduringtransport, canreturn fullGPUrootlive toinitcaller andperformunchanged3IB thenchild-firstshutdown/off/channelrestore. Default93 keepsboundedtransactionwrapper. ValidateactualQMPold-vs-newwrite/waittraceparity, partialconstructorrollback/on-offfailure/foreignbusyguard/lockavailableduringGPUwork, thenfullbuild93controland94session. No new PM4/HFI/powerconstants, no userspace readiness. Unknown childstop, sharedlockreacquire or transportrestore retainsroot/reset.

E19 implementation: splitQMPsessionbegin/end storesIOcallbackcopy, channelgeometry, changed/opened/onattempt/restorestate; oldtransactionwrapperusesbothwithsamecallbacktiming. HeapAOPowner holdschannel/IPCCmapping/transport/powerchild; beginunlocks beforepowerbegin andreturnslive toinitcaller; childexercise/end neverunderAOPmutex. Endclosespowerchild beforetrylocking/validatingchannelidentity+emptybox/off/restore/unmap/free. Unknownstop/busysharedlock/foreignpending/changedchannel/off-or-restorefailure retainmetadata/mappings andreset. EntireGMU/SMMU/power/clockhelpers unchanged. Actual22pinnedE18write/kick/wait/tasktracesandresults exactmatch;19actualAOPowner scenariosPASSincluding lockavailablefromseparateGPUcaller andretentiongates. Fixedhostassertion accidentallyincludingmode0success inzero-writefailcases; productionunchanged. Fixturepinnedsource+SHAprovenanceincludedsohosttestdoesnotrequireprivateGitcommit. Fullbuildnext,noE19hardwareyet.

Beforehardware, updatedrunvalidation fornewAOPowner markers: kernelstringidentifiesnewpath whileoldartifactssupported. ValidatorrequirescorrectGPUvaluesforall3fences, unlockedliveowner andstrictSMMU/clock/power/AOPteardownorder; missing/incorrect/reorderedmarkers andREBOOTREQUIREDrejectedbyactualPythonhosttest. LegacyAOPchannelstringsnolongerrequiredfornewpath. Fullbuildrepeatedtocapturecurrentrunner/builder/newhosttestintosourcebinding; nohardwareattempthasbeenmade.

E19 finalfullhost/XNU/EFI/container/sourcebinding passed includingrunneracceptancechecks. AutomaticRAMimageprepared. First93LPAC/accessmatrixdefaultcontrol then94heaptopowner sessionafterAndroid1. NoE19hardwareoutcomeyet.

E19 default93control PASS run20261031T204228Z/auto20261031T204204Z ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Next94heapAOPowner session on sameartifact.

## E19 hardware PASS — full GPU owner returned live with AOP mutex released

Control93 run20261031T204228Z ACCESS27/alloc8/LPAC42 passed. Session94 run20261031T204325Z/auto20261031T204301Z: AOP_OWNER heap1/powerlive1/mutexheld0/channelopen1 returned toinitcaller, same3IB44/45/46 all4096wordswrong0/distincttokens. FullGMU/SMMU/PLL/clock/CX/CFGshutdown thenACDoff/channelrestore/unmap/rootfree result1transport0. NewrunnerstrictGPUvalues/owner/orderacceptancePASS, runner0/autosuccess/independentAndroid1; no900e. No userspace service/draw claim. Nextseparate/dynamicBOandboundedgenericcommand submission, notextraownership-onlyloops.

## E20 plan — real GPU access to a BO allocated after bootstrap

E19verified796012e preserved. Currentmemoryblocker: session uses onlyfirmware-plan BOallocatedbeforeGPUboot; no post-startup pagepublication/bufferbinding hasbeenverified. Minimalexperiment (newwaffle_dynamic_bo=1,94sessiononly): afterfullownerbeginreturns andGPUidle/zerooutstanding, allocate16KiB BOatfreecontrolledVA0x80078000 (insideexistingcompactwindow), provebothlow/hightableentriesvacant andnoexistingregionoverlap, installAP_UNPRIV pages, cleanpagetables andinvalidatebothASIDs. BindsessionNCaliastonewBO whileREADY; retainoldfirmwareBOallocation. Same3IBs44/45/46 mustfetchcommands/writeactualmarkersinnewmemory. FreenewBOonlyafterfullGPUstop/contextdetach. NoECATSwhileGPUlive; actualGPUfetch/writeisproof. Preflightrefusalscleanupnormally; partialmapping/TLBuncertaintyretainsall/reset. ThisisoneboundedBOprototype, notgeneraluserspaceallocator orrenderclaim. Hostmustcover vacancy/overlap/partialfailure/dualTLB/bindingbeforecommands/aliaslifetime/unsafe-retention beforefullbuild/control93/session94.

E20implementation: newscopedSMMUdynamicfield+vacancy/overlapguards,16KiBallocationafterownerreturn, dualaliasAP_UNPRIVmapping, tableclean+existingdualASIDsync, READY/zero-submissionNCBOrebind. OldBOallocationretained; oldCPUaliasunmappedonlyafternewaliasready, newbackingfreeonlyafterfullstop/detach. ExistingGMUcodebyteidentical(appendAPIonly), entireboard/AOP/power/clockandSMMUlowlevelhelpersunchanged. Actualmapper12scenariospass vacancy/overlap/PA36/partialmap/TLB/bindfail; actualsessionnewBO3results+oldBOuntouched/failedaliasrebindpass; actualparentfinishchecksnewpagefreeafterchildstop/detach. Hostexpectationupdatedforlegitimateoldaliasunmapduringrebinding; productionunchanged. Newflagrequires94sessionthroughallrunners; actualGPUresults+publication/use/releaseorderrequired. Fullbuildnext,noE20hardwareyet.

E20 fullhost/XNU/EFI/container/current-sourcebinding passed. Invaliddynamicflagchain rejectedbeforeUSB. AutomaticRAMimageprepared. First93defaultLPAC/accessmatrix then94dynamicBO afterAndroid1. NoE20hardwareyet.

E20 default93control PASS run20261031T205251Z/auto20261031T205227Z ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Next94dynamicBOsession on sameartifact.

E20 firstlaunch run20261031T205410Z/auto205346Z rejected BEFOREkernel entry: loaderlogexact"waffle: unsupported RAM test request", resultnot-started0/0. Kernel_probe_startedfalse; dynamicmappinghypothesisNOTtested. Androidrecovered/independent1, no900e. Rootcause: omittednewbootflag fromloaderwaffle_cmdline_allowed whitelist, despitekernel/runnerchecks. E20-r2 fixesonlyloaderflagpolicy: exactsinglewaffle_dynamic_bo=1 requiresfull94sessionchain; duplicates/wrongvalues/missingprerequisitesrefused. Addedactualpolicycases; GPUsourceunchangedfromfirstartifact. Preserveoriginalartifact/failedreports; rebuildseparater2 thencontrols/dynamicrun. NotcountedasGPUmappingfailureorarepeatedhypothesis.

E20-r2 fullhost/XNU/EFI/container/sourcebinding PASS. Binaryidentitycheckcaught22metadata bytes:16LC_UUID +6timestampbytesintwocopiesofDarwinversion. Byte-levelauditprovesallnonmetadata bytesidentical, kernel/GPUsourceidentical. Comparisonupdatedfortwoversionstrings; abortedsetupssentnoRAMboot(manifestnotautomaticyet). Bothoriginalimages/reports preserved. Next93controlthenfirstactualdynamicGPU94.

E20-r2 default93control PASS run20261031T205814Z/auto20261031T205750Z ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Nextfirstactual94dynamicBOexecution.

## E20-r2 hardware PASS — GPU fetch/write to newly allocated post-bootstrap BO

Control93 run20261031T205814Z/auto205750Z ACCESS27/alloc8/LPAC42 passed. Dynamic94 run20261031T205950Z/auto205926Z: afterfullownerreturned, new16KiBBO low80078000/high1ff8000478000 PA8d1a74000 allocated/mappedAP_UNPRIV/cleaned/dualASIDpublished andREADYsessionrebound. Same3IB44/45/46 fetch/writeonnewmemory all4096wordswrong0; fullGMUstop+SMMUdetach beforedynamicfree, thenclock/CX/AOPrestore. Runner0/autosuccess/independentAndroid1; no900e. FirstlaunchfailurewasloaderpolicyrefusalBEFOREkernel, preservedseparately; correctedgatedflagonly, GPUnonmetadatabinaryunchanged. EvidenceE20-result.json. Nogeneraluserspaceallocator, shader orimageclaim. NextboundedgenericIB/shaderpayload; localMesaComputeratorA7XXsourceinventory captured, notyetadapted.

## E21 preparation — host compute tooling, no GPU implementation or hardware test

E20verified80802ac preserved/phoneAndroid. StockMesaComputeratorA7XXsrc chosenasreference. BuildingtargetinoldQRISConlyconfiguration failed: scriptPATHinitiallymissedvenvMako (fixedenvironment), thenlinkhadmissingNIRsymbols. GC-sectionsrelinkstillmissingnir_intrinsic_infos; no stubsadded. Separatecompute-build withfreedrenodriver butopenglfalse ALSOselectednir_stub.c, confirmedarchive. Afterunsuccessfultoolattempts,reassessedMesonarchitecture: with_gfx_compute (rootmeson1072) requiresactualOpenGL/Vulkan/CLCfrontend, notjustgalliumdriver/tools; NIRmeson84thenchoosesheaders-onlystub. NextsupportedconfigurationenablesOpenGLcore whileleavingEGL/GLX/platformsdisabled, andbuildsonlyhostComputerator. NoMesa sourceedits, noGPUfirmware/driverchanges, nohardwareexperiment. OldQRISCdisassemblerSHAstillf44277e4... matchesrecordedreference.

E21 hostpreparation completed (NOTaGPUhardwarepass). FullNIRsupportedMesonconfigurationopengltrue resolvedstubarchitecture; stockComputeratorbuildlinkswithoutMesasourceedits. ExternalofflineFD750assemblerusesrealir3_compiler_create(NULL)/ir3_parse_asm withcacheoff, outputs128-byteowninvocation8shader/metadata/disasm withoutDRMdevice. Deterministicrepeat +decode/reassembleinstructionbytesPASS; initialwholepaddedbinarycomparisonwasoverstrong(128vs256withidenticalprefix). Mesa'sownir3_shader.cvalidator333..370ignorespaddingNOPs; hosttestnowusesidenticalnativeinvariant andretainsallnon-NOPinstructionbytes. Invalidassemblyrejectedwithoutoutput. OriginalQRISCdisassemblerhashunchanged. AllGPU/kernel/loadercode remainsverifiedE20. No shader execution/imageclaimed. NextA7xxPM4exportandboundedshaderdispatch, usingComputerator templates/generatedXML andownedBOaddresses, ratherthaninventedregistervalues.

## E21 PM4 export plan — actual Mesa A7xx emitter with host-only BO/ring recording

E20hardware80802ac andofflineassembler6aa7314 preserved. Currentblocker: no verifiedboundedshadercommandstream/payloadlayout. ReusecompiledstockComputerator a6xx_init<A7XX>/assemble/emit_grid, wrappingonly BOallocation/upload/map and ringallocation withhostmemoryrecorders. Proposed16KiBdynamicBOlayout:commandsoffset400..1000, shader1000..1100, UAVdescriptor1100..1200, output100..120, control2000..3000. OnlyexpectedfourBOs accepted; no DRMdevice orsubmissioncall. Emitbinarypayload/PM4/BOmanifest fromexactMesa750profile, decodepacketbounds/relocations andauditregisters againstexistingprotectedwindows beforeanyhardware. Keepkernelunchangeduntilhostexport validated. Firstshaderhardwaregoal8SP-writteninvocationIDs, notimageclaim.

E21hostexportPASS: exactstockComputeratorA7XXbackend emits184dword13packet stream,73registerwrites, fourBOs fit16KiBlayout. Auditorchecksheaderparity/packetbounds/indirectshader+UAVaddresses/outputdescriptor/controlfence againstmanifest andall48nativeCPprotectspans; zero protectedwrites. AddindexXORguardsoutsideBOs, zeroallocatedcontrol, poison8outputwords. NoGPUexecution. Nexthardwareexperimenthaspreparemode1 replacingONLY5wordCP_EXEC_CSpacketwithsame-lengthCP_NOP (count4), thenmode2originaldispatch. Bothshouldexecutecontrolfencewrite1/fullguardreadback; onlymode2expectsSPoutput0..7. ScopegenericboundedIBexchangeandcomputejob only; default3IBpathretained. No protectionregister/firmware changes. Loaderflagwaffle_compute1/2requiresfull94dynamicBOchain; guardalllayersbeforehardware.

E21implementation readyforfullbuild: sharedboundedIBexchange extractedfromold8wordpath; actuallegacyhostscenariosstillPASS. Compute stagesguarded16KiBpayload/8poisonoutput/control0 then184wordIBseq44; checksall4096wordsonreturn/control1+mode2IDs0..7. Completeandstop45onlyafteractualreadback, failurespoison/retain. Mode1changesexactlyone5wordpacket (fourwordsdifferbecausefirstpayloadzeroalready), mode2originalMesaCS.14actualsubmissionprepare/dispatchfailurescenariospluspayloadprotected/escape/parityrejections andrealrunneracceptancehostchecksPASS. Fixedhostincorrectfive-word-differenceexpectation tofour(actualpacketstill5words); productionunchanged. Loaderpolicyexactcompute1/2requiresfull94dynamicBOchain; flagswiredthroughrunnersBEFOREhardware. CoreGMUboot/TCM/security/allboardandSMMUdynamicmappinghelpers unchanged. NoE21hardwareyet.

E21 fullhost/XNU/EFI/container/currentcompiled-sourcebinding PASS. ActualMesaemitter repeatedtwicepayload/PM4/manifestbyteidentical. NewflagchainsrefusedbeforeUSBwithoutprerequisites; loaderpolicypositive/negativecasespassed. First93control, then94compute-prepare(noEXEC), then94compute-dispatchonlyafterpreviousPASS/Android1. NoE21hardwareyet.

E21 default93control PASS run20261031T212802Z/auto212738Z ACCESS27/alloc8/LPAC42 noRAW/fullshutdown/PLL/CX/AOPrestore. Runner0/autosuccess/independentAndroid1. Next94compute-prepare:actualMESAstate/load/fence, onlyEXECreplacedNOP.

E21 prepare94mode1 hardwarePASS run20261031T212939Z/auto212916Z. Actual184wordMesaA7xxstate/shader/UAVload streamwithEXECreplacedNOP acceptedACK44; control1 writtenbyGPU, output8wordsremainpoison, all4096wordswrong0; slumber45/fullshutdown/AOPrestore, runner0/independentAndroid1/no900e. Thisqualifiescommandsetup/preload/control, NOTshaderexecution. Savedprepare94reportbeforedispatchoverwrite. Nextmode2originalEXECsamekernel.

## E21 hardware PASS — first actual A750 compute shader under XNU

Default93control212802Z passed. Preparemode1 run212939Z/auto212916Z acceptedMesa184wordstate/preload/fence withEXEConlyNOP; output8wordsremainedpoison/control1/all4096wrong0. Dispatchmode2 run20261031T213222Z/auto213158Z samekernel/originalEXEC: actualSPshaderwrotelocalinvocationIDs0..7 from8threads toSSBO, control1/all4096wordswrong0. ACK44/slumber45/fullGMU/SMMU/PLL/clock/CX/AOPshutdown, runner0/autosuccess/independentAndroid1, no900e. Thisisfirstshaderexecution, notanimage/onscreen/iOSacceleration claim. Savedbothprepare/dispatchreports. Nextoffscreen16x16shaderpattern notimplemented; ramp256assemblyofflinecandidateexistsbutnotinhardware. UserrequestedGitHubsave/push now; stopnewGPUchangesandpublishverifiedE21.
