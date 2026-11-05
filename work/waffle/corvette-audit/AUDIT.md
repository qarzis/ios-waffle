# Corvette applicability, 2026-11-05

Pinned3848a29620f0cf7d541bed64319a4e66f1658914, source hashes/blob IDs in provenance.json. Source-only reads, no foreign boot/firmware executed.

- Corvette is OnePlus Ace3Pro SM8650/Adreno750 gen70900, Synaptics S3910; closer GPU reference than redwood. Per-device display/PMIC/memory/firmware parameters still require native Waffle qualification.
- docs/corvette-gpu.md reports Native Metal desktop/widgets, per-client low4GiB VA reservations, fence-based BO release, context queue publish before doorbell, F2H retirement drain, IFPC exclusion and guarded A7xx PM4 packets. These are concrete source audit targets; not evidence these implementations already work on Waffle.
- The documented Native Metal path needs external NativeAdrenoMetal (original SHA47eb3a...522ce; patched2a01d8...e5) and Vulkan library SHA8d7b56...8725. Repo explicitly does not distribute them and has not established reproducible source build/licensing provenance for those external inputs. No such files found by filename under /home/qarzis. Source adapter alone cannot reproduce that tested setup. Existing hakios-metal-waffle is a distinct backend; do not assume binary ABI compatibility.
- Audio and haptics in this snapshot still describe redwood APR/ASM/ADM stream1801 and AW86927, respectively. They do not implement native PM8550B or Waffle GPR/APM sound. Our H05 has actual Waffle PCM-controlled physical taps; remaining iOS HAL routing is separate.
- Do not merge donor address map/UEFI or external binaries wholesale. First compare ownership/queue/ABI contracts on host and keep Waffle defaults unchanged. No 60FPS claim follows from donor desktop milestone; donor itself reports unresolved warm-run900E and limited stability coverage.

## Additional concrete comparisons
- Native GPU ABI cache flag in donor hakios.gpu.cpp is0x10000; Waffle private BO cache flag differs. Do not copy ioctl/flag contracts across the Native bridge and Waffle DRM shim without translation.
- Donor native client VA capacity256MiB, compositor512MiB is reservation, not physical GPU RAM. It fixes their specific lifetime/alias issue and does not by itself raise Waffle FPS.
- Donor Synaptics syna_move_due caps MOVEs at8ms/125Hz after observed compositor flicker at2ms polling. Waffle macan_synaptics.c currently emits MOVE for every active contact on every report, even unchanged coordinates. Test suppressing unchanged MOVE / optional measured coalescing separately; DOWN/UP must remain immediate and final coordinates preserved. Native raw ranges and IRQ162 differ from Waffle IRQ55; do not port wholeboard.
- Donor v7 SPMI core0c400000/cnfg0c42d000/observer0c440000 matches the Waffle implementation already qualified for buttons/torch/haptic. Useful independent source comparison, not a new fix.
- Donor haptic rc.jobs explicitly waits for ringer state and sound_test uses AudioServices completion plus CFRunLoop. H06 tests completion/runloop without altering the motor driver; no assumption that request-only H05 established routing.
