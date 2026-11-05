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

## System path verified (H08/H09)

The missing `/product/haptics` node prevented MobileGestalt from selecting the PCM Actuator path. Publishing the existing generated identity in the dedicated test changed CoreHaptics `supportsHaptics` from 0 to 1. A public CoreHaptics transient and system vibration 4095 produced actual HAL PCM and two native motor pulses before three independent control pulses. Each stopped and restored its registers. H08 and the separate-worker H09 both returned runner exit 0 and Android confirmed.

This verifies a bounded tap approximation, not full waveform fidelity, long vibrations or intensity control. The service uses a separate sleeping worker so torch initialization can continue. It remains opt-in; ordinary GPU boot integration is a separate H10 experiment and is not yet claimed working. The driver requires the existing native haptic identity only when its checked PCM service is selected. The staged source exposes `waffle_haptic_test=1` for a one-shot and `=2` for the PCM service; the accompanying loader policy must explicitly admit the requested bounded mode. Do not enable unrelated donor peripherals.

H10 subsequently passed the first bounded joint test with guarded GPU desktop rendering, the threaded haptic PCM service and torch service, using one XNU core. Original runner exit 0 and Android return were confirmed. Its GPU window intentionally ended after 60 seconds. This does not establish multicore joint stability, indefinite runtime or a new FPS result. Further tests were stopped at the user's request.
