<p align="center">
  <img src="uefi/branding/assets/logo.png" width="120" alt="ios-waffle">
</p>

<h1 align="center">ios-waffle</h1>

<p align="center"><strong>An experimental iOS 16.5 port for the OnePlus 12.</strong><br>
PJD110 · Snapdragon 8 Gen 3 / SM8650 · Adreno 750 · waffle<br>
XNU and iOS boot through UEFI into RAM.</p>

## What works

| | Status | Notes |
| --- | :---: | --- |
| CPU, interrupts, timers | ✅ | 7 cores tested; one core reserved for the USB loader |
| Display | ✅ | 1440 × 3168 panel; iOS renders at 750 × 1624 |
| GPU | ✅ | Hardware rendering through Mesa; stutter remains, long-term stability unverified |
| Metal | ❌ | |
| Touch | ✅ | Taps and swipes |
| Buttons | ✅ | Power, volume up, volume down |
| Alert Slider | ✅ | Do Not Disturb / vibrate mode / ring; native iOS banners |
| Wi-Fi | ❌ | |
| Vibration | ⚠️ | CoreHaptics and system vibration tested; normal boot integration pending |
| Flashlight | ✅ | On/off from Control Center |
| Battery | ❌ | Native readings reach iOS power source; live UI percentage pending |
| Packages | ⚪ | Sileo and tweaks unverified |
| Dynamic Island | ⚪ | Unverified |
| 120 Hz | ⚪ | Unverified |
| Sound | ❌ | DSP and APM graph verified; playback pending |
| Microphone | ❌ | |
| Camera | ❌ | |
| Sensors | ❌ | |
| Brightness | ❌ | No iOS brightness control |
| Bluetooth | ❌ | |
| Cellular, SIM | ❌ | |
| GPS, NFC | ❌ | |
| USB | ⚠️ | Boot loader and logs only |
| Storage (UFS) | ❌ | iOS runs from RAM |
| Sleep | ❌ | Screen lock works; system suspend does not |
| Hardware AES | ⚪ | Unverified |
| Apple ID, App Store downloads | ⚪ | Unverified |

⚪ — unverified. [GPU progress and test results](docs/waffle-gpu-milestones.md).

## Device and requirements

The tested device is the **OnePlus 12 PJD110**: Snapdragon 8 Gen 3 / SM8650, Adreno 750 Gen7.9.1, and a BOE panel with Synaptics S3910. Other regional OnePlus 12 variants and panels have not been tested.

Development requires:

- an unlocked bootloader supporting `fastboot boot`;
- root and USB debugging in Android to collect device data and firmware;
- Linux, `adb`, `fastboot` and a prepared XNU toolchain;
- your own iOS 16.5 images, phone firmware, recorded stock/live DTBs, and a separate Mu tree with the PJD110 platform.

**There is no ready-to-use universal OnePlus 12 installer here yet.** The `hackios` / `hackios.bat` scripts and original build workflow are inherited from the donor. Their Ace 6T instructions and release kit are not a verified waffle boot guide. Complete local build artifacts, RAM images and firmware used in the experiments are not included in this publication. Host tests that compare vendor behavior require the pinned OnePlus reference sources under `work/waffle/gpu/vendor/`; firmware parsing tests also require your local captured firmware.

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
| `tools/run-waffle-auto.py` | Verified automatic RAM boot, bounded diagnostics and Android recovery |
| `uefi/waffle-hakios/` | Source overlay for the adapted automatic HakiOS loader |
| `tools/tests/waffle-ecats-access-host.py` | Checks actual ECATS code against native encoding and fault models |

RAM boot sequence:

```text
Android → fastboot boot → PJD110 UEFI → USB loader
        (automatic entry on the adapted HakiOS build; Boot iOS on older builds)
        → XNU + root/system images in RAM → SpringBoard
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
