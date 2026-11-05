# H05 PCM tap bridge

Scope: first iOS-facing mono S16 write device, /dev/redwood-haptic, matching the Actuator HAL already present in the test root. No driver replacement for speaker audio, no arbitrary continuous waveform playback.

Producer: 512-byte stack copies via uiomove outside the event mutex; signed16 PCM peak is calculated without INT16_MIN overflow. Threshold256. A non-silent onset queues one request; silence or a30ms inter-packet gap permits a new onset. One pending request coalesces bursts. Events older than100ms are discarded.

Consumer: sleep10ms using assert_wait_timeout/thread_block, not busy delay. At most one qualified16ms amplitude32 pulse per80ms. Actual native H04 transaction snapshots26 read registers, refuses busy/fault/foreign boost modes, disables autores for DirectPlay, writes low amplitude, starts, polls faults, stops, confirms HPWR_DISABLED/PLAY_ENclear, restores own configuration, rechecks faults. Any failure closes the event service until reboot. No HBST writes.

Lifecycle: persistent context retains at most two MMIO write mappings. Panic/return quiesce can use existing SPMI stop/module-disable with no mutex waiting once cores stopped; idle quiesce closes admission through leaving. No legacy Awinic init/firmware/reset involved.

Activation: mode2 only, dedicated loader capability, CPU1 and bounded <=90s return, hosttest uses60s. Separate flags cannot mix one-shot/read-only/torch/audio/GPU. General iOS service activation is NOT enabled by this experiment.

Evidence required: fresh READY, three direct onsets from client, three completed pulse/stop/restore sequences, no quarantine/fault; measure active_us. Public AudioServicesPlaySystemSound(Vibrate) request at35s precedes distinct direct_begin at40s. A request log or direct-device success does not prove HAL routing. Report actual Actuator output in HAL log before claiming system feedback.

Host tests: event queue handles silence/sustained signal/cooldown/coalescing/expiry/signed extrema. Actual cdev fixture checks copy chunk bounds, uiomove errors, odd writes, unready/shutdown and no hardware work on callback. Actual SPMI writer and bounded transaction failures/return quiesce tested separately. Full XNU/EFI/container validator pass. Hardware result pending in H05 at time of this document.
