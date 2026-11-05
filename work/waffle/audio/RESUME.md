# A15 hardware inventory PASS — 2026-11-05

Originalrunner0/success1/Android1; run20261105T111402Z. Complete immutable kernel-1.log strict analyzer proof saved. 107routes/71banks, referencedCB0–5, remaining65 M=0 but nonzeroSCTLR; NOTfree/owned/writable. No DSP/DMA/PCM/writes. Missing-root preUSB failure preserved then dedicated bound root built. Next qualify native secure ownership/nonzero disabled config before any CB writes. No active phone owner.

# ACTIVE — A15 read-only full inventory building

2026-11-05 user requests audio alongside GPU. New waffle_audio_smmu_inventory.h + actual sanitized host fixture PASS. Full routes/banks double-read, geometry/type/range/change checks; candidates exclude stage2/referenced/enabled orphan banks; ownership remains0. Existing isolated audio-iommu path heap storage/free/unmap; no SMMU writes/DMA/PCM. Native DT qsmmu-v500 => qsmmuv500_impl, not Adreno. Full build diagnostic-audio-inventory-a15 active; log audio/build-a15.log, freeze compiled inputs. GPU D19C sole USB owner (run20261105T110850Z), do not overlap; next validator/checkpoint then audio-only RAM inventory after Android confirmed.

# ACTIVE A14 survey complete — 2026-11-03

Run20261103T102416Z/auto102352Z read-only Apps SMMU survey completed, outer0/normal return/independent Android1. IDs4c017e6b/60000047/5111,107 groups/71 banks/4KiB pages/CBbase80000. Audio SIDs1001/1081/1061 have zero valid stream matches. This does NOT qualify DMA or PCM. Next: native domain attach, free context ownership, mapping and period completion; no arbitrary inherited bank or raw PA handoff. A13 graph lifecycle remains qualified, amps/iOS sink absent. Evidence A14-result.json/components.log.

User asks audio and GPU together; phone experiments serialized. E107 GPU currently owns USB (auto102811Z); no concurrent hardware access. Historical stop instructions below superseded by explicit user resume.

# ACTIVE audio A13 PASS — 2026-11-02

User continues audio plusGPUartifact/performancework. A13run20261102T203337Z/auto203313Z passesDSPboot/SPF1/OPEN344token2ACK0/CLOSE64token3ACK0/PAS1+36shutdown/normalXNUreturn/outer0/Androidindependent1. OnechangedAPMwordlegacycap1→modernGC0b001001, primaryfactoryproofvalidatedonactualfirmware. A12boundedGLINKintentcachealsohardwarefixed. NoPCM/DMA/hardwareendpoint/amplifierstartup. Nextblocker nativeAppsSMMU/audioDMA ownership+map/periodcompletion. NativeaudioIon appendslow4bitSID<<32toIOVA; DT1001(mask80),1061(mask0), IOVApool10000000..20000000. DoNOTsendrawphysicaladdresses/borrowredwood1801.

GPUtestsremainseparate/RAMonly; latestE101automaticappscene running(checkGPUresume/logs), no concurrentUSB. LatestA13evidenceA13-result.json/components. Noactiveaudioboottest. Firmwareprivate.

User resumed after Git publication; A11 diagnostic hardware continuation is now authorized. Public code: fcfb312987b5a2238eba055641ad56e14ba9bfd3.

# Current stop state — A10/A11, 2026-11-02

User stopped hardware work and requested Git publication only. Phone is in Android,
boot_completed1 checked; no hardware runner or build remains active.

A09 remains the last qualified complete DSP lifecycle. A10 added a two-module
WR_SHMEM->RD_SHMEM APM graph open/close prototype. OPEN344/CLOSE64 compare byte-for-byte
with actual pinned Linux v6.12 builders; reply correlation sanitizer tests pass.
The hardware GRAPH_OPEN failed locally in glink_send after about5.65s before an
APM reply; GPR counters stayed1out/1in (SPF only). Exact errno/root cause unknown.
Do not mark graph operation, DMA or PCM as working.

