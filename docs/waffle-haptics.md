# OnePlus 12 haptics

The native PM8550B HAP525_HV motor controller works through SPMI. A short hardware pulse was felt by the user; the following PCM-device test produced three short taps, also felt by the user. These are bring-up tests, not a claim that keyboard feedback or all CoreHaptics effects work.

| Component | Result |
| --- | --- |
| Controller identity and native power state | Verified, read-only |
| Short pulse, stop and register restoration | Verified; 16.09 ms in H04C |
| Mono S16 PCM to `/dev/redwood-haptic` | H05 passed: three taps, no client errors |
| H05 pulse duration | 17.097, 16.049, 16.048 ms |
| iOS Actuator routing and keyboard/system feedback | Pending |
| Continuous waveforms and variable intensity | Pending |

The diagnostic bridge queues PCM onsets and emits a fixed short tap at qualified amplitude, with an 80 ms minimum interval. It sleeps while idle, stops on failure, and retains the checked exit path. It does not modify the firmware-owned boost bank. The legacy Awinic driver belongs to different hardware and is not used.

H05 returned to Android successfully with original runner exit 0. H04C's motor test passed and was felt; its original overall runner failed because early proof lines rotated out of the final snapshot. Exact overlap recovery preserved the full trace and confirmed the component; that collection path was corrected before H05.

Speaker audio is separate: native ADSP boot and APM graph control are verified, but PCM DMA and the amplifier route remain unfinished.
