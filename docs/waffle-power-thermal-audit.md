# Waffle thermal and latency audit — 2026-11-04

This is a source audit and a post-return Android snapshot, not an iOS thermal qualification.

## Measured results

D07 changes only the reserved second framebuffer mapping from device memory to WCOMB, matching the existing boot console RAM mapping. Initial B copies fell from31–36ms to1.7–1.9ms. The user reported smoother motion, with tears remaining.

D08 serializes the producer until full presentation finishes. Source changes disappeared from the collected observations and the user reported tear-free scrolling, but severe lag and heat. Some framebuffer logs report about10fps. D09 releases the producer after CPU source reads finish, before the private working-frame copy and hardware commit wait. It is built and host-tested but not yet phone-tested. Neither candidate qualifies60fps or continuous thermal stability.

After D08 returned to Android, fresh readings were approximately battery40C, CPU/GPU49–51C and shell45–46C. Android also contained higher cached readings, including CPU95C; their timestamps and execution phase were not established. Do not call them measured iOS peaks.

## Source findings

* `osfmk/arm64/cpu.c` defaults to WFI enabled. The generic PSCI patch avoids destructive cache maintenance on idle; it does not remove WFI. No evidence supports replacing idle assembly here.
* `osfmk/kern/clock.c::_clock_delay_until_deadline_with_leeway` blocks the thread when preemption/interrupt state permits and spinning is not required. The presence of `delay_for_interval` alone is not proof of a busy loop.
* The existing `macan_cpufreq.c` override is opt-in and the Waffle loader does not admit its frequency-control arguments. Its EPSS register base is0x18591000. The PJD110 live tree instead gives four EPSS banks starting0x17d91000. Do not reuse donor frequency writes.
* The GPU path enables native HWCG. That is distinct from full runtime idle/DVFS management. Current initialization does not qualify IFPC/NAP entry between frames, and the submit session retains its OOB ownership until close.
* Enabling IFPC alone would violate existing host assumptions: admission and memory-idle checks read GX registers while expecting GX powered. Native idle/re-entry also coordinates queue submission, power sequencing and saved state. Those paths need a separate ownership review and bounded validation; no new power register writes are included in this work.
* Previous UI roots repeated the CPU concurrency proof35seconds after startup. Seven cores were already qualified. The next manual-scroll root omits this artificial stress and automatic app workload, with GPU60seconds/kernel90seconds. This reduces diagnostic load, not a claimed thermal driver fix.

## Battery blocker

Recent iOS logs report SOC=-1. The live tree's battery service is `oplus,hal_sm8350` under PMIC GLINK with two cells; the channel `PMIC_RTR_ADSP_APPS` was observed open in A08/A09 audio logs. The pinned OnePlus v2 driver uses owner32778, request type1, battery GET0x30, USB GET0x32, SOC property4 and temperature property12. The local HakiOS donor's temperature ID13 is a different device ABI.

BAT01 queries seven properties exactly once, with strict24-byte reply matching, result/range checks and bounded waits. It sends no setters or notification/configuration commands. It neither supplies live iOS percentages nor proves the firmware's property map until compared with actual phone values. Build and host tests passed; hardware is pending.

## Next checks when the phone is available

1. Check the cooled Android temperature before any new load; do not infer it from cached HAL entries.
2. Run the separate read-only battery probe and compare returned units/values with Android before connecting it to IOPMPowerSource.
3. Run the short D09 manual scroll test, verify source stability and ask about tearing and lag. Preserve exact stop, framebuffer restoration and Android return evidence.
4. Only then consider runtime idle/DVFS implementation with native ownership/restore requirements. Do not mix a power transition experiment into the source-retirement test.
