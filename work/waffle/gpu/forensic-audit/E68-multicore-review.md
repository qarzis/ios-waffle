# OnePlus 12 multicore and volume HUD audit — 2026-11-02

The loader default appended `cpus=1`. Waffle policy refused explicit `cpus`; XNU already contains PSCI SMP startup and stop support. Added bounded opt-in 1–7 CPU policy and runner argument, retaining the default until qualified. The resident USB loader owns physical CPU0 and excludes it from the XNU device tree. Eight XNU cores need a separate handoff design; accepting `cpus=8` cannot provide eight cores in this mode.

Four-core hardware run `20261102T071804Z` passed: all four sysctl CPU counts equal 4; four workers consumed 572 ms CPU during 269 ms wall time (2.1 effective processors, not a fourfold speedup claim). Kernel reports four running, clean return and Android boot independently confirmed. Original two-core run returned normally but the host runner failed because it compared the absent GPU probe number against 65; original failure retained, both unguarded comparisons fixed.

The delayed CPU probe now samples active CPUs after its 35-second sleep, checks pthread failures, and records actual process CPU versus wall time. A separate root builder enables this probe with normal softpipe UI and no GPU initialization. Seven-core 240-second test is currently running; no seven-core success claim yet.

Volume HUD: user reports the slider is too high. The four-core native screenshot `screen-11.raw` actually captured the HUD in Settings. Decode as 1440×3168 BGRA; top is approximately 58 logical points on the 375×812 canvas. Device identity contains donor volume-up/down button location properties. Their raw five-word representation has not yet been traced through the iOS consumer. No global DPI or opaque coordinate mutation has been made. Need correlate geometry with device traits before selecting the minimal fix.

On-demand screenshots use a file request mailbox handled by the existing runner; no concurrent fastboot process is allowed.
