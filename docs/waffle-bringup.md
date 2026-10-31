# OnePlus 12 PJD110: XNU bring-up

The waffle diagnostic build adds an SM8650 platform to `loader/` and
embeds that loader in a separate copy of the existing PJD110 UEFI port.
Early CPU/MMU/GIC checkpoints and bounded iOS 16.5 userland boots have
been verified on the PJD110. CPU 7 with Mesa softpipe reaches the
SpringBoard desktop. This is an experimental RAM port; peripheral
support remains incomplete.

The two stock base DTBs recorded in the existing waffle firmware manifest
agree on the following values:

| Parameter | Value |
| --- | --- |
| Qualcomm SoC ID | 557 |
| Revisions | `0x10000`, `0x20000` |
| CPU MPIDRs | `0x000`, `0x100`, …, `0x700` |
| PSCI | SMC |
| GIC distributor | `0x17100000`, size `0x10000` |
| GIC redistributors | `0x17180000`, size `0x200000`, stride `0x40000` |
| Architectural timer | 19.2 MHz; virtual timer PPI 11 / INTID 27 |
| UEFI display reservation | `[0xD5100000,0xD7C00000)` |

The loader validates EL1 and a 1440 × 3168 GOP framebuffer inside that
reservation. Staging, panic logs and the XNU window are allocated from
EFI conventional memory intersected with the live Android RAM banks, with
all stock/live reserved ranges removed. EFI conventional memory alone is
insufficient: the first hardware test faulted while copying into the
TrustZone reservation at `0x82700000`. It does not use macan's RAM map,
qemu-virt MMIO, redwood watchdog calls, or disk log writes.

Checkpoints 1–5, 10–23, 50–64 and the loader return self-test (999) are
accepted. Builds made with `--userland` also accept checkpoint 0 and RAM
root images, with a mandatory 1–300 second return timer (60 by default). Other hardware
driver boot arguments remain refused. The build pins the kernel's size and CRC32 to catch a
mismatched payload; this is not an authentication mechanism.
XNU runs on a separate CPU selected with `bootcpu=N` so the EFI CPU can
retain the USB transport. The bundled payload uses CPU 1 (MPIDR `0x100`);
the loader refuses it if that is already the EFI CPU.

## Rebuild

First prepare the toolchain, SDKs, patched XNU and ath12k as described in
the main README. Use a separate copy of the already prepared Mu-Silicium
tree containing the PJD110 platform, stock drivers and existing fixes:

```bash
python3 tools/build-waffle-diagnostic.py \
  --mu work/waffle/mu \
  --dtb /home/qarzis/OnePlus12-port/vendor_boot.img-2.dtb \
  --dtb /home/qarzis/OnePlus12-port/vendor_boot.img-3.dtb \
  --live-dtb work/waffle/hardware-test/android-live.dtb
```

Artifacts are placed in `work/waffle/diagnostic/`: a diagnostic Android
boot container, `xnu-diagnostic.xnup`, the kernel, hashes, build logs,
firmware provenance and the relevant source snapshot. The kernel target
is `build`, which links the monolithic image; it excludes the separate
DriverKit symbolset checks that the repository's iig shim does not satisfy.

## Hardware check

These commands are for a hardware test after building. The build script
does not run them or communicate with a phone.

```bash
fastboot boot work/waffle/diagnostic/HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img
# Choose Boot iOS in the UEFI menu.
fastboot -s xnuloader getvar platform
fastboot -s xnuloader getvar kernel-supported
fastboot -s xnuloader stage work/waffle/diagnostic/xnu-diagnostic.xnup
fastboot -s xnuloader oem selftest
fastboot -s xnuloader getvar result
fastboot -s xnuloader oem log
fastboot -s xnuloader get_staged work/waffle/selftest.log
```

After a successful return-path self-test, try `oem run 1` and collect
`getvar result` and `oem log`/`get_staged` again. Advance checkpoints only
after confirming that the preceding one returned. A successful build on
the PC does not establish that PSCI handoff, interrupts or the return path
work on the phone. If `getvar result` reports a hung kernel, restart the
phone before another run. `oem menu` returns to the menu when no kernel
owns the allocated RAM.

Further work depends on these logs: establish CPU/MMU/GIC entry first,
then add the SM8650 device drivers and a controlled userland boot path.
The Ace 6T hardware options remain unavailable in the diagnostic build.

