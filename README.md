<p align="center">
  <img src="uefi/branding/assets/logo.png" width="120" alt="ios-waffle">
</p>

<h1 align="center">ios-waffle</h1>

<p align="center"><strong>An experimental iOS 16.5 port for the OnePlus 12.</strong><br>
PJD110 · Snapdragon 8 Gen 3 / SM8650 · Adreno 750 · waffle<br>
XNU and iOS boot through UEFI into RAM.</p>

The port reaches the SpringBoard desktop. Display output, touch input and physical buttons have been tested on the OnePlus 12. The interface currently uses CPU rendering through Mesa softpipe. **GPU hardware acceleration is not working yet.**

This project is based on [ios-macan](https://github.com/hxfuxyy/ios-macan). Adreno 829 and peripheral support in the original OnePlus Ace 6T project does not establish support for those features on the OnePlus 12.

## What works

Status as of **October 31, 2026**, based on recorded tests on the PJD110.

✅ — verified on hardware · ⚠️ — partially implemented · ❌ — no working waffle implementation · ⚪ — unverified.

| Feature | Status | Verified OnePlus 12 behavior |
| :--- | :---: | :--- |
| **XNU boot** | ✅ | Kernel entry, MMU, GIC, timers and iOS userland boot |
| **SpringBoard / desktop** | ✅ | iOS 16.5 reaches the desktop with software rendering |
| **Display** | ✅ | UEFI framebuffer output; 1440 × 3168 GOP |
| **Touch** | ✅ | Synaptics S3910: real taps, movement and swipes in iOS |
| **Buttons** | ✅ | Power and volume up/down; screen lock and wake confirmed |
| **Software graphics** | ✅ | Mesa softpipe / EAGL shim; CPU-rendered interface |
| **iOS serial number** | ✅ | `WFFL00OPLUS12`, verified in Settings → About |
| **USB loader and logs** | ✅ | Kernel and RAM image transfers from the PC, log retrieval and return to the loader |
| **Return to Android** | ✅ | Checked after tests, including completed Android boot |
| **All 8 cores / SMP / frequency scaling** | ⚪ | Boot on a selected CPU is verified; full operation of all cores is not claimed |
| **Adreno 750 GPU** | ⚠️ | GMU/HFI/SMMU preparation tests work. Successful CP_INIT execution and GPU rendering under XNU remain unconfirmed |
| **Metal** | ❌ | No waffle backend |
| **Wi-Fi / Internet** | ❌ | The donor network driver is not connected to waffle initialization |
| **Sound** | ❌ | The donor ADSP/audio path is not connected for waffle |
| **Microphone** | ❌ | No working audio path |
| **Battery / charging from iOS** | ❌ | The donor battery driver is not connected; iOS charging control is not implemented |
| **Vibration / haptics** | ❌ | No working waffle integration |
| **Flashlight** | ❌ | No working waffle integration |
| **Cameras** | ❌ | Not implemented |
| **Sensors** | ❌ | Gyroscope, accelerometer, ambient light and proximity are not connected |
| **Brightness control** | ❌ | Display output is verified; brightness control from iOS is not implemented |
| **120 Hz** | ⚪ | Panel mode and iOS output refresh rate are unverified |
| **Bluetooth** | ❌ | Not implemented |
| **Cellular / SIM** | ❌ | Not implemented |
| **GPS / NFC** | ❌ | Not implemented |
| **USB inside iOS** | ❌ | Loader transport is verified; the iOS USB stack is not implemented |
| **Persistent UFS storage** | ❌ | iOS uses RAM images; changes within a RAM session do not survive reboot |
| **Full device sleep** | ❌ | Screen locking works; system suspend is not implemented |
| **Sileo / tweaks / Dynamic Island** | ⚪ | Components exist in the original project; full validation on the OnePlus 12 is not claimed |
| **Apple ID / App Store downloads** | ⚪ | Operation on this port is unverified |

## Fixes and verified milestones

- **OnePlus 12 memory map.** The loader uses the live RAM map and reserved regions. An early copy failure into a TrustZone carveout was fixed.
- **XNU entry and return.** Early CPU/MMU/GIC checkpoints, bounded userland sessions and return to EFI have been tested.
- **Touchscreen.** Synaptics power, GPIO SPI, the TCM protocol, coordinate normalization and event delivery to iOS are implemented. The user confirmed taps and swipes.
- **Physical buttons.** Power and both volume buttons are connected through SPMI; real events were confirmed in iOS.
- **CPU-rendered interface.** Waffle selects Mesa softpipe so the interface can run while GPU driver development continues.
- **GPU preparation.** Compact GPU mapping overlap and TG1 encoding for TTBR1 with 4 KB tables were fixed. These fixes did not resolve the current CP failure.
- **GMU power and clocks.** Preparation test 93 passed the GMU 625 → 260 MHz sequence, an HFI query, shutdown, GX power collapse and PLL restoration.
- **SMMU access modes.** E03 passed all 27 translation checks for microcode, the restore buffer and eight HFI allocations without launching CP RAW.

Details and test references: [bring-up](docs/waffle-bringup.md), [GPU status](docs/waffle-gpu.md), [debug log](GPU_DEBUG_LOG.md), [forensic audit](work/waffle/gpu/forensic-audit/AUDIT.md).

## Current GPU blocker

The stock Android driver runs the Adreno 750. Under XNU, GMU firmware boot, HFI communication, memory allocation and GPU preparation have been verified. Previous RAW CP_INIT experiments lost USB and entered Qualcomm 900e mode; no successful CP ACK under XNU has been recorded.

E03 verified the tested SMMU translation modes after GMU shutdown. It **does not prove actual GPU memory reads**, microcode execution or frame rendering. A successful build or matching register values also does not establish working hardware execution.

The cause of 900e remains unknown. The remaining investigation covers CP startup prerequisites and the RAW publication/firmware handling boundary. A cold stock Android HFI trace captured a successful first CP_INIT; TrustZone/reset logs available through Android are encrypted.

The user reported nonworking touch after the temporary E04 Android tracing image. A normal reboot restored touch. That image will not be reused until the cause is understood.

Next milestones: measurable command execution and GPU data transfer → fence/timestamp → one verified frame → a waffle backend connected to IOUserClient, Mesa and IOSurface → an accelerated iOS interface. Metal is a separate task.

## Device and requirements

The tested device is the **OnePlus 12 PJD110**: Snapdragon 8 Gen 3 / SM8650, Adreno 750 Gen7.9.1, and a BOE panel with Synaptics S3910. Other regional OnePlus 12 variants and panels have not been tested.

Development requires:

- an unlocked bootloader supporting `fastboot boot`;
- root and USB debugging in Android to collect device data and firmware;
- Linux, `adb`, `fastboot` and a prepared XNU toolchain;
- your own iOS 16.5 images, phone firmware, recorded stock/live DTBs, and a separate Mu tree with the PJD110 platform.

**There is no ready-to-use universal OnePlus 12 installer here yet.** The `hackios` / `hackios.bat` scripts and original build workflow are inherited from the donor. Their Ace 6T instructions and release kit are not a verified waffle boot guide. Complete local build artifacts, RAM images and firmware used in the experiments are not included in this publication.

## Source and building

```bash
git clone https://github.com/qarzis/ios-waffle.git
cd ios-waffle
```

Preparation and tested diagnostic build steps are documented in [docs/waffle-bringup.md](docs/waffle-bringup.md). Main tools:

| File | Purpose |
| :--- | :--- |
| `tools/build-waffle-diagnostic.py` | Host checks, XNU/EFI builds and diagnostic image packaging |
| `tools/validate-waffle-diagnostic.py` | Boot container, EFI, kernel and payload validation |
| `scripts/run_waffle_ios.py` | Kernel/RAM image transfers, bounded sessions and log collection |
| `tools/tests/waffle-ecats-access-host.py` | Checks actual ECATS code against native encoding and fault models |

RAM boot sequence:

```text
Android → fastboot boot → PJD110 UEFI → Boot iOS
        → USB loader → XNU + root/system images in RAM → SpringBoard
```

An ordinary iOS session and minimal GPU diagnostics use different RAM image sets. A successful diagnostic test does not mean its image can boot the desktop. Do not run historical RAW tests from the log as a step-by-step guide: the log preserves failed experiments.

## Repository layout

| Directory / file | Contents |
| :--- | :--- |
| `kernel/files/bsd/dev/waffle_*` | OnePlus 12 Synaptics, Adreno/GMU and SMMU port |
| `kernel/files/bsd/sys/waffle_*` | SM8650 profile and supporting interfaces |
| `kernel/kernel.patch` | Integration into XNU |
| `loader/` | USB loader, waffle boot policy and memory map |
| `userland/` | iOS userland integration and software renderer selection |
| `tools/`, `scripts/` | Building, validation and boot tools |
| `docs/waffle-bringup.md` | Display, touch, buttons and early bring-up |
| `docs/waffle-gpu.md` | GPU port status and hardware test history |
| `GPU_DEBUG_LOG.md` | Hypotheses, experiments, results and limitations |
| `work/waffle/gpu/forensic-audit/` | Published audit material and diagnostic evidence |
| `uefi/`, `wifi/`, `sileo/` | Inherited donor components; code presence does not establish working waffle support |

## Credits and licenses

The port is based on [hxfuxyy/ios-macan](https://github.com/hxfuxyy/ios-macan), OOSexGang's work, and vcvkk's earlier POCO X5 Pro port. Stock Qualcomm/OnePlus sources are used to compare hardware configuration and protocols.

Original component licenses are preserved: XNU uses APSL 2.0; Linux components, Mesa, Mu / Project Silicium, zstd and userland packages retain their respective licenses. Noto Sans notices are in `uefi/branding/assets/`.

Not affiliated with Apple or OnePlus. iOS belongs to Apple and is not distributed in this repository.
