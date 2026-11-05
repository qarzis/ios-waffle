# H05 bounded iOS PCM service test active

2026-11-05 user confirms H04C impulse felt and resumes. Added mode2 --haptic-service-test behind dedicated loader CPU1/return<=90 guard, outer CPU1/60sec only; cannot mix pulse/readonly/flash/audio/GPU. Existing HAL root has Actuator and /dev/redwood-haptic path. New cdev copies monoS16 in512B chunks, mutexqueue only, worker sleeps10ms, fixedqualified16ms/amplitude32, min80ms onsetcooldown, stale100msdrop; continuousPCM doesnotloopmotor. Faultquarantines service. Mode0/readonlyoff. NativeSPMIowner+PPIDgates/panicquiesce retained. Pureevent/actualPCMwriter testsPASS (new tests not yet in initial build mandatory list, run manually). H05 full XNU/EFI/pairedvalidatorPASS. Root rebuilt with publicAudioServicesPlaySystemSound(Vibrate) at35s, direct3PCM onsets at40s, distinctdirect_begin marker; directsuccessdoesNOTproveHALroute. Boundcurrent+snapshot kernel sources/events/loader and root hash, automaticrunactive (auto-h05.log). Do not touchUSB concurrently. Phone gets Android automatically. Hardware result pending.

# H04C FIRST PHYSICAL IMPULSE CONFIRMED — 2026-11-05

User felt pulse. Run204242Z: componentpassed1/start1/stopped1/restored1/emergency0/writes7; measured16090us, requested16000, amplitude32/255, noHBSTwrites. Originalrunner1 because finalrollingloglostearlyproof; preservedoriginal. Exactexistingmerge recovered2166215bytes/SHA79dcc8...981 without inferred/modified bytes and validatesallmarkers. Collector extended existingexactrecovery to --haptic-pulse, actualASTrolling/gap/defaulttestsPASS; no repeatboot merely forparser. Androidconfirmed1. H04C-result.json stores raw/streamhashes+userfeedback. H04Bneverstarted due loaderpolicy; dedicated allowlist/H04Cloader-onlyrebuildfixed (kernelunchanged).

Next connect existing iOS Actuator PCM path (/dev/redwood-haptic, present in root HAL) to a bounded tap worker. No iOS haptic service yet. Keep fixedqualified amplitude/duration, coalesce events/min80ms cooldown, sleep whenidle, quarantine on fault and preservepanicquiesce. Nativehardwarefirstpulse is proven; do not copy AW driver.

# H04B candidate — no pulse device test yet

Dedicated native16ms/amplitude32 transaction now includes persistent context, panic/return quiesce, measured active_us, post-restore fault check. Default off; only separate --haptic-pulse isolated CPU1/60sec accepts current+snapshot bindings and kernel hash; read-only flag cannot enable it. Host helper/actual writer+quiesce/CLI/binding tests PASS. H04 initial build was deliberately not booted because quiesce/final fault check were added afterward. H04B full build active (build-h04b.log); do not boot initial H04. H03 original0/Android1 remains last hardware evidence. Pulse not yet felt/proved on hardware; no iOS actuator service yet.

# H03 power survey PASS; H04 pulse candidate host tests

Run20261105T202626Z original0/Android1. VSETd4(force bits0),HBFOLLOW e0(auto hardware follow),HBEN00,CLAMP00. No PMIC/motor writes. H03-result.json binds immutable kernel-2.log. Four added read-only native power registers,26 total; all read-failure/observer gates tested. This is observed power policy, not guarantee of future firmware exclusion.

H04 candidate core/header and actual SPMI adapter: fixed amplitude32/255,16ms, stop/readback/poll HPWR20ms, emergency module-disable on uncertain stop, explicit CFG/PTN ownership, no HBST writes. Actual helper tested every read/ambiguous write failure, fault, stalled timer, stuck HPWR, exact restore; adapter tests opt-in/owner/PPID-under-lock and readback. CLI dedicated --haptic-pulse CPU1/60seconds, cannot combine read-only/flash/audio/GPU modes. New code still host/build only; before device, add/qualify panic/return quiesce and final fault check. Initial H04 build does NOT include those extra protections, do not hardware boot it. H03 is last device result.

