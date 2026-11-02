# OnePlus 12 audio audit — 2026-11-02

Scope: local HakiOS reference, current XNU audio bridge, read-only native Android capture. No kernel changes, amplifier writes, DSP reset or iOS boot performed.

## Proven gaps

1. `kernel/files/bsd/dev/macan_audio.c`: audio_play only forwards PCM when audio_sink is non-NULL. Repository search finds redwood_audio_set_sink declarations and definition, but no caller in kernel/userland. Existing device writes are not hardware playback.
2. macan_adsp.c is opt-in stage-1 DSP transport, not playback: GPR SPF state query only. Its ADSP base 0x9f100000 / capacity 0x04b00000 and DTB 0x9f080000 disagree with captured live Waffle DT: ADSP 0x9df00000 / 0x05280000, DTB 0x9de80000 / 0x80000. Do not enable unchanged donor DSP initialization.
3. Local HakiOS hakios.sound.c is explicitly POCO X5 Pro/redwood, legacy APR ASM/ADM/AFE. Waffle live DT exposes GPR adsp_apps. Its numeric ports, GPIO and SMMU setup are not qualified for SM8650.

## Native evidence

android-baseline/ contains cards/PCM list, firmware names, live DT extract, vendor pineapple mixer XMLs and ODM mixer_paths.xml. Root read-only capture succeeded. Bound module oplus_audio_tfa98xx_v6 has two devices, I2C 4-0034 and 4-0035; WCD939x also enumerates on SoundWire, but that alone does not prove the speaker route. ODM speaker path sets TFA_CHIP_SELECTOR=3, TFA Profile=speaker and feedback On. Android boot_completed=1 before capture.

## Hypotheses and next experiments

H1 (selected): no hardware PCM consumer is implemented. Confirmed by static callsite audit; next implement only after transport/route qualification, and require completed PCM periods rather than successful writes.
H2: unchanged donor ADSP startup cannot be used safely on Waffle due to memory/platform mismatch. Address mismatch confirmed against captured live DT. Next compare all resources, firmware layout and reserved ranges before a bounded DSP boot/ready/shutdown test with amplifiers off.
H3: HakiOS amplifier control can be reused selectively because native Waffle also has TFA devices. Unproven: inspect exact chip revision, firmware/container and OnePlus driver before any register write. Same I2C address is insufficient.

## Incremental plan

A. Qualify Waffle ADSP resources and firmware, then boot/ready/GPR state/shutdown with amps off.
B. Implement the native GPR/APM PCM route and DMA mapping; measure consumed periods while amps remain off.
C. Port only the exact amplifier configuration with bounded quiet tone and teardown.
D. Connect existing iOS PCM bridge; verify sustained audio and volume/mute.

Local HakiOS revision inspected: 8851317. OnePlus source tree index pinned in upstream-source-index.json. This audit is not an audio playback success.

## A01 — native firmware preflight implementation

Collected all 54 required load blobs (43,350,670 bytes), metadata and native TFA container via read-only rooted Android access. Private vendor files remain under android-baseline/firmware and are excluded from source checkpoints.

check-waffle-audio.py resolves the ADSP mailbox through its phandle (there are two IPCC controllers; selecting the first compatible node was rejected). It validates metadata, each load size and relocated bounds against live reserved-memory nodes. Result: native firmware fits; five donor defaults mismatch (ADSP base/capacity, DTB base, IPCC, RSC). Smem, command DB, QMP and lock address match. This is not proof that all power/interconnect policy is portable.

macan_adsp.c now permits Waffle ONLY adsp=3, a firmware-only worker; modes 1/2 remain refused until hardware qualification. It uses native ADSP/DTB ranges solely for file validation. Preflight bypasses survey, PAS, mailbox, RPMh, IPCC and amplifier writes, including normal stop/quiesce cleanup. Donor modes remain unchanged. Default adsp=0 remains off.

Measured: host harness compiled actual firmware_check and actual macan_adsp_init with ASan/UBSan. Real ADSP+DTB accepted; old donor capacity rejected; bad ELF, truncated metadata, excessive phdr count and short segment rejected. Actual mode gate accepts Waffle 3 only, rejects Waffle 1/2/4 and donor 3. Full XNU incremental build passed. Builder now refreshes and pins macan_adsp.c. No on-device XNU test yet; no audible playback claimed.

