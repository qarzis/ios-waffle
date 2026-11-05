# PM8550B H02: qualify stop prerequisites before pulse

Source: upstream/qcom-hv-haptics.c, revision e39bf7032e38c547d588372a11a5dd55eb714860; H01 observed CFG/PTN revision4, boost revision0002. No motor writes in H02.

Native call chain:
1. load_constant_effect: lock/exclude calibration, establish VMAX/headroom/power mode, set brake configuration, set PTN DIRECT_PLAY amplitude, set auto-resonance (disabled in the OnePlus build branch), select DIRECT_PLAY.
2. enable_play(true): clear three fault sources; configure open-loop power/RC calibration with charger ownership considerations; write source/brake/PLAY_EN; boost workaround conditional on exact revision.
3. erase/stop: cancel producer/work, clear PLAY_EN, wait for braking plus a resonant cycle using HPWR_INTF. A timeout invokes module toggle in native driver. Then release owned power.

H02 adds reads of CFG0b/0c/50/51/63/72; no read-to-clear/W1C writes, no boost writes, no reset or enable changes. Existing H01 revision/mode/allowlist gates remain. Host helper rejects failure at each of22 read positions; actual torch/SPMI observer tests platform/mode gating and no write interface. Full build passed. Hardware result pending.

First pulse cannot be called ready based on these raw registers alone. Needs bounded exclusive actuator operation; native fault handling and power conditions; a proven stop/readback path and cleanup on every failure; restore only owned configuration. HBST owner3 remains outside this driver's write scope. Do not use donor Awinic GPIO/reset as recovery.