# H02 hardware component PASS — 2026-11-05

Run20261105T201705Z/auto201641Z. All22 read-only registers captured: HPWR00(disabled),fault00,brake41,cl_brakee1,autores89,cal04. No PMIC writes or motor start. Immutable kernel-2.log SHA saved H02-result.json. Original runner1 due unrelated multicore proof failure (cpu-proof.json preserved); Android independently confirmed1 by outer runner. Do not claim overall success or pulse qualified. Native OnePlus constant-mode branch disables autores whereas inherited89 has enable set; do not blindly use inherited state. H02-stop-contract.md documents native fault/open-loop power/braking/stop dependencies. No active USB owner.

# H02 stop prerequisites — host PASS, full build in progress

2026-11-05 user resumed vibration/audio and requested HakiOS 2.3.4 review. Added six CFG-only read registers (HPWR 0b, fault 0c, brake50, closed-loop brake51, autores63, calibration72), pinned native qcom-hv-haptics.c definitions. Existing revision/allowlist/platform/mode gates retained; no write callback. Sanitizer helper checks all22 read failure positions and actual observer adapter passes. New line stop_survey=1 records raw prerequisites; not a readiness assertion. H02 hardware NOT tested. Build log build-h02.log, artifact diagnostic-haptic-stop-survey-h02. Existing H01 artifact/source bindings remain historical; do not use it with modified sources as if newly compiled.

Native enable/stop requires fault/power/braking behavior beyond PLAY_EN; no motor pulse implemented. Release donor remains AW86927 and APR audio; provenance/audit in ../hakios-2.3.4-audit/. Phone Android boot_completed=1 before build; no hardware owner.

# H01 read-only hardware identity PASS

Run20261105T192859Z originaloverall1(Android1)dueGPUlogging; componentcompletekernel2 rawSHA savedH01-result.json. ModelCFG4/PTN4/HBST0002(HAP525_HV/boostv0.2),enable80/play01(motorENbitoff),vmax30=2400mV,TLRA0602=7690us. CFGAPID591/PTN592owner0, HBST530owner3read-only; do notwriteforeignboostbank. Nativewa_flagsSW_CTRL_HBST onlyboostv0.1, notobservedv0.2. ActualAndroiddriverboundPM8550B. No PMIC/motor/resetwrites. Futureboundedpulse needs nativeDIRECT_PLAY/autores/brake/fault/stop policy and source-backedlimits; ordinaryiOShapticinterface notimplemented. GPUregressioncomparisonD22 usesoldD16kernel, soH01notactive.

# H01 read-only PM8550B survey ready

Android active driver confirmed qcom-hv-haptics bound to SID7 F000 liveDT. Native qcom-hv-haptics.c/debugfs downloaded pinned e39 and verified gitblob, upstream provenance saved. Macan/HakiOS Awinic driver is different hardware and stays gated off. Android shell class attributes were permission denied (no calibration values captured). H01 extends only existing Waffle torch diagnostic level1 with sixteen allowlisted CFG/PTN/HBST reads; no PMIC write interface, GPIO/reset/motor action. Normal torchservice level3 unchanged. CFG/PTN mustrevision4; purehelper+actualobserveradapter hosttestsPASS; fullhost/XNU/EFI/container build andpairedvalidatorPASS. Dedicated haptic_readonly manifest binds current/prepared/snapshot torch.c/header; outerblockscompiled observer ifunbound. Image diagnostic-haptic-readonly-h01 also D21 UI ordinary EAGLclearfix/E75 guard2, nativeimportsOFF. First hardwarepending. Need reportexactIDs/state before any pulse; calibration/boost/braking/stop/ownership stillunqualified.
