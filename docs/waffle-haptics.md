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


## November 6: calibration and diagnostic integrity

Root access supplied by the owner allowed read-only capture of the native motor calibration: RC count574, open-loop7692us, closed-loop7550us and reported132Hz (motor9999). ColorOS Crisp is still in progress: the existing bridge emits bounded16ms taps, not the original shaped waveform. Native FIFO configuration was read without FIFO writes.

Torch diagnostics now use the existing bounded loader line writer instead of individually locked characters. H13 retained all service-ready records under seven-core GPU load. Its complete run remains failed: an unrelated GPU BO publication record was interrupted by concurrent output. No full-session pass or stability improvement is claimed for H13.

A separate private PID1 GPU experiment, S20, passed native IOSurface output:1218000 pixels checked, zero mismatches, CPU reads directly after completion, no glReadPixels, backing restored, and automatic return to Android. This validates the isolated output transport, not SpringBoard integration or a measured FPS increase. Experimental native-output code is not promoted by this haptics update.


## November 6: native FIFO transport qualified (H16)

An isolated one-core RAM test completed with runner exit0 and confirmed Android recovery. The native FIFO counter changed0→144→0 after36 four-byte zero uploads and a native flush. Saved status selectors and SoundWire input configuration were restored. No FIFO playback, sample-clock/calibration change, voltage change or boost write occurred in this phase. The existing16ms direct-play baseline followed successfully.

H15 established that zero count may coexist with cleared empty/full flags; the stock native driver uses the count. Its original run remains failed due to an ambiguous4KiB log overlap. A unique8KiB exact overlap recovered the evidence; the collector now expands the exact suffix instead of guessing or skipping bytes. H16 passed with the corrected collector.

A normal Android CLICK was observed selecting native style0/effect1. The device JSON configures that entry as144 samples at24kHz. This identifies a candidate native click shape; it is not yet replayed by iOS. ColorOS Crisp playback and ordinary boot integration remain pending. This update records private diagnostic results and does not promote the experimental FIFO implementation.