Current source is A11 diagnostic instrumentation: GLINK intent overflow and send
state/error logging, with unchanged packet/allocation behavior. XNU compile passed;
UEFI packaging stopped by user, no A11 device test. Next authorized continuation
should capture this trace, then fix only the proven transport cause. Do not blindly
increase buffers or change graph ABI without evidence. Native audio Apps SMMU is
15000000 with SID1001/1061; DMA remains unported.

A10-result.json, A10-components.log and AUDIO_DEBUG_LOG.md preserve evidence.
Primary source caches: upstream/linux (v6.12 adc218676eef25575469234709c2d87185ca223a),
upstream/audioreach-engine API headers and pinned OnePlus msm_audio_ion sources.
Private firmware remains excluded from publication.

---

# OnePlus 12 audio — resume after A09

2026-11-02. Active task: bring up audio using the local HakiOS reference.
Phone was returned to Android; independent `sys.boot_completed=1` confirmed.
No hardware test remains running.

## Qualified milestone

A09 run `work/waffle/runs/20261102T135600Z`, automatic run
`work/waffle/auto-runs/20261102T135536Z` passed native ADSP firmware boot,
fresh SMP2P ready/handover, GLINK, QRTR node5/services13, GPR SPF state1,
PAS1/PAS36 shutdown and normal kernel return. No PCM or amplifier startup.

- Artifact: `work/waffle/diagnostic-audio-scm-continuation-a09`.
- Evidence: `A09-result.json`, `A09-components.log`, `AUDIO_DEBUG_LOG.md`.
- Public commit: `272c92d48c7634d210823ab89baffd7b7d053a01`, verified on
  `qarzis/ios-waffle`, branch `waffle/gpu-bringup`.
- Qualified private code checkpoint: `03019f75ab1dfacbf063ff99b66241c0969d0416`.
- Public documentation: `docs/waffle-audio.md`; sound remains marked unavailable.

## Do not repeat

The donor ADSP carveouts, IPCC and RSC addresses were wrong for Waffle.
Native resources and all firmware blobs have been captured and verified.
A05 confirmed RPMh requests but panicked on unmapping a permanent mapping;
A06 corrected that and passed. A08 booted DSP and queried GPR but failed to
stop because the SCM loop aborted after100 interrupted returns. A09 preserved
the continuation for a bounded2s; PAS shutdown needed273 interruptions/649168us.
An earlier call needed417 interruptions. Do not restore the100-call cap.

WAITQ wake handling is still unsupported on Waffle: it is refused and dependent
secure calls are blocked instead of blindly resuming an unresolved context.
A08's dependent PAS36 WAITQ followed the abandoned PAS1 call; it did not recur
when PAS1 completed in A09. Pending IPCC30002 was observed even during a clean
A09 stop, so do not add speculative IRQ clearing as a fix for this resolved case.

## Remaining work

There is no AudioReach/APM PCM graph, DSP PCM-buffer mapping/period completion,
ported speaker amplifier initialization or connection to the iOS audio sink.
Next investigate the actual GPR/APM graph and mapping ABI from primary source,
then qualify consumption of silent PCM periods with amplifiers off. Native
Android has two TFA devices at I2C4-0034/0035 and an ODM speaker profile; the
exact speaker route still needs qualification. WCD939x enumeration alone does
not establish the speaker route. HakiOS redwood uses legacy APR/ASM/ADM/AFE;
its playback packets and addresses cannot be copied into Waffle's GPR path.

Native captures/private firmware: `android-baseline/`. Pinned OnePlus references:
`upstream/`, `upstream-source-index.json`, `upstream/msm-kernel/provenance.json`.
Never publish the captured firmware or amplifier container.

All tests are RAM-only. Keep the existing native power ownership/retention and
stop guards; modes3/4/5/6 are isolated bounded diagnostics, not ordinary iOS audio.
Do not run concurrent fastboot commands while the hardware runner owns USB.
