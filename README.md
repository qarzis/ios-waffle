<p align="center">
  <img src="uefi/branding/assets/logo.png" width="120" alt="ios-waffle">
</p>

<h1 align="center">ios-waffle</h1>

<p align="center"><strong>An experimental iOS 16.5 port for the OnePlus 12.</strong><br>
PJD110 · Snapdragon 8 Gen 3 / SM8650 · Adreno 750 · waffle<br>
XNU and iOS boot through UEFI into RAM.</p>

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
| **Adreno 750 GPU** | ⚠️ | CP initialization, authenticated ZAP, indirect command buffers and actual GPU memory writes pass under XNU; the iOS rendering backend is unfinished |
| **GPU CP_INIT / ZAP** | ✅ | Native CP_INIT acknowledgement, PAS13 signature authentication and secure-mode transition with TRUST=0 |
| **GPU command execution / memory** | ✅ | GPU fetches PM4 from an indirect buffer and writes a marker; CPU checks all 4,096 words, including commands and guards |
| **GPU resource ownership** | ⚠️ | Three sequential IB submissions and heap-owned GMU/TCM/SMMU state pass; persistent board-clock/AOP ownership and the userspace backend remain unfinished |
| **GPU-rendered iOS interface** | ❌ | No connected waffle Mesa/IOUserClient backend; the desktop still uses softpipe |
| **Automatic UEFI loader entry** | ✅ | Adapted HakiOS UEFI enters the RAM/USB loader without a physical Boot iOS selection; automatic test/recovery cycles verified |
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
- **GPU preparation.** Fixed compact GPU mapping overlap and the TG1 encoding required by 4 KB TTBR1 tables.
- **CP execution.** Added the missing LPAC mapping/aperture, native GMU bank placement and invalidation of both ASIDs. The full native CP_INIT now acknowledges successfully; E08 reproduced the result across two Android resets. The individual contributions of this prerequisite set were not isolated.
- **GMU power and clocks.** Preparation test 93 passed the GMU 625 → 260 MHz sequence, an HFI query, shutdown, GX power collapse and PLL restoration.
- **Physical clocks.** E06-r2 measured approximately 231 MHz GFX3D and 260 MHz GMU under XNU and verified complete shutdown and restoration.
- **SMMU access modes.** The latest E15 control passed 27 access checks for microcode, restore and eight HFI allocations, plus 42 LPAC translations, without CP RAW.
- **Authenticated ZAP.** E09 passed PAS13 initialization, memory setup and signature authentication, then the native CP secure-mode switch with TRUST=0.
- **Actual GPU memory result.** E10 verified a four-word GPU write. E11-r2 then verified that the GPU fetched the same PM4 stream from memory and executed it. All 4,096 words were checked, including unchanged command words and guards. The initial E11 exposed an exact unprivileged IB permission fault; AP_UNPRIV was fixed only for that command buffer.
- **Resource lifetime.** E12–E15 verified three sequential IB submissions with distinct results, GMU/TCM ownership across initialization return, SMMU-owned tables and callbacks, and child-first shutdown before context detachment and memory release.
- **Automatic RAM boot and full logs.** Adapted HakiOS UEFI starts the existing waffle USB loader automatically. Completed kernel logs retain the full record instead of truncating to the 32 KB console buffer.

Details and test references: [bring-up](docs/waffle-bringup.md), [GPU status](docs/waffle-gpu.md), [debug log](GPU_DEBUG_LOG.md), [forensic audit](work/waffle/gpu/forensic-audit/AUDIT.md).

## Current GPU work

The earlier CP_INIT failure has been passed. The verified chain is now GMU/HFI boot → native CP_INIT ACK → signed ZAP authentication → secure-mode transition → indirect PM4 fetch → actual GPU memory write → CPU readback → full shutdown and Android recovery.

The latest **E15** session passed three sequential IB submissions with different result markers. Each checked all 4,096 words of its buffer. GMU/TCM and SMMU state now have explicit ownership across constructor returns; the SMMU parent retains tables, saved contexts and callback storage until its GMU child has stopped. The default control also passed the access matrix and LPAC translations. The recorded E15 runs completed without 900e and returned to a fully booted Android.

**This remains a bounded kernel diagnostic, not a persistent iOS GPU driver.** The next work is board-clock, CX and AOP lifetime, dynamic buffer mappings, a userspace submission/fence backend, and connection to the existing RedwoodGPU, Mesa and IOSurface stack. Shader execution, a verified offscreen frame and hardware composition of the iOS interface have not been tested. Metal is a separate task. Reopening a GPU session after shutdown in the same boot is also unverified; current tests reset through Android between cold sessions.

See the [milestone and evidence table](docs/waffle-gpu-milestones.md) for successful and failed experiments, exact results and limitations. Historical 900e failures and the E11 permission fault remain in the debug log; they are not current pass results.

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
