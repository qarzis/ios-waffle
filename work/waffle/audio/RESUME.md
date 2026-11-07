# A27 PASS readonly; architecture ownership blocker

Run20261107T090834Z 65candidatesallread1/CBAR0/CBA2R0. No preformattedstage1V8Lcandidate. Originalrunner0/success1; checkAndroidfieldinlatestautolog. A26rollbackCBAR0abort retainedseparately and directformatwritesREMOVEDfromactivecode. Active8tabletestrequirespreexistingstage1VA64beforewrites(host28read/32writefailPASS). NoactiveUSBtest. Next nativeAndroid context ownership/programming path versus actualGR1virtualization; no moreblindbankformat experiments. A27-format-inventory.json stores65records. SoundstillnoPCM.

# ACTIVE A27 readonly format inventory build99339

A26run090316Z panic strw1[x0] at CBARoffset1018 value0 DURING RESTORE, not provenfirsttargetwrite. Androidconfirmedtrue. Directformatexperimentremoved from activecode; noCBAR/CBAwritesallowed. A26-result.json+patchsaved. Header nowrequires preexistingstage1CBARtype1+VA641before8tablewrites; host28read/32writefail+badformatzerowritePASS. macan_adsp.c adds readonlyAUDIO_BANK_FORMAT per candidate. Build99339 logaudio/build-a27.log. Next root/validate then run --audio-preflight --audio-iommu WITHOUT --audio-cb-access (readonly) toinventory allformats. DoNOTretestA26/formatwrites or claimownershipfromM0. Needrevisearchitectureafter3experimentsA24/25/26.

# ACTIVE A26 format programming hardware runner57851

Artifact diagnostic-audio-format-a26 fullbuild/root/pairedvalidationPASS. Log audio/auto-a26.log. Header now10fields: original8 plusCBARindex8/CBA2Rindex9; order9,8,0..7 and immediateformatreadback, reverseall/restoresnapshot. Strictwriteronlyexactselectedformataddresses andsaved/target. M0/routes/DSPunchanged. Nativearm-smmu.c CBA2Rfirst1 thenCBARstage1+WB/NSH=1f300. Host34read/40writefailuresPASS+modeledA24TBIcoercionPASS. Needactualresult/AndroidbeforeotherUSB.

# A25 confirms inherited bank format mismatch

Run20261107T083357Z CB6CBAR0/CBA2R0/VA640/TCR240028063. Afterrollbackunchanged1. NoV8L despiteV8Ltargetprofile. Next qualify CBARstage1/CBA2RVA64 setup whileM0 with reverseformat+table rollback and exactreadback, extendstrictwriteronlyselectedbank. Notyetimplemented. Runner11777 Androidrecovery maystillactive; waitbeforeUSB.

# ACTIVE A25 format inventory build

Session30059 log audio/build-a25.log. Onlyreadonly added to macan_adsp.c: before/after GR1CBAR1000+4cb, CBA2R1800+4cb,TCR2cb+10. NativeArmSMMUdefines CBA2R800 withinGR1/VA64bit0; before/after checks unchanged. No format writes. HypothesisA24TBI60mismatch could reflect VA64=0, unproven until read. Next package/root/validate/run same A24 --audio-preflight --audio-iommu --audio-cb-access.

# A24 RESULT — only TCR2 bits6/5 mismatch

Run20261107T082650Z auto082626Z Androidtrue. Access1/configured0/restored1/writes16,readmaskff/mismatch01. TCR2expected38011 actual38071; sevenotherregistersexact. Bits6/5TBI1/TBI0 per local ArmIHI0062D.c16.5.39, NOTreserved. Next disabledbankCBA2R.VA64/CBAR format proof; do not maskreadback or guesswriteorder. NoactiveUSBowner/DSP/DMA/playback.

# A24 READY — audio priority, phone unavailable

