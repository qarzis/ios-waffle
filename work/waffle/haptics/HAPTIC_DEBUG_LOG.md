# OnePlus 12 haptic debug log

## Hardware model
PM8550B HAP525_HV, SPMI SID7 CFGf000/PTNf100/HBSTf200, liveDT and pinned OnePlus native driver e39bf703. CFG/PTNowner0,HBSTowner3. Donor AW86927/I2C firmware/addresses do not apply. No HBST writes.

## H01 identity
Read-only CFG/PTNrevision4,boostrevision0002,VMAX2400mV,TLRA7690us. No motor started.

## H02 stop prerequisites
Read22 registers. HPWRdisabled/fault0,brake41/clbrakee1/autores89/cal04. Componentpassed; overallCPUproof1 becauseparallel0.7. Androidreturned. Failure preserved independently fromcomponent.

## H03 autonomous power
Read26registers. VSETd4 forcedbits0,HBFOLLOW e0,HBEN00,CLAMP00. Original0/Android1. No writes. Supports a narrowly gated low-amplitude autonomous-hardware-follow experiment, not general boost ownership.

## H04/H04B/H04C one-shot
Initial H04hostbuild notbooted; H04Baddedpanicquiesce/finalfaultcheck, but loader refused unknown haptic_test token, kernel notstarted, no pulse. Specific loader buildflag/CPU1/bounded-time policy added and rejection tests passed. H04C reused exact H04Bkernel with newloader. Actual16.090ms/amplitude32 pulse,7writes,stopped/restored/emergency0. Userfeltit. Overallrunner1 becausefinalrollingloglostearlyproof; exactoverlaprecoveryverifiescomponentwithouteditingbytes. Collectorfixed for haptic probes, originalfailurepreserved. Android1.

## H05 PCM bridge
Exclusive mode2, cdevmonoS16 eventqueue and sleepingworker. Fixed16mstaps/min80mscooldown, sustainedinputdoesnotloopmotor; faultsquarantine. PublicVibrate at35s then3directPCM at40s. Hardware3directtaps17097/16049/16048us,7writeseach/stoprestorepassed. Userfelt3taps. Original0/Android1. NoactuatorHALlog or pulsebeforedirect_begin: systemrouteunqualified. Rawtimestampedprintfreplay excludedfromeventcount, retained inoriginaltrace.

## H06 completion/runloop request
Hypothesis: request-only client fails to process AudioServices completion/runloop. SamekernelH05, onlyclientrootchanged. Clientspawnedbutnocall-stageprintorbaselinepulse. Original1/Android1. FirstprintwasafterCFRunLoopGetCurrent/AddSystemSoundCompletion; exactblocklocationunknown. Do not treat this as hardwarefailure or confirmedrequest. No repeatwithoutinstrumentation.

## H07B public CoreHaptics and independent baseline
H07initialclientcompiledonly, notbooted. H07BusespublicSDKCoreHaptics query/init/start/singletransient; pre-callmarkers. Separate --direct-only job writes3PCM at47s so blockedframeworkcallcannothidebaseline. SameH05kernel/rootchangesonly. Pairvalidator/currentkernel/source/rootbindingpassed. Hardwareactive; inspectauto-h07b.log. No phonequestions orTelegramdependency (userunavailable).

## Other work
A18 host MAP44/UNMAP28 matches actual pinned Linux bytes; not transmitted/DMAunqualified. Corvette3848a296 pinned audit indicates sameSM8650/Adreno750 GPU but oldredwoodaudio/haptics; externalMetalbinarypairnotinrepo/localenv. No blindmerge.

## H07B result and H08 revised architecture
H07Boriginal0/Android1,3baselinePCMpasses,CoreHaptics_supports0/play1/noHALsamples. Sourceauditfound exactMGGetBoolAnswer(DeviceSupportsClosedLoopHaptics) andmissingproduct/hapticsnode, despitegeneratedidentityalreadyexisting. Thus threeprobesreplacedbyarchitecturecheck, no blindretry. H08service-onlynodehosttests+loaderUEFIbuild+pairedvalidatorPASS, notbootedbecauseuserborrowedphone. KernelH05unchanged. Probeone-elementarrayboundcorrectedbeforeH08. EvidenceH07B-result.json,H08-identity-diagnosis.md,rebuild-h08.py/build-h08.log.