Next: integrate firmware preflight into a bounded RAM diagnostic with an explicit adsp=3 boot argument and independent return-to-Android checks. Then qualify native RSC voting/ICC chains and firmware authentication before enabling hardware boot. Do not bypass the Waffle mode guard to try the old donor addresses.

## A02 — diagnostic boot integration failed before firmware validation

First RAM boot: 20261102T125913Z. Exact panic: Process 1 exec of /sbin/launchd failed, errno 2. Loader log explicitly assigned resident system image to md0 root and payload ramdisk to md1. The initial diagnostic passed an empty resident image, so it could not run PID1. This is an image-layout failure, not a DSP/firmware result. Separately, source inspection found Waffle input init returns before the common ADSP init. Corrected both for A03: resident/root holds static PID1+dev directory+private firmware; payload auxiliary image is empty; Waffle init now calls the guarded ADSP init. Modes other than3 still blocked on Waffle. Automatic return to Android succeeded. No DSP/PAS/amp startup occurred.

New loader policy allows exact adsp=3 only in an isolated userland diagnostic with a single explicit return budget <=60 seconds. GPU/torch/multicore combinations and modes1/2 rejected by sanitizer policy tests. A03 must show PID1, both native MDT validations, explicit PREFLIGHT OK and clean kernel return; successful boot alone does not pass.

## A03 — hardware firmware preflight PASS

Actual RAM boot 20261102T130159Z, auto-run 20261102T130135Z. Native static PID1 reached. XNU validated adsp_dtb phdrs=3/span0xe000 and ADSP phdrs=57/55 load segments/span0x5280000, destination0x9df00000..0xa3180000. Literal marker WAFFLE PREFLIGHT OK. No PAS/RPMh startup marker or panic. Kernel returned normally (31174 log bytes); outer runner exit0, Android recovery confirmed and independently checked by ADB boot_completed=1. Evidence A03-components.log and A03-result.json. This tests actual XNU file access and validation only; DSP transport/playback still absent.

## Next blocker — native power and interconnect contract

Pinned native qcom_q6v5_pas.c confirms PAS1+DTB PAS36. Live CX/MX requests are level384, whereas donor rails() requests256. Native ICC graph reconstructed from pineapple.c+matching header and checked against DT endpoints: LPASS43->EBI512 uses LP0/SH0/MC0/ACV; crypto41->EBI512 uses CE0/SN3/SN0/SH1/SH0/MC0/ACV. Donor code votes SN2 and omits SN3/SH1. SH1 has an enable mask, so blindly treating every BCM as a scalar bandwidth vote is invalid. Details native-icc-routes.json and native-adsp-power-contract.json; static analysis is not a hardware qualification.

Next experiment must isolate correct native rail/ICC requests and teardown before enabling PAS authentication/reset; preserve the Waffle hardware-start guard until those requirements are covered. Do not retry unchanged donor votes.

## A04 implementation — native power plan, no RPMh writes

Added waffle_adsp_power.h with native Waffle rail levels384/384/128, required8 BCM resources, exact one-hot SH1/ACV enable values, increasing VCD order and commit only on each VCD boundary. ARC indices and BCM auxiliary VCDs must match the current command database; unknown/missing/malformed resources fail closed. Kernel adsp=3 now validates this plan after firmware, still without starting PAS/DSP or writing mailbox/RPMh/IPCC/amps. An explicit bounded write transaction is not enabled yet.

Fresh native Android capture after mounting debugfs read-only confirms lcx30030/lmx30040/xo300d0 and native level tables. Debugfs was unmounted after collection. Captured regulator summary shows the remoteproc proxy CX/MX consumers released in Android, but this does not prove every inherited BCM vote can be dropped under XNU. No zero/release writes were introduced.

ASan/UBSan host checks compare all8 encoded BCM commands with the actual pinned native tcs_cmd_gen function and real cmd-db resource data: rail indices7/4/3;6 VCD commits;6 resource corruption cases rejected. The actual kernel command-database lookup is also compiled and tested against native resource layout plus invalid magic/count/aux bounds/slave ID. Firmware regression tests pass. Full XNU/UEFI build and paired image validation pass.

## A04 hardware result PASS — power plan remains a dry run

