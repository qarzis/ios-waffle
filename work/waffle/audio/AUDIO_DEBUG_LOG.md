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

## A07 setup — inherited DSP state survey

Added isolated read-only mode adsp=5. Native Waffle IPCC physical base406000 replaces donor1106000 for the survey. Firmware and native power table are checked first, then existing step_survey reads SMEM partition/SMP2P/GLINK item presence, last crash item and IPCC received register. It does not consume/clear doorbells, allocate SMEM, send stop requests or touch PAS/QMP/RPMh. Loader accepts mode5 only in an isolated <=60s diagnostic; mode5 stop/quiesce skips donor shutdown. Host mode/policy checks and full paired XNU/UEFI build passed. The actual initial state must be read before choosing the next DSP reset experiment.

Source audit also resolved a potential ELF mismatch: native pineapple uses_elf64 controls rproc_coredump_set_elf_info at qcom_q6v5_pas.c:1866, not the ELF class of the actual firmware loader. Captured MDTs are ELF32 and validated; do not replace them with invented ELF64 metadata.

## A07 hardware survey PASS

Run20261102T133455Z, auto-run20261102T133431Z. Partition0/2 exists at81e9f000/size60000 with2items. SMP2P443 and429 absent; GLINK478/479 present, remote480 absent; IPCC receivedffffffff. No inherited DSP state item to claim as an active previous run. Explicit DSP_SURVEY OK, clean kernel return, outer exit0 and Android recovery confirmed. These observations do not themselves prove clocks or code execution. Next bounded boot must refuse if a DSP state item unexpectedly appears before ownership instead of resetting an unowned DSP.

## A08 experiment plan — first bounded native DSP boot

Hypothesis selected: with qualified native firmware ranges/IPCC base and A06 power request transport, the existing PAS/SMP2P/GLINK/GPR stage1 can boot Waffle DSP and answer APM SPF state. Evidence: A03 firmware validation, A06 power acknowledgements and cleanup, A07 absent inherited SMP2P/remote GLINK items. Minimal test: mode6, no PCM/amp/GPU; allocate native host SMP2P item, hold qualified power votes, QMP image state, authenticate PAS36 then PAS1, require fresh ready+handover, GLINK/QRTR and GPR SPF1, then PAS shutdown and Android recovery. Existing state appearing before ownership is refused without resetting an unowned DSP. Native votes are retained at handover/shutdown; donor rail/ICC release is bypassed for Waffle. No HakiOS APR sound commands transplanted.

Native qcom_scm.c confirms PAS init has two args (VAL,RW), mem setup has3VAL args; donor SCM argument encoding matches. uses_elf64 affects coredump format only. Native power helper source was byte-compared with hardware-qualified A06. Full paired build/source/image checks pass. Crash collector now accepts bounded180s wait so it covers the DSP test; no flash commands introduced. Passing compilation is not boot proof. Required result: authenticated36/1, ready/handover, GLINK/QRTR, GPR SPF1, PAS shutdown36/1 and independent Android recovery. A failure must be attributed to the first literal failing stage before another experiment.

## A08 hardware partial bring-up, overall FAIL at shutdown

Run20261102T134432Z, auto-run20261102T134408Z. PAS36 and PAS1 authenticated; copied payloads readbackOK. SMP2P ready2 then handover6; GLINK up; QRTR node5/services13; actual GPR SPF1 response. Explicit STAGE1 OK mode6. First failure: PAS1 shutdown exhausted100 SCM_INTERRUPTED returns. Existing code then wrongly proceeded to dependent PAS36, which returned WAITQ_SLEEP and was blindly resumed for10s without native wake processing. Shutdown result0/clean0; whole runner FAIL, preserved as such. DSP crash item says APPS force stop, consistent with the requested SMP2P force-stop path; this string is not proof of an unsolicited DSP crash. Android recovery and independent ADB1 succeeded. No PCM or amp startup. Literal excerpt A08-components.log; full original raw log SHA in A08-result.json.

### Shutdown hypotheses (max3)