## H12: readonly FIFO survey, logging failure preserved

Original runner exit1, automatic Android recovery confirmed. Exact overlapping snapshot stream SHA2084d902ecfb3db0e7387254933ac68948655d69c3afe9ac55a5c42c60637970. PTN08=01,24=e0,2a=00,2b=10,a0=8f: native FIFO present, capacity1920 samples. No FIFO writes. CoreHaptics supports1/play1 and direct client3/errors0 retained; no exact Crisp waveform claim. READY and format survived but cooldown text interleaved at character granularity. Root cause found in actual torch say() per-character loader_log_putc calls; reducing line size does not provide atomicity.

## H13: bounded record atomicity hypothesis (host PASS; hardware pending)

Use existing loader log lock once for <=64-byte chunks via existing loader_log_line; torch say() no longer locks separately per character. Interrupt-disabled maximum remains64 input bytes. No waveform or power change. Actual extracted formatter/wrapper sanitizer test proves short READY records use one write, long messages remain bounded/truncated correctly. Full build pending; do not mark test passed from host compilation.


## H13 result and three-run instrumentation review

Original runner1/Android1. READY, format and cooldown now complete; actual formatter change worked. Overall failure is `Missing GL BO publication` (also the actual first failure in H12, correcting the earlier attribution to haptic READY). Missing parsed publication731 is visibly split by launchd output; 730 and732 intact. waffle_smmu.c still logs ordinary BO messages per character. No GPU hardware-fault claim from this failed parser result. No fourth repeat of the same noisy seven-core CPU-proof combined test. Reassess evidence channel: use existing compact bounded BO records for future workload tests, and isolate native-output transport from CPU/haptic workload.

Root enabled by user: read-only calibration574/7692us/7550us/132Hz; motor9999, fifo_vmax7900mV and direct/cl2400mV captured. No register write, calibration action or motor playback performed. High native FIFO voltage is observation, not authorized test configuration.


## H14: native FIFO status selector transaction (host PASS, hardware pending)

Current blocker: FIFO_READY is not proof of empty FIFO; do not fill or flush from that bit alone. Native e39bf703 selector0x8005 is implemented as saved CFG71/70, select, CFG09/0a sample, restore both selectors and independently verify readback. Idle CFG4/PTN4/module80/PLAY01/HPWRdisabled/fault0, ready and native FIFO capacity admission required. Writes are restricted to CFG70/71; no FIFO data/flush/motor/boost action in this transaction. Ordinary PCM service/test2 unchanged. Only isolated haptic_test1 performs this survey before the already-qualified direct16ms baseline; survey failure blocks that baseline. Panic quiesce during survey restores only selectors, not motor/power.

Actual header sanitizer test covers14 read failures,8 ambiguous write failures,1922 fill values,revision/ownership/idle/refusal and exact restoration. Actual five-gate status read adapter and extended owner-checked writer/quiesce fixtures PASS. Read-only observer gates unchanged. Full H14 build plus fresh CPU root ongoing. Hardware checker requires empty1920-capacity and restored selectors; no passing hardware result yet.


## H14 result: flag-equality hypothesis refuted; safe refusal

Original1/Android1, first error missing bounded pulse proof because survey intentionally blocked it. Actual fill0/capacity1920/empty0/full0, status passed0/restored1/writes4, FIFOwrites0/motorstarted0. Saved selectors restored; no force/flush/motor test followed. H14-result.json retains immutable tracehash. Incorrect assumption was emptyflag == (fill==0): actual native get_available_fifo_memory never requires this equality. Inherited SWR_ACCESS=e0 (native SWR config/input enabled), so future FIFO writes/playback must explicitly establish no autonomous SWR writer; do not assume it is zero.

## H15 count-based status correction (device test running)

