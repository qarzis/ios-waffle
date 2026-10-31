# GPU forensic audit — OnePlus 12 / Adreno 750

Audit in progress. Production source changes and further hardware probes are paused until diagnosis is complete. Builds and register readback are not proof of command execution.

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
