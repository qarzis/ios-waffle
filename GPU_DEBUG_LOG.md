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