Removed invented flag equality; native count bounded by capacity is authoritative, raw high/low fields now retained, flags observational. Hardware checker still requires fill0/capacity1920 plus full selector restore and existing baseline stop/restore. Compiled actual pinned haptics_get_fifo_fill_status and get_available_fifo_memory against our helper:16384 count/flag combinations PASS, full1920 and overflow distinguished, H14zero/zeroflags accepted. Core error-injection and owner/quiesce fixtures PASS. Fresh H15 kernel/root/source/image bindings paired-validated, auto-h15.log session50163 running, soleUSBowner. No FIFO data or clock/boost writes.

## Private ColorOS HAL mapping investigation

With user-granted root captured liboplusvibratoreffect/libaacvibrator/libsivibrator/vendor vibration service privately under android-style/native-hal (hash provenance). Actual exported get_effect_stream_9999 walks60 entries,24-byte stride at ELF VA585ff8; soft table586598. IDs640/647 absent from these embedded tables. Embedded default ID0 is263samples24kHz and byte-identical to ODM def/effect_0.bin; embedded softID0 differs from ODM soft override. Thus preview API ID640 is not yet proven to map directly to table0. Continue vendor mapping before claiming original Crisp waveform. Never publish proprietary ELF/APK/waves.


## H15 actual result: component PASS, original collector failure preserved

Original runner1/Android1. Immutable snapshots show selector passed1/restored1/writes4, FIFO fill0/cap1920/raw0000, then baseline passed1/stopped1/restored1/emergency0/writes7, active16115us. Original error is ValueError ambiguous exact snapshot overlap at kernel173 (not motor failure). The 4KiB suffix matches twice with overlapping SQLite repetitions; the 8KiB suffix is unique and exact. Collector now increases suffix4K->8K->...64K only until a unique byte-exact overlap; still refuses gaps/ambiguous maximum/different payload. Synthetic periodic and rejection fixtures PASS. Recovered2175303bytes/SHA242f0937abda6befc18c1a1d0166d49d72261b5019f7508f995295eb09f5cb06. Offline actual haptic acceptance blocks PASS; never rewrite original exit. H15-result.json records both.

## H16 zero FIFO transport (building; no hardware result yet)

Separate helper only in isolated test1: saved selector/idle/exclusive admission, native HAP_DRV_STS0x0005 source check refusesSWR4, then saves/masks inherited SWR_ACCESS e0 bits per native swr_slave_reg_disable. Requires empty FIFO and MEM_OP_ACCESS0. Flush1->0,36 single-attempt4-byte zero commands (144samples), observe fill144, flush1->0, verify count0, restore selectors and SWR only if cleanup known clear. Never PLAY, rate, calibration, voltage or HBST writes. Unknown cleanup retains SWR disabled; panic/return never re-enables into uncertainFIFO. Source1-baseline still follows only successful transport. Actual header45readfailures/24configwritefailures*2ambiguity/72partialdatafailures PASS. Actual adapter verifies five gates, LE4B withlen3, exactPTN20 only, liveowner under lock, one attempt/noDINreadback. Existing status/observer/log/writer/quiesce regressions PASS. Full H16 build active; compiled inputs frozen.

## Native style mapping advanced

One normal Android CLICK (cmd synced prebaked0) produced actual aidl_vibrator log `perform effect1`, `findEffect vibStyle0,effectid1`, completed. Native JSON motor9999 def_style maps effect1 to ODM def/effect_1.bin@24000Hz,144bytes/6000us. This is evidence for native click selection/file configuration, not a live FIFO dump or iOS replay. Read-only actual binder getWaveformIndex returns640=-1,647=-1,type0=1; transaction IDs15/16/17 from local actual IVibratorManagerServiceStub. Private frameworkJAR decompiled methods confirm index is queried from system service. Androguard newer hidden-API domain flag4 retained numerically, instruction bytes/JAR untouched. Native-click mapping proof/ELF/JAR/waves stay private.


## H16 hardware PASS

Run20261106T080956Z / auto20261106T080933Z: original0/Android1. Actual status count0->144->0,36zero4Bcommands, loaded1/cleared1/selectors1/SWRrestored1. Native idle driver source7 observed (not source4/SWR). No FIFO PLAY/rate/cal/VMAX/HBST writes in H16 buffer phase; qualified16ms baseline followed. Recovered trace SHAe97632a41ad7ffa62a0f14f3f9ce562e6feeaa3e182c7e80817600fb3a14009d. Current strict actual acceptance blocks also PASS offline. H16-result.json preserves boundaries. Public docs checkpoint d58e692 records result without promoting pending code.

