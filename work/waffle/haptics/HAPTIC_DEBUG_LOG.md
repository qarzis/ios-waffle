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
