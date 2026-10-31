# HakiOS UEFI adaptation for OnePlus 12 PJD110

This overlay adapts [oosexgang/hakios-uefi](https://github.com/oosexgang/hakios-uefi) at `687fa6c6a5a70f43184de92980e0a76eea5f2c4b` onto our existing, hardware-tested waffle Mu-Silicium tree (base `42fe563791e51bf5500c2e470ed294ca0c94b97c` plus local PJD110 platform/transport fixes).

It is **not** a pristine build of upstream HakiOS's declared Mu base `e51cd877e31c8fbb322032dc4cb6715e83d25ad3`. The working waffle platform, dependency revisions, memory map and vendor drivers are retained. HakiOS's boot manager changes, firmware identification, boot shim source and branding are adapted on top.

Upstream's stage-0 redwood loader writes a raw logdump partition and assumes fixed payload placement. This adapter instead starts the existing waffle RAM/USB loader from its FV GUID. It automatically enters the RAM/USB loader. The existing Volume Up callback can select the menu; returning through `oem menu` falls through to that menu. The escape paths remain in code but were not physically exercised in this validation. No `PAYLOAD_BASE` is supplied when building the waffle boot shim, so the optional fixed-address copy is not compiled in. The adapted XnuLoader has no partition-write code. It does not add GPU support or resolve CP_INIT.

## Build

The input must be the already prepared waffle Mu tree, with the current matching `loader-waffle.efi`, PJD110 drivers, board configuration and recorded DTBs. This overlay does not supply proprietary vendor binaries or iOS assets. Keep them local.

```bash
python3 uefi/waffle-hakios/build.py \
  --mu-source work/waffle/mu \
  --output work/waffle/mu-hakios-new
```

The script creates a separate tree, checks and applies `integration.patch`, generates HakiOS branding and runs `build_uefi.py -d waffle -r DEBUG`. It never contacts a phone. Existing output directories are refused. `banner.py` is the upstream HakiOS generator, preserved as source.

Output: `Mu-waffle.img` is the Android-format RAM boot container, and `Build/wafflePkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` is the raw firmware volume. The `.fd` file is not the Android fastboot boot container.

## Local result, October 31, 2026

Build succeeded. Separate container validation confirmed Android boot v4, the exact existing 55,808-byte loader, both recorded stock DTBs, and the matching XNU payload. PJD110 memory map, configuration, DTB and loader match the previous tree byte for byte. The automatic-entry variant was hardware tested: it enumerated as `xnuloader` without selecting Boot iOS, returned to Android, and completed the actual automatic-cycle runner with `sys.boot_completed=1`. This verifies the boot transport, not GPU execution.

The packaged local result and manifest are in `work/waffle/hakios-uefi-auto/`. The included XNU kernel is the prior E03 diagnostic build; no new GPU experiment is enabled by this UEFI adaptation. Original waffle UEFI and Android have not been replaced.

## Automatic host cycle

`tools/run-waffle-auto.py --artifact work/waffle/hakios-uefi-auto` verifies the image hash, reboots Android into fastboot, RAM-boots the image, waits for the waffle USB loader and returns to Android. `--prepare-gpu` adds the existing prepare-only probe93; `--access-matrix` or `--measure-clocks` selects a diagnostic variant. These paths do not send CP RAW. Failures preserve reports; Android recovery must be confirmed before another experiment. This cannot physically press buttons if recovery loses USB.