2026-11-07 fullbuild+firmwareroot+pairedcontainerPASS. Artifact diagnostic-audio-readback-a24. Eight AUDIO_CB_FIELD expected/actual/read/mismatch outputs, no write-order change. ASan/UBSan hostPASS, exactcurrent/snapshotbindings verified. ADBdevices empty; async request pending. No USBtestowner. Next: python3 tools/run-waffle-auto.py --artifact work/waffle/diagnostic-audio-readback-a24 --audio-preflight --audio-iommu --audio-cb-access . Phone will reboot/test/Androidreturn. Do not claim DSP/playback. UniXNU workingintegration removed; historicalGit retained.

# ACTIVE audio resumed; UniXNU integration removed by user request

2026-11-07: removed UniXNU GPU working integration/binaries/reference repos; pre-integration GPU restored, shared files restored from A23 source where present. Historical Git commits retained. Removal manifest UNIXNU_REMOVAL.json. Current audio blocker remains A23 disabled CB table readback, restored1/configured0. Added actual/read/mismatch fields for all8 registers and AUDIO_CB_FIELD output; no register sequence/value change. Host sanitizer tests PASS26read/32write failures+restore. Next full build and bounded A24 readback diagnosis, not DSP playback yet.

# ACTIVE UniXNU audit after A23 failure; phone returned Android

Userprovidedhttps://github.com/UniXNU/UniXNU. Pinnedlocalreferencee2fdae4312d0acc3d8a52bc457101e7918095e6a, ArmSmmu4K83969cd, PaganiSM8750board25b1109, actualaudioforkShad0w23333drivers3d570b7. Readwork/waffle/unixnu-audit/AUDIT.md+provenance.json. UsefulACTUALmodernGPR/APM/PaganiReach+PaganiAudioHALreference andArmSmmu4Kownedcontext/rollback; NOTAPR-only. DonorSpeakerhost-only/neverdevice, SMMUpassthrough+rawphysicald0000000NOToursnativeDMA, noaddresscopy/binary17.7offsetpatch. CoreSM8550/A740notA750qualification.

A23testcompleted original1/Android1;CB6configured0/restored1/writes16, noM/SID/DSP. All8tablefieldswrittenbutatleastonereadbackfailed; missingperregisterinstrumentation. Root causeNOTyetproven. NativeUniXNUProgram.c ordersCBAR/CBA2R +TCR2/TCRbefore64bitTTBR; oursA23TTBRbeforeTCRand32bitsplit/nocontextformatsetup. NEXT: minimalperregisterexpected/actual/mismatchlogging(nohardwarebehaviorchange) thenoneisolatedrun; donotjustreordermultiplethingsorcopydonorregisterliterals. NativeCB_ATOSunsupported(ID0ATOSNS1), ECATSviaLPASSQTB0x7b3000; SIDrange1000..1400/iovawidth32/interconnectvotes; routefileA24-native-tbu-route.json. DoNOTrunATS1PR.

NoactiveUSBowner/build. PhoneAndroidafterA23confirmed. A22controlaccessPASS0/Android1. A23tablesnativeattributehostPASS(f47prot7quirks0), buthardwareconfigurationNOTpassed. Currentkernel/sourcesA23newheadersuncommitted; preservemainindex/privatecheckpointworkflow. UpdateHAPTICworknotpriority, userwantssoundcontinuous. Publiclastf65c9db. No shutdownrequest.

# ACTIVE A22 hardware control-access test

SoleUSBownerauto-a22.log session96397/auto20261106T092339Z. Fullfreshartifactdiagnostic-audio-cb-access-a22 +a22-root, kernelsources/imagepairedvalidated; firstpreUSBmanifestrefusalpreservedthenautomaticUSBflagcorrected. Runouter --audio-preflight --audio-iommu --audio-cb-access. NoextraADBuntilcomplete.