H1 selected for A09: fixed100-interruption cap aborts a legitimate continuation before completion. Native qcom_scm-smc.c repeats interrupted calls until return while preserving A6. Test: Waffle-only time-bounded2s continuation with100us pacing, unchanged PAS payloads; expect shutdown completes after >100 returns. A2s unresolved result refutes cap alone as the cause; do not increase again without new evidence.
H2: WAITQ wake handling is missing. Native driver uses IRQ work+FAST GET_WQ_CTX and completion before RESUME/ACK; donor blindly sleeps and resumes. Evidence is PAS36 WAITQ in A08, but it follows the abandoned PAS1 continuation and may be secondary. A09 must refuse unimplemented WAITQ and block further secure calls rather than corrupt another context.
H3: last SMP2P/IPCC interrupt remains pending after link polling is stopped and causes repeated secure interruptions. Native Linux has an IPCC IRQ handler; this port polls. Read-only PRE_PAS_STOP IPCC_RX instrumentation will distinguish this from an empty mailbox before altering IRQ handling.

A09 changes only interrupted-call duration/preservation and safe failure handling: retain unresolved continuation and dependent PAS/metadata/power, do not continue dependent shutdown, and reject unhandled WAITQ on Waffle. Host sanitizer test executes actual SCM loop with mocked SMC registers:250 interruptions retain A6 and original args,2s timeout blocks subsequent secure calls, WAITQ rejected instead of blind resume, busy/donor behavior preserved. Separate build test registration error was corrected before hardware; log A09-test-registration-failure.log.

## A09 hardware PASS — full native DSP/GPR boot and clean shutdown

Run20261102T135600Z, auto-run20261102T135536Z. Authenticated PAS36+1, SMP2P ready/handover, GLINK, QRTR node5/services13 and actual GPR SPF1 all succeeded. PAS1 shutdownOK and PAS36 shutdownOK; explicit DSP_BOOT result1/stop_clean1. Normal kernel return, no panic/adspFAIL, outer exit0, automatic Android recovery and independent ADB1. No PCM, DAC or amplifier startup; no audible playback claim.

SCM continuation evidence:417 interruptions/205418us on an earlier call; PAS shutdown273 interruptions/649168us. Both exceed the old100-return cap and completed within the new2s bound with preserved A6/context. H1 confirmed; no further cap-increase experiments needed. PRE_PAS_STOP IPCC_RX30002/stop_ack1 was present while shutdown still completed, so H3 pending IPCC alone is not the current blocker; do not add speculative interrupt clearing. No WAITQ was needed when PAS1 continuation completed correctly, so A08's dependent PAS36 WAITQ was secondary. Native WAITQ wake support remains deliberately unsupported/refused if encountered in future; do not claim generic SCM completeness.

Qualified milestone: native firmware lifecycle and GPR control transport. Next architectural gap is an AudioReach/APM PCM graph and DSP buffer mapping, then board-specific TFA amplifier configuration and the iOS PCM sink. Local HakiOS legacy APR/ASM/ADM path is a reference, not a drop-in for this GPR firmware.

Publication: source and concise status published to qarzis/ios-waffle branch waffle/gpu-bringup at272c92d48c7634d210823ab89baffd7b7d053a01. Push and ls-remote verified; public worktree clean. Proprietary firmware excluded. Audio resume state saved in work/waffle/audio/RESUME.md.

## A10 architecture audit and experiment plan — APM graph before DMA

Pinned Linux v6.12 revision adc218676eef25575469234709c2d87185ca223a AudioReach/APM/GPR builders, plus AudioReach/audioreach-engine API headers (tree b38cb85a1a2543aa28aa1b27f4c380cafa5024bb, individual Git blob hashes verified). Native OnePlus msm_audio_ion.c and live DT establish audio SID1001 and1061 (low4-bit mask1), IOVA pool10000000..20000000 and Apps SMMU15000000; the audio device is Android IOMMU group52. Redwood SID1801 is inapplicable. Do not send ordinary physical addresses as PCM DMA addresses. Correct mapping still needs implementation and hardware ownership qualification.