## Touchscreen development

The live Android FDT and input device identify the BOE Synaptics S3910
on SPI at `0xA90000`. GPIOs 48–51 carry SPI; GPIO 162 is active-low IRQ,
161 is active-low reset, and 108 enables AVDD. TLMM per-pin registers
start at `0x0F100000`. VDD is the 1.8 V `pm-humu-l4` regulator.

`waffle_synaptics.c` uses GPIO SPI and the TCMv1 continued-read protocol,
selects native coordinate processing with `DC_CONTROL_LBP_HBP=2`, and
feeds normalized contacts into `/dev/redwood-touch`. This sequence comes
from the [official OnePlus driver](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8650/blob/c951f93ec63fbee49d468ee2f9d93ac0e807da67/vendor/oplus/kernel/touchpanel/synaptics_hbp/syna_tcm2.c).
It changes volatile settings only and uses the stock VDD voltage.
Pins are restored before returning to EFI. The first hardware test booted
iOS but received an all-zero SPI header. The next variant explicitly votes
for the stock 1.8 V rail through apps RSC DRV2 (`0x17A20000`, TCS offset
`0xD00`). Android's command DB identifies `ldob4` at `0x41C00`; its live
regulator summary confirms 1800 mV/HPM for `spi0.0-vdd`. The volatile vote
is retained on EFI return, with Android taking ownership again on reboot.
The third test (`diagnostic-touch-power2`) completed all power commands,
received the application identify and report-config readback, and delivered
real finger down/move events to the iOS HID service. The user confirmed
working taps and swipes. The application advertises native bounds
14399 × 31679, which the driver discovers and normalizes at runtime.
The 60-second test returned normally. Logs are in
`work/waffle/runs/20261023T131613Z/`; Android captures are in
`work/waffle/touch/`. A separate Downloads package contains the touch build;
the previous package is preserved.

The contact parser is checked with ASan/UBSan for multiple contacts,
coordinate scaling, palm releases and malformed frames. Build a separate
test image with `--userland --output work/waffle/diagnostic-touch`, then
use `scripts/run_waffle_ios.py --kernel work/waffle/diagnostic-touch/kernel`
after booting that matching image and selecting Boot iOS. Logs and raw
screenshots are saved under `work/waffle/runs/<UTC timestamp>/`.

## Power and volume buttons

`macan_buttons.c` also handles waffle's SPMI v7 bus 0 / EE0. The live
FDT gives core `0x0C400000`, ownership configuration `0x0C42D000` and
observer `0x0C440000`; the APID table is at core + `0x2000`, with a
`0x20` observer stride. Hardware reports arbiter version `0x70010000`,
896 APIDs. APID 533 identifies the PMK8550 PON HLOS block and APID 559
identifies PM8550 GPIO6.

| Button | Input | iOS consumer usage |
| --- | --- | --- |
| Power | SID0, PON `0x1310`, bit7 | `0x30` |
| Volume up | SID0, PON `0x1310`, bit6 | `0xE9` |
| Volume down | SID1, GPIO6 `0x8D10`, active-low bit0 | `0xEA` |

The GPIO DT label says `vol_up`, but its Linux code 114 is volume down;
PON RESIN code 115 is volume up. The driver validates peripheral types
and GPIO input/pull-up/enable settings, reads status every 16 ms, and
requires two matching samples before reporting a transition. It changes
no PMIC configuration and stops polling before EFI return.

The first hardware test with `diagnostic-buttons` delivered down/up
events for all three buttons to the iOS HID service (`delivered=1`).
The user confirmed volume controls and power lock/wake work. The bounded
test returned normally. Logs: `work/waffle/runs/20261023T133500Z/`.
The test uses the separately rebuilt root at
`work/waffle/buttons/images/root.packfs` for HID delivery diagnostics;
the system image is unchanged.

The subsequent serial customization sets waffle's device-tree
`serial-number` to `WFFL00OPLUS12`. The final Downloads package
`OnePlus12-iOS16.5-RAM-buttons` combines the exact kernel from the
successful button test, the tested root image, and a rebuilt matching EFI
with this property. Container/EFI/kernel pins and package hashes were
validated. The final package then booted successfully in run
`20261023T134539Z`. The user confirmed the new serial, and the About-screen
screenshot shows `WFFL00OPLUS12`. The 60-second test returned normally;
the package includes `iOS-serial.png` and its runtime verification record.
