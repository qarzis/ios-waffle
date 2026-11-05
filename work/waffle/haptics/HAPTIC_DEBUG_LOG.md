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
