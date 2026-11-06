# ColorOS Crisp: native waveform handoff

## Verified inputs

Pinned OnePlus qcom-hv-haptics.c e39bf7032e38c547d588372a11a5dd55eb714860, not the donor Awinic driver. H12 reads HAP525_HV PTN08=01,24=e0,2a=00,2b=10,a0=8f. The native MMAP FIFO mask gives 15*128=1920 samples. FIFO ready is not evidence that it is empty. HBST ownership remains firmware-only.

The actual Settings controller maps Russian Хруст / English Crisp to touch_style_vibration_intensity=0 and native preview effect640; soft maps1/effect647. Private RichTap HE preview has five events, not a single short direct-play pulse. HE frequency values are proprietary normalized parameters, not Hz. The ODM def effect0 is263 signed bytes at declared24kHz (10.958ms), but effect0-to-Crisp event mapping is not proven. No private APK, HE asset or waveform is for publication.

## Current blocker and hypotheses

1. Most supported: current PCM bridge deliberately reduces every accepted onset to a fixed16ms DirectPlay pulse, so it cannot preserve the ColorOS shape or frequency. Evidence: waffle_haptic_pulse.h and actual H08-H12 traces; no FIFO data-port writes. Test: one isolated, bounded signed-sample FIFO transaction, with full restore and measured drain, after the prerequisites below. Expected: FIFO fill increases by sample count, drains, HPWR goes disabled; no need to infer waveform fidelity from a player ACK.
2. Native24kHz requires the RC clock/calibration handoff implemented by haptics_set_manual_rc_clk_cal. Existing H12 survey does not capture the calibration count or multiplexed FIFO fill. Test first: read Android exposed calibration values if permitted and capture the exact native selector/register protocol. Do not substitute another device calibration constant. Expected: per-device calibration value or explicit missing-input result.
3. A native FIFO wave alone may still differ perceptually from the Settings RichTap preview because proprietary HAL selection/shaping is not established. Test only after the transport works: map effect640 through the actual local HAL/assets; then compare bounded low-amplitude playback. Do not rename def/effect0 as exact Crisp without this link.

## Minimal implementation boundary

Keep DirectPlay and default boot unchanged. Add a separate opt-in FIFO transaction only after ownership/idle/calibration can be proven. Read/save selector, rate, calibration and MEM_OP_ACCESS fields. Native fill status uses CFG status selector0x8005 (selector writes must be restored); FIFO_READY alone is insufficient. No data-port reads or assumed data-port readback. HAP525 uses four-byte PTN20 writes plus PTN2c for tail bytes; non-refill flush is MEM_OP_ACCESS bit0 set then cleared. Preserve pattern-memory access/selection and rate upper nibble. Restore every altered field after successful drain/stop; ambiguous writes require STOP and quarantine rather than claiming completion. Never write HBST.

First candidate must fit native initial-program limit320 samples and measured capacity. Bound duration below30ms, scale amplitude conservatively, no refill/interrupt integration yet. Qualify every read/write failure, uncertain start/stop and timeout using the actual transaction on the host before hardware. Then require hardware completion, restored registers, no fault and automatic Android recovery. Compilation and subjective vibration alone do not qualify a full waveform driver.


## Device calibration obtained with user-enabled root

Read-only Android sysfs capture android-root-calibration.txt: RC clock count574 (native count bytes02/3e), open-loop period7692us, closed-loop7550us, reported132Hz, motor9999. Native24kHz enum is10, so preserving observed rate upper nibblee0 would giveea; this is a planned field value, not a hardware write. CAL_RC_CLK mask0c requires manual value08 with unrelated bits preserved. Current sample FIFO voltage7900mV must NOT be copied into initial test settings; retain qualified2400mV ceiling and scale waveform amplitude. Selector CFG71=80/CFG70=05 selects FIFO status; save/restore both before interpreting CFG09/0a as fill (high low4bits, emptybit6/fullbit5). No selector, RC calibration, rate, boost or FIFO writes have yet been performed by this work.