Kernelmode8explicitwaffle_audio_cb_access1only: freshfullinventory/rereadglobal/routes, choosefirstcandidateunreferencedM0, toggleONLYCFCFG80whileM0,readback,restoreincludingambiguousfailure,reroutescheck. NoSMR/table/TLB/DSP/DMA/ampwrites. Writerexactbase/offset/twovalues/5gates,stoprestoreonly,panicpersistentsnapshotrestore. Helperreadfault16/writefault4/denied/route/active/isolationtestsPASS, actualwriterfixturePASS, loaderpolicydefaultvsuser8negativesPASS,CLIflagmissingparentrefusedbeforeUSB. ReadbacksuccessONLYprovescontrolaccess,NOTsecureownership/DMA. Actualpostcheckerrequirespassed/admitted/changed/restored andM_enable0route_writes0DSP0. NeedresultsafterautoAndroid1; retainoriginalfailureifany.

A21nativeprofileCB46ASID46/stage1/4K/IAS36/OAS36/TCR80351c/TCR238011/MAIRf404ff44+efe4/SCTLR0a5f10e7confirmedactualnativebuildercfg77da. DoNOThardcodeAndroidCB46orcopyphysicalTTBR. A18MAPpacketuntx. Userprioritysound,Crispdeferred. H20notdevice-tested. PublicVibration✅f65c9db. Mainindexpreserve/privatecheckpointlast a7a60b38; newA22filesuncommitted. No shutdownrequest.

# ACTIVE A21 native SCTLR consistency PASS; phone reconnected

UserconnectedAndroid,independentboot1/rootKSUconfirmed. Nohardwaretestowner. A21actualnativeown4KiBDMAimport/unmap0/privatekprobecontextprovescb46/asid46/cfg_sctlr77da/cbar1/fmt1/stage0. Actualpinnedfunctionarm_smmu_lpae_sctlr+definescompiledandmatches0a5f10e7cachedSCTLRexactly; highbitsarenativecacheattributesnotrandom. a20-native-domain/sctlr-proof.py PASS, A21-result.json/hash. Androidprofilecompleteenoughforstage1config,NOTXNUbankownership. Allownkprobe/instancesremoved/globaltracing0.

NextA22needsimplementboundeddisabled-CBcontrol-accessprobe: freshcompleteinventoryexcludeallvalidroutes/enabledorphan/choosecandidate/perbootexclusiveclaim,snapshot,changeonlydormantfaultbitwithM0,readback,restore; noSMR/DMA/DSP. ExistingA15candidatealoneNOTpermission. Header/transactionnotyetimplemented. DoNOTcopyAndroidphysicalTTBRorassumeCB46reservedforallboots. NativeTCR/MAIR/SCTLRderivedandconfirmedfromliveconfiguration;useownnewtablesaftermappingqualified. Noactivebuild. Userprioritysound,Crispdeferred/H20notdevice-tested. PublicVibration✅f65c9dbpushed; periodicpublicdocsallowed; privateAndroidtraceaddresses/binariesnotpublish. NeedprivatesaveA19/A20/A21newsource/results/logswithouttouchmainindex.

# ACTIVE sound A20 native domain captured; phone disconnected

Prioritysound,userdeferredCrisp. H20hapticbuildexistsbutNEVERdevice-tested. PublicREADMEVibration✅commitf65c9dbpushed. Noactivebuild/USBowner.

A20Androidrootread-onlykprobesonactualmodulefunctionsconfirmCB46/ASID46/stage1/AppsSMMUphysical15000000/numpage128/pgshift12. Nativeown4KiBDMAimport/unmap0onallruns. ActualTLBpage174=128+46, USB47distinct. NativecachedCBstateTTBR0002e0008f5ca1000/TTBR1002e000000000000,TCR0080351c/TCR200038011,MAIRf404ff44/efe4,SCTLRcached0a5f10e7. DecodeIAS36/OAS36/4Kpages. NOTliveMMIOreadback; cachedSCTLRnotyetverifiedandAndroidphysicalTTBRmustNEVERbecopied. Layoutproofa20-native-domain/layout-proof.c staticassertsprefixcfg48/stage72/smmuio16/numpage24/cbs80/cbstride48PASS, fieldsphysbase/pages/ASIDcrossvalidateobservations. A20-result.json+4tracesrecordhashes. Address/contextobservationsprivate.