Selected hypothesis: firmware accepts a minimal WR_SHMEM->RD_SHMEM graph through existing GPR/APM transport. Test only GRAPH_OPEN and GRAPH_CLOSE: one native subgraph/container, two endpoints, one port1->port2 connection. No PREPARE/START, media format, shared-memory map, DMA address, hardware endpoint or amplifier writes. IDs use the documented Linux private ranges. Perf=lowlatency2, directionRX2, scenario playback1, container PP capability1/stream position1/stack defaultffffffff/ADSP2 are from primary API definitions, not guessed. Closure targets only this graph; a failure unwinds the owned DSP via qualified PAS shutdown.

waffle_apm.h emits OPEN344 and CLOSE64 bytes. Host ASan/UBSan test compiles actual Linux graph population, serialization and close builders with minimal host list/allocation shims; both packets compare byte-identically. Capacity guard, unsupported opcode and token output tested. Actual kernel GPR reply parser is tested for token/opcode/domain/ports/length, ACK0/error, stale/duplicate rejection and preservation of SPF's dedicated state response requirement. Mode7 adds graph lifecycle to bounded native boot; prior mode6 still performs only SPF query. Successful compilation/serialization does not prove firmware accepts the graph. Expected hardware result: both correlated APM ACK status0, clean PAS shutdown and Android recovery. PCM transfer remains untested even if graph lifecycle succeeds.

## A10 hardware FAIL before graph delivery

Run20261102T142409Z. Native DSP boot/GPR SPF1 mode7 passed. GRAPH_OPEN344/token2 logged at24.922219s; stage12 failure at30.575201s. No APM response log. Link shutdown reports GPR1out/1in, corresponding only to SPF query, so graph delivery failed inside local glink_send. Exact transport errno was not yet instrumented. Native FIFO capacity16384 bytes, so packet size alone is not proven as cause; remote-intent capacity/allocation/request completion remain unqualified. PAS1/PAS36 shutdownOK, normal kernel return and Android recovery confirmed. Whole graph test FAIL; do not claim firmware rejected or accepted the graph. Evidence A10-components.log/A10-result.json.

## A11 instrumentation, user STOP

Added logging only: remote-intent table overflow counts/largest dropped intent; send errno, table occupancy/in-use/maximum size, request ACK/grant and FIFO room; graph transport error. Packet bytes and allocation behavior unchanged. Full XNU compile completed; loader built; UEFI packaging was interrupted at user request. No A11 hardware test was launched. Owned build processes terminated and no hardware runner remained; independent Android boot_completed1. Work remains stopped. Do not auto-resume tests due to the later request to publish Git updates.

Publication verified: fcfb312987b5a2238eba055641ad56e14ba9bfd3 on qarzis/ios-waffle/waffle/gpu-bringup. User subsequently resumed hardware work; stop request revoked. Resume A11 trace capture without graph/intent allocation changes.

## A11 hardware trace — root cause established, graph delivery FAIL

Resumed after user explicitly reauthorized work. Run20261102T192851Z, auto192826Z. Large remote advertisements512/1024/4096 were each dropped by full64-entry table. Sender error55/ENOBUFS: entries64,used0,largest128,fits0,asked1,answered1,granted1,FIFOroom16368. Remote allocation was granted; TX FIFO space is sufficient; no credits are busy. Local metadata admission discards the larger valid credits. Graph packet remains unmodified344 bytes and was not delivered. PAS shutdown and automatic Android recovery confirmed; overall testFAIL remains recorded. Evidence A11-components.log/A11-result.json.

## A12 minimal fix — bounded diverse remote credit cache

Keep table64 and packet344 unchanged. Match existing IDs before empty slots; duplicate advertisements cannot clear in-flight ownership. Admit unused larger remote credits by replacing the smallest unused smaller cached credit only when full. Never replace in-use entries, never send/free a remote allocation, and never grow the local table or payload buffer. Discarding metadata for an unused remote-owned credit does not create an outstanding transfer. Native Linux tracks advertisements in its remote intent IDR; the old fixed cache limitation was local to this port.

Host ASan/UBSan compiles the actual kernel glink_send: reproduces A11 ENOBUFS from64 unused128-byte entries with request/grant but no fitting cached credit; after admitting512/1024/4096, the same344-byte APM packet sends with512-byte credit and no request/table growth. Checks in-flight IDs survive duplicate/resize attempts, existing IDs win over earlier empty slots, and full-busy/malformed admission is rejected without mutation. Hardware test must show large-credit admission, OPEN/CLOSE correlated ACK0, PAS shutdown and Android recovery. If graph delivery still fails, review the new evidence before any further buffer or ABI changes.