Actual XNU run20261102T131242Z, auto-run20261102T131218Z. Live command database produced all11 planned commands: ARC7/4/3 plus8BCMs,6VCD commits. Explicit POWER_PLAN OK and PREFLIGHT OK. Kernel returned33449 log bytes normally, outer exit0, automatic Android recovery and independent ADB boot_completed1 confirmed. No DSP, amplifier or RPMh power write performed. See A04-components.log and A04-result.json. Final output includes4 identical copies of command records through combined logging; every copy was compared, not counted as4 tests.

Next measurable step: bounded native RPMh transaction with busy/pending guards, per-command status checks, waiting only on VCD commit boundaries, and no writes on an unqualified table. Preserve inherited/shared resource requests; do not use donor zero/release sequence. A successful TCS acknowledgement would only qualify command transport, not DSP boot or sound.

## A05 implementation — bounded native RPMh request transport

New mode adsp=4 runs firmware and command-db validation, then one whitelisted BCM batch and one ARC batch under macan_rpmh_lock. DSP/PAS/QMP/IPCC and amplifier startup remain disabled. Native RSC drv2 base17a20000/TCS0 is used; major3/4, capacity, all3 active TCS idle and no pending IRQ required before writing. BCM wait mask0xf5 waits only at the six VCD commit boundaries; ARC wait mask7. Per-command issued and requested-completion bits checked, IRQ+idle required, bounded200ms polling. Completed transactions restore saved TCS programming with trigger stripped and verify readback. Timeout leaves in-flight registers untouched, latches failure and forbids subsequent batch/retry.

This experiment never drops resource votes. Scalar BCMs use maximum encoded bandwidth and CX/MX/XO highest native levels7/4/3. ACV is deliberately raised to enable+performance mask3 instead of the dry-run native no-performance mask1, to preserve any inherited performance bit. All votes remain through EFI return until Android reset, as in the previously qualified sensor power path. No donor release sequence is called for mode4.

ASan/UBSan tests execute the actual transaction function with mocked RSC: v3/v4 success, exact command/wait whitelist, stale trigger removal, saved programming restoration, busy/pending/capacity/version rejection before writes, incomplete command status, bounded timeout and no retry. Native planner and actual firmware/mode gate regression tests pass. Physical acknowledgement still pending.

A05 build integration: first full XNU compile rejected the new helper because stopping was declared below it. Moved the existing shared state declaration ahead of the helper; no runtime logic change. Original compiler log retained as A05-first-build-failure.log. This was a compile-order failure, not a hardware experiment.

## A05 hardware FAIL — requests acknowledged, MMIO cleanup panicked

Run20261102T132502Z, auto-run20261102T132438Z. Native RSC version30200/config800c8104; active TCS0/1/2 all idle; IRQ0. BCM batch result1/waitf5 and ARC batch result1/indices7/4/3; all11 command status10101. Then exact panic vm_map_delete: Attempting to remove permanent VM map entry. Cause: new wrapper used ml_io_map (permanent) then ml_io_unmap. Confirmed from local XNU machine_routines.c: ml_io_map passes unmappable=false, ml_io_map_unmappable passes true. Whole experiment FAIL; hardware requests acknowledged does not override cleanup failure. Runner retained panic and restored Android successfully. Evidence A05-components.log and A05-result.json.

A06 correction is limited to correct MMIO ownership: use ml_io_map_unmappable with VM_WIMG_IO and pair with ml_io_unmap. Extended ASan/UBSan test compiles actual kernel wrapper, actual cmd-db parser and actual transaction function together; checks removable mapping contract, shared lock across both batches and unmap after unlocking, plus stopped/mapping failure guards. Native11 resource lookups and malformed input tests remain passing. No changes to resource values, retry policy or DSP gates.

## A06 hardware PASS — native power requests plus clean MMIO teardown

Run20261102T132912Z, auto-run20261102T132848Z. Both native BCM/ARC batches result1; all11 distinct command statuses10101. Explicit POWER_APPLY OK/TCS buffers restored1 after removable mapping was unmapped. No panic, normal kernel return, outer runner exit0, automatic Android recovery and independent ADB boot_completed1. Corrected map/unmap contract resolves A05 panic. Votes intentionally retained until Android takes ownership. This qualifies power request transport, not actual DSP execution, clocks or audio playback. Literal evidence A06-components.log and A06-result.json.

Next: read-only native SMEM/SMP2P/GLINK state survey. Current donor full-boot path treats any historical SMP2P item as an active previous DSP run and attempts shutdown; that assumption is unqualified for Waffle. Establish actual inherited state before enabling reset/authentication or reusing readiness flags. No DSP boot yet.