Allisolatedinstances/kprobesremovedaftereachrun,globaltracing0. LastattemptcfgbitfieldprobeFAILEDpre-registrationbecauseADBdevicegone. Noorphanprobe. PhoneUSBcurrentlydisconnected; donotclaimready. ContinuehostimplementationwithoutUSB. Next: boundedperbootSMMUbankreservation/candidateclaimexcludeinheritedroutes/enabledorphans/rollback; previousA15M0onlyNOTownership. NeedqualifieddisabledbankcontrolaccessbeforebindingaudioSIDorDSPmap. NofixedCB46constant/donor1801/rawPAsubstitute/globalreset. A18APMMAPABIhostPASSstillnottransmitted.

# ACTIVE AUDIO priority — user deferred Crisp, vibration marked working

User explicitly wants sound now; stopCrisp/H20 device work. H20fullbuildcompleted,nohardwaretest. PublicREADMEVibration✅ CoreHaptics/system tested, Crisp pending; commitf65c9db pushedfork/waffle/gpu-bringup.

A19 NEW actualAndroidDMAproof: userrootADBavailable, /dev/msm_audio_ion nativeimport/unmap ioctls frompinnedUAPIblob96cdc6908e5f38e8b45a4f406412f1c9ffab2857 (pathinclude/uapi/audio/linux/msm_audio.h, revision38d503...). ScalarFDargument confirmedactualdriver. FreestandingARM64android-dma-import-probe.c allocatesown4096BsystemDMAheapbuffer, importsMAP40046161,UNMAP40046162, closesFDs, noHYP/DSP/PCM/mixer. Exit0/import0/unmap0. Isolatedtracefsinstancefilteredgroupmsm-audio-ion captured2/2events:map_pages/unmap_pages sameIOVA1fff7000,size1000,group`soc:spf_core_platform:qcom,msm-audio-ion`. A19-result.json/trace. Domainpreexists,soCBnumber/ownershipnotyetproven; noXNUDMAqualificationorclaimedvoice. NativeIOVAfallingneartopconfirmsactualpooladdress,notrawPA. Nextobserveactualnativedomain/stream/CBattachmentorreadnativepage-tablecontext withroot; donotpickfreebankblindly. A18MAPpacketstillhostonly/untransmitted.

Tracefsdebugfsmountedread-onlyobservationpurposeviaordinarymount; noMMIOregisterwrites. Created/removedprivateinstanceswaffle_audio_audit/waffle_audio_dma, globaltracingoffuntouched. Firstsystemsoundquerycreatednoaudiomaps(inconclusivenegative);directownDMAprobeispositive. PhoneAndroid/noUSBowner. Rootcapturesandaddressesprivate,nouploadneeded. No shutdownrequest.

# A18 host ABI PASS, DMA ownership still next blocker

2026-11-06: waffle_apm_memory.h serializes one native taggedIOVA MAP44 and UNMAP28 without GRAPH_OPEN's16-byte command header. Actual Linux functions compiled/bytecompared10size/SIDcases and negativeoutofpool/rawPA/unaligned/overflow/invalidinput testsPASS. No integration/transmission toDSP, noDMA/PCM. Corvette3848a296 audio reviewed and stillAPR/ASMstream1801, notWaffleGPR/APM1001/1061. HapticsH05nativePCMtapbridgepassed separately; no speakersoundclaim. Publicdocs fba59b2 published toqarzis/ios-waffle waffle/gpu-bringup.

# HakiOS 2.3.4 source review — 2026-11-05

Pinned donor 2631f5d (full revision in ../hakios-2.3.4-audit/provenance.json). Current drivers/audio/hakios.sound.c still uses APR AFE/ASM/ADM and stream1801; it does not supply a Waffle GPR/APM DMA backend. Existing qualified A13 graph remains unchanged. A16 CLIENTPD=0 refutes global-disable blocker; bank ownership/attach remains unresolved. No PCM or sound claimed. H02 haptic host/full build underway, no new audio hardware test.

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