## A12 hardware result and architectural review

Run20261102T193654Z: larger512/1024/4096 credits admitted without table growth; identical344-byte GRAPH_OPEN reached DSP. Correlated token2 BASIC_RSP_RESULT returned opcode01001000/status1 (generic failure). Transport correction measured; graph stillFAIL. PAS1/PAS36 shutdownOK; independent Android boot_completed1 confirmed after user resumed GPU work. Evidence A12-result.json/A12-components.log.

Three graph attempts A10/A11/A12 now require architecture review before further experiments. Pinned AudioReach parser apm_gpr_cmd_parser.c (blobfb7a5dd4c8210787dab07d6ab078bbfaf73e855c) directly stores container property08001011 version1/type_id; current packet has legacy PP capability1. Modern GC type is0b001001, SC0b001000 (NOT1 or2). This is a compatibility hypothesis, not established firmware ABI: inspect container factory legacy translation before changing packet. No PCM/DMA/amp writes added.

## A13 architecture review completed — modern container type hypothesis

Pinned containerfactory cu.c directly looks up type in{0b001000SC,0b001001GC,0b001002OLC,0b00100dPTC}; unknown1 returnsAR_EFAILED. Pinnedparser stores08001011/version1/typewithoutlegacytranslation; WR_SH_MEM_EP API supportsGC. Actualfactoryhostrejects1 andacceptsGC, currentA12packetfailscontract. This is stronger than stack/topologyhypotheses, but nativefirmwarecompatibility stillrequiresdeviceproof.

A13 changes exactlyONE32-bit OPENword1→0b001001; size344, SG/modules/ports/stack/domain/transport unchanged; CLOSE64identical. Host uses actualLinuxserializer withlegacyinput first (exactoneworddifference), thenmodernGCinput(byte-identical); actualenginefactoryacceptscandidate. NoDMA/PCM/amps. Expected OPEN/CLOSEcorrelatedACK0/cleanPASstop/Android; ifstatus1remains doNOTrepeattypechangewithoutnewdata. CurrentGPUtestsfinishbeforeany audioUSBboot.

## A13 hardware PASS — native APM graph lifecycle

Run20261102T203337Z/auto203313Z: identical344-byteOPEN exceptGCtypeword returnedcorrelatedtoken2/status0; CLOSE64token3/status0; lifecycle1/moduleWR/RD/oneconnection/noDMA/noPCM/ampsOFF. PAS1/36shutdownOK, DSP_BOOTresult1/stop_clean1, normalreturn, outerrunner0/autosuccess andindependentAndroid1. EvidenceA13-result.json/A13-components.log. Confirmsmoderncontainer-typeABI correction for thisfirmware; doNOTreverttolegacyPPcap1. Nextblocker DSPPCMmemorymapping+periodcompletion, thenhardwareendpoint/TFAroute/iOSsink; graphPASSisNOTaudibleplayback.

## A14 next blocker — native audio DMA context survey

UserexplicitlyrequestsGPUandaudioinparallel; phoneexperimentsserialized. NativeAppsSMMUDT15000000/1MiB audio1001(mask80also1081),1061(mask0); low4SIDbitsappendedatbit32toIOVA10000000..20000000. Primarynativearm-smmu-qcom-pm.cblob b2218da124538e10488b73117e3de2a5db7056c1 verified: TCU DT hasNOclock-names/qcom,regulator-names/interconnects; nativeoptionalresourcepathrequiresnoresourcewrites. TBUwakecallbacksseparateandNOTinvoked. NoignoredNUMPAGENDXB/SMR/CBoverridepropertiespresent. EvidenceA14-power-prerequisites.json.