## H17 zero FIFO engine (host PASS, rebuilding before hardware)

Fresh root capture before H17 after user reconnect: RC574/t_lra7692us unchanged. Pure helper accepts explicit RC argument; only private diagnostic caller supplies574, not production/default calibration. H16 upload helper optional bounded consumer callback keeps SWR excluded while consumer runs. H17 consumer: fresh qualified HAP525/boostv2/VMAX<=2400mV/HPWRoff/PLAY1/fault0/SWRdisabled admission; save selector/FIFO rate/RC/CAL/autores, F24kHzlow10 preservinguppernibble, measuredRC574/manualCAL, autoresoff, PLAY80/sourceFIFO. Require144initial, monotonic intermediate counts, drain0 with4500..30000us timing. STOP0+HPWRdisabled, restore all changed settings and originalPLAY1. No VMXO/VMAX/HBST/data/flush writes from consumer. Fault/stale/stall/ambiguousstart alwaysSTOP; uncertainSTOP emergency module-disable with no restoration. Failed consumer keeps SWR disabled even if buffer subsequently clears, since clock restoration may be uncertain.

Actual helper60readfailures/17writes*2ambiguity plus frozenclock/stalledFIFO/instantempty/refill/fault/stuckSTOP PASS. Combined actual upload+consumer+cleanup fixture passes normal execution and confirms failed consumer/SWR quarantine, emergencydisable/noSWRreenable. Actual adapters prohibitrefillwhileplayactive, PCMservice/defaultmode2 unchanged. Logging now explicitly says buffer consumer1 instead of stale H16 motor_started0; play phase separately reports actualcontrol/results. Initial H17 host build never ran on device; rebuilt after combined-fixture quarantine correction. Fullbuild-h17.log active session24713, freezecompiledinputs. Needpackage freshkernel/image +boundH16CPUroot, haptic_fifo_zero_play_test true/haptic_fifo_rc_count574/newplayheaderbinding, validate, thenCPU1/60/hapticpulse. No USBowner until test launched. Never claim this plays Crisp: coefficientsstillallzero.


## H17 hardware FAIL (zero FIFO execution experiment1)

Original1/Android1. Actual initial144/last144/progress0/drained0 across30304us; STOP1/restored1/emergency0. Buffer loaded144 then cleanupflush0/selectorsrestored, SWRinputretaineddisabled after failedconsumer. No realwave/HBSTwrites. H17-result.json/hash preserves exactstream. Proven first blocker is no FIFO consumption, not transport, flags, calibration identity or compilation. Why still unproven.

At most three hypotheses: (1) strongest: clearing SWR_ACCESSe0 asserted SWR_PAT_RES_N(bit20) and disabledCONFIG_EN(bit80), potentially gating shared pattern engine; source names prove reset asserted, effect onFIFO is hypothesis. (2) FIFO power handshake/HPWRready absent (H17 lacked activeHPWR observation); nativeopen_loop_drive_config may require additional observedstate. (3) FIFO clock/manualRC mode doesn't run despite written rate; capturedRC574 and exactnativeenum10 makes randomcalibrationreplacement unsupported. Do not repeat or force boost.

## H18 minimal experiment for hypothesis1 (building)

Change only input exclusion e0->40 mask: SWRoriginale0 becomesa0, preservingCONFIG_EN/RES_N while inputbit40disabled. Playback admission now requires resetdeasserted20 and inputdisabled40. Add read-only activeHPWR/PLAY/FIFOready/power_seen and observedSWR to log. No other clock/voltage/data/handshake modifications. New81readfault cases/all17writeambiguity/stall/quarantine fixtures PASS. Nativeburst/owner/restoration regressions PASS. Fullbuild diagnostic-haptic-fifo-reset-h18 activebuild-h18.log session45163. PhoneAndroid, noUSBowner. Freezecompiledinputs; package/root/header/calbinding/validate thenisolatedCPU1/60test. If it fails, use observedHPWR/PLAY beforeanotherhypothesis; afterthreeunsuccessfulexecutionexperiments revisit architecture.