A14read-onlymode8 snapshotsID0/1/2, decodedglobal/CBgeometry, validSMR/S2CRmatchingonlyaudiostreams, matchedCBAR/SCTLR/TCR/TTBR/faultstatewithoutclearingfaults. EXIDSvalidityusesS2CRbit10; legacyusesSMRbit31. ReadcallbackhasNOWRITEAPI,1MiBbounds; translatedCBindexchecked; duplicateoverlapmarkcontextunqualified; postreadSMR/S2CRstabilitychecked. HostASanUBSanpassesnativelegacy/EXID/mask1001-1081/sharedbank1061,allreadfailures/geometry/reroute/bypass/ambiguityguards/64bitfields. SnapshotdoesNOTgrantownershiporsignifyDMAworks.

Mode8isolated60sloaderpolicy/nodspreset/noPAS/noRPMh/noGPR/nofirmwareload/noTLB/noregisterwrites. DedicatedCLI--audio-preflight --audio-iommu excludespower/survey/boot/graph/GPU; normaladsp0unchanged. Kernelstop/quiescereturnwithoutdonorcleanupformode8. FirsthardwareexperimentmustcaptureactualmappingthenAndroid1; doNOTreplaceanyinheritedCB.

## A14 hardware survey PASS; audio DMA context remains absent

Run20261103T102416Z/auto102352Z: ID0/1/2=4c017e6b/60000047/5111,107streamgroups/71banks/4KiBpages/CBbase80000. All three audio SIDs1001/1081/1061 have ZERO valid matching streams. Read-only mode completed, no DSP/PAS/RPMh/DMA/register/TLB writes; normal return, outer0, independent Android boot_completed1. Snapshot pass does not qualify DMA; no inherited audio context can be assumed. Next inspect native domain attachment and qualified free-bank ownership before any context programming. Evidence A14-result.json/A14-components.log.

A15 offline native domain audit recorded in A15-domain-attach-audit.md: absent audioSMRs doesNOTmeanfreeCB0; nativeallocator tracks pinnedstreams+bitmap andStage1startsNUMS2CB. GenericS2CRwrites haveimplementationoverride; globalreset/selftest unsuitableforliveUEFIDPU. Nextreadonlyroute/bankinventorybeforefirstDMAwrites; nohardwareexperimentduringGPU E109.


## 2026-11-05 A17 host-only ACTLR applicability
Native qsmmuv500_device_group selects DT qcom,actlr by smr_is_subset; init_cb writes ACTLR only for matched overrides. Parsed captured live Apps-SMMU table and native audio stream masks: neither1001/mask80 nor1061/mask0 matches. Evidence A17-dt-actlr-audit.json and A17-actlr-analysis.json. This rules out blindly copying a donor/Adreno ACTLR override; no bank ownership or DMA proof, no register writes. New HakiOS source reviewed at pinned revision in ../hakios-2.3.4-audit/provenance.json; APR/ASM transport remains incompatible with native GPR/APM.


## A18 host-only native MAP/UNMAP serialization — 2026-11-05
Added waffle_apm_memory.h, not connected to DSP transport yet. Actual pinned Linux allocator/map/unmap functions compiled and byte-compared: MAP44 and UNMAP28 (NO GRAPH_OPEN's16-byte APM command header). Native DT audio pool10000000..20000000; SID1001/1061 low4bits atbit32; first step one page-aligned contiguous region, SHMEM8_4Kpool3, property0. DonorSID1801/rawPA/out-of-pool/unaligned/zero/overflow/small capacity refused without modifying output. Ten sizes/SID cases pass ASanUBSan. This proves packet bytes only, NOT domain ownership, DSP map ACK, DMA or sound. Preserve earlier fixture compile failures A18-memory-host*.log; final pass A18-memory-host-final.log. Next transport integration requires qualified SMMU mapping and correlated returned map handle; never send these bytes using raw PA as substitute.


## A19 native Android DMA import/unmap observed — not XNU playback

User prioritizes sound; Crisp deferred. Root unlocks native observational route. Actual IOMMUgroup52device soc:spf_core_platform:qcom,msm-audio-ion and tracefseventsexist. First volume0soundeffectquery producednoaudiomap, so no DMA inference fromit. Nativeaudioimportdriveralreadyhas ioctl scalarfdMAP/UNMAP. Retrieved pinnedUAPIpathinclude/uapi/audio/linux/msm_audio.h blob96cdc6908e5f38e8b45a4f406412f1c9ffab2857/Gitblobhashverified; MAP_IOW(a,97,int)=40046161,UNMAP98=40046162. NoHYPioctls109+.

Compiled freestandingARM64Androidsyscallprobe ownsone4096BsystemDMAheapbuffer. Heapallocate0/audioimport0/audiounmap0/exit0. IsolatedSMMUtrace2/2events map/unmap sameaudio group/iova1fff7000/size1000; noothergrouptrace, noFIFO/DSPcommand/amp/PCM. A19-result.json/hash. NativeDMAoperationpositive; nativeaudioIOVApoolconfirmed. Contextbanknumber/securityownershipstillunknown: preexistingAndroiddomain doesnotgrantfreeUEFIbank. Nextderiveactualnativedomainallocation/attach beforeXNUwrites. Do notmistake nativepassforiOSsound.


## A20 actual native audio context observed through bounded kprobes

User continued sound. Root tracefs supports module-symbol kprobes. No MMIO write or SMMU reprogramming by probe. First probe on __arm_smmu_tlb_sync captures actual args: audio-own-buffer unmap followed in SAME task/PID by page174/sync2032/status2036; unrelatedUSB usespage175. Native macroCB(s,n)=numpage+n. Follow-up arm_smmu_tlb_sync_context fields from config-independent exactsourceprefix confirmaudioCB46/IRQ46/ASID46, USB47, sameSMMUobject. Third observation independently confirms physicalioaddr15000000/numpage128/pgshift12/stage0(S1). Each nativeimport/unmap0/probeexit0; maps inpool1fff4000..1fff6000.

Fourth read-onlyprobe captures Linux cachedCB46 state via cbs pointer80/stride48 derivedfrompinnedlayout:TTBR0=002e0008f5ca1000,TTBR1=002e000000000000,TCR0=0080351c,TCR2=00038011,MAIR0=f404ff44,MAIR1=0000efe4,cachedSCTLR=0a5f10e7. These are cached kernel fields, NOT liveMMIOreadback. DoNOTcopyTTBRphysicaladdress orcachedSCTLRblindly. TCRlowPASIZE1->36bitoutput, T0SZ28->36bitinput,4Kpages; ASIDTTBRhigh46consistent. Hoststatic_assert exactprefixoffsets andcachedCBstridePASS; actualpage/physicalgeometrycorroborateslayout. A20-result.json recordstracehashes andscope. This provesnativeconfiguration/observation, NOTXNUbankallocationorwritability/DMA.

Each isolatedinstance+ownkprobe removedaftercapture/globaltracingremainedoff. A final cfgbitfieldcrosscheck didNOTexecute: phoneUSBdisconnectedbeforekproberegistration, so noorphanprobecreated. rootreadstopped, continuehostaudit. Criticalremainingimplementation: perbootbankreservation excludingallinheritedroutes/enabledorphans + boundedexclusive claim/rollback ofoneknown-disabledbank, thennewownpagetables/nativeattributes, streambinding/TLB, ACKbeforePCM. AndroidCB46isnotfixedboardABIorownershipgrant.


## A21 native configuration corroboration after reconnect

Androidboot1/rootKSUconfirmed/noexistingkprobes. ResumedpreviousincompletecfgobserverinprivateinstancefilteredCB46. Own4KiBDMAimport/unmap0/exit0, nativecontextcb46/asid46/cfg_sctlr77da/cbar1/fmt1/stage0. Compiled ACTUAL pinned arm_smmu_lpae_sctlr function andregisterdefines withcfgbitfield77da/cbar1: produces0a5f10e7exactlymatchingpreviouscachedvalue. ThuscachedSCTLR'shighbitsarevalidnativecacheattributes,notrandomunexplainedvalues. DecodeWACFG2/RACFG2/SHCFG1/MTCFG1/MEMATTR15/CFCFG1/CFRE1/M1/HUPCF0, AArch64stage1. Exacthostfunction/proof a20-native-domain/sctlr-proof.py/PASS; A21-result.json/hash. ClearMbuilderalsoverifiedwithoutchangingcache/faultbits. NoSMMUMMIOwrites/DSP/PCM. Probeinstanceandownkproberemoved,globaltracing0preserved.

NextminimalXNUexperimentmustqualifycontrolaccesswithoutDMA: freshinventory/oneunreferencedM0context/perbootsoftwareexclusiveguard, alteronlydormantfaultconfigurationbitwithMremaining0, verifyreadback/restoresnapshot, neverbindstreamoroverwriteactivebank. Read-onlyinventoryM0isnotsufficientbyitself. A22notimplementedornotrunyet; doNOTclaimXNUdomainworksfromAndroidprofile. A18APMMAP remainswirepacket-onlyuntilownIOVAmappingqualified.


## A22 disabled-bank control access experiment (hardware running)

User requested continuous sound work. NativeCB46profileisnotallocationpermission. New helper uses freshfullinventory, rereadsCR0/ACR/IDs/everySMR/S2CR, chooses firstunreferencedcandidateM0outsideNUMS2CB, exactSCTLRsnapshotmatch. ChangesONLYdormantSCTLR.CFCFGbit7withMremaining0; immediatelyreadbackandrestoreoriginalevenambiguouswrite, verifiesroutesunchanged. NoSMR/S2CR/global/TLB/table/DSP/DMAwrite. Resultmeanscontrolaccessonly,notsecurebankownership.

Actualkernelwriter5gatesrequiresmode8/Waffle/bootoptin/active/contextbase+exactoffset; onlyoriginalororiginal^80accepted, bothM0. Shutdownpermitsrestoreonly; panicrestoreusespersistentsnapshot. Host16readfailures/4ambiguouswritecases/denied/changedroutes/active/referenced/noisolationPASS; actualadapterboundaryfixturePASS. Loaderpolicyallowsnewtokenonlyisolatedadsp8/return<=60, defaultbuilddenies, unknown/duplicate/GPU/multicorerefused. CLIflagrequiresaudioiommuanddedicatedsourceboundmanifestbeforeUSB. FullA22kernelbuild/currentcompiledsources/rootimagehashespairedvalidationPASS. FirstpreUSBmissingautomaticloaderdeclarationrefused,nophoneaction; preservedauto-a22-preusb-manifest-refusal.log. CorrectedmanifestforalreadyautomaticMuimage; auto-a22.log session96397 runningauto20261106T092339Z soleUSBowner. NootherphoneaccessuntilreturnAndroid. NoA22PASSclaimbeforeactualreadback+restore+Androidrecovery.


## A22 actual XNU PASS: disabled context control access

Run20261106T092403Z/auto092339Z runner0/success1/Android1. FreshinventorychoosesCB6, unreferencedM0; original05c9a70e->test05c9a78e->original, changed1/restored1. NoMenable/routes/DSP/DMA/TLB/globalwrites. Actualhardwarecontrolaccessconfirmed, nosecure/permanentownershipclaim. A22-result.json exacttracehash. FirstpreUSBmanifestrefusalpreserved. NoUIaudiooutputclaim.

## A23 tables and native attribute proof; disabled table profile building

AndroidownDMAmapkprobeactualprot7(READ|WRITE|CACHE),4KiB,domainquirks0. Actual pinnedqcom-io-pgtable-arm.c protectionfunctioncompiled producesf44attributes/PAGE3=>f47exactly. Newwaffle_audio_page_tables.h acceptsdistinctown36bit/4Ktable+dataPAsandinteriornativepoolIOVA, createsonlythreepresententriesL1/L2/L3, onepage andbothguardsunmapped. CPUmodeltestsrefusealiases/overflow/outofpool/alignmentbeforedestinationmutation. NativefunctioncomparisonPASS, noGPUABIcopied.

IMPORTANT: ID04c017e6bhasATOSNSbit26set. NativeTRANS_OPSrequiresNOTATOSNS, soordinaryCBATS1PRhardwarewalknotavailable. Nativeqsmmuv500overrideusesTBUhalt/power+ECATS; doNOTinventordinaryATOSsupport orclaimsoftwarewalkashardwaretranslation. NeedqualifyTBUroutebeforenexttranslationprobe.

A23 minimalcurrenthardwarestep isDISABLEDtableprofileonly. NewhelperafterA22successfulclaim savesTCR2/TTBR0/TTBR1/TCR/MAIR(two32bitwordsperTTBR), writesnativeprofilepointingOWNnewtables, readsall8words, reverserestore+readall, checksM0unchanged. NeverwritesSCTLR/SMR/CBA/TLB/ATOS/DSP. Host26readfaults/32ambiguouswritefaults/deniedreadback/refusalPASS. Actualkernelwriterallowsonlyexpected8offsetsandsaved/targetvalueswhenprofileactive, shutdownrestoreonly. Persistentsnapshotpanicrestore, incompleteconfigrestore retainsbackingratherthanfree. Allocateown16KiB wiredspace/3tables+datapage; cacheclean is preparationonly(nohardwarewalkclaim). ExistingA22ordinaryoptinflagselectsfreshsource-boundartifact; defaultmode8stillreadonly. Strictcurrentheaderbindingandpostcheck added forcompiledAUDIO_CB_CONFIGmarker.

Freshfullbuilddiagnostic-audio-cb-config-a23 build-a23.log session70104running, noUSBowner. Freshroota23-rootbuilt/currentadspbound. Freezecompiledinputs, finishbuild/packagekernel/currentcompiledheaders/rootimage/automaticflag, pairedvalidate thenoneisolated60secaudio-cb-accessrun. NohardwareA23resultyet. Userrequestscontinuoussound, notCrisp.

2026-11-07 A24 candidate: user cancelled UniXNU GPU integration and resumed audio. A23 first cause not proven; per-register expected/actual/read/mismatch instrumentation added. Preserves writes/rollback and all8reads recorded. Host ASan/UBSan failures/restorePASS. No new hardware result.

A24 run20261107T082650Z: accessPASS,configured0,restored1,writes16. All8reads valid; onlyTCR2 offset10 expected38011 actual38071 differs60. SevenTTBR/TCR/MAIR fields exact. ArmIHI0062D.c16.5.39 defines bits6/5 TBI1/TBI0, NOTreserved. Do not mask. Next inspect disabled CB CBA2R.VA64/CBAR format and resetTCR2 before changingwriteorder. Android confirmedtrue, noDSP/DMA.

A25 candidate hypothesis: inherited disabled bank may be VA64=0 while tables/nativeTCRtarget V8L. ArmIHI0062D.c CBA2RVA64 bit0 selects V8L. Add before/after read-only CBAR/CBA2R/TCR2 log, no additional writes; compare unchanged state after A23 rollback. A24 alone does not prove format mismatch.

A25 run083357Z: beforeCBAR0/CBA2R0/VA640/TCR240028063; afteridentical unchanged1. Confirms bankformatnotV8L. TableprofilestillTCR2mismatch60. Next implement owned-disabled format setup+restore; CBAR0 also is not requestedstage1encoding. Do not claim format change alone solvesTBI. NoDSP/DMA.

A26: nativeformatsetup CBA2RVA641 thenCBAR1f300,immediateexactreadbacks,8tablewords,reverse10wordrollback. Targetvaluesderivednativearm-smmu.c notAndroidbankconstants. Host34readfail/40ambiguouswritefails+formatcoercionPASS. Fullbuild/root/pairedvalidationPASS. Runner57851active,hardwareunqualified.

A26run090316Z FAILEDkernelabort: PCwr strw1[x0], FARoffset1018CBAR6,value0. LRbranch comparedsavedvalue -> rollbackwrite. Initialformatprogrammingnotprovenrefused. Androidtrue. Restorationnotqualified. Removeddirectformatwrites; activeconfigrequirespreexistingstage1/V8Lbeforetablemutation. A27READONLYcandidateformatinventory buildactive. Architecturalreview: M0/unreferenced isnotownership, CBARzeroStage2restorationnotusable. No moredirectformatwrites basedonfreebankassumption.

A27run090834Z READONLYPASS(originalrunner0):65candidateformatsread1 allCBAR0/CBA2R0. No existingStage1V8Lbank. Rulesoutsimpleswitchbank. NeednativeAndroid allocation/programming/HYPmediationaudit beforemorewrites. ArchitectureassumptionfreeM0bankimpliesusablecontext rejected.
