# HakiOS 2.3.4 applicability — 2026-11-05

Pinned source and exact hashes are in provenance.json. Remote was fetched into the existing donor repository without checking out or changing its working files. No release code merged into Waffle.

- Haptic remains AW86927 on I2C, including Awinic firmware and reset GPIO. Waffle H01 proves PM8550B HAP525_HV through SPMI. Reuse the iOS actuator/samples interface later, not the donor register sequence or firmware.
- Audio remains APR AFE/ASM/ADM and stream 0x1801. Waffle has qualified GPR/APM graph open/close and native streams 0x1001/0x1061. Donor packets and stream selection are not ABI compatible. Its SMMU allocation/restore structure is useful reference; it is not ownership proof for a Waffle context bank.
- Metal wallpaper/status-bar/widget correction is in pipeline-variant selection. It applies to the Metal renderer after that renderer is ported; Waffle currently uses Mesa/EAGL. No equivalent immediate EAGL patch inferred from the release note.
- Donor porting guide explicitly restricts native Metal tables to chip ID 0x06030500 and scanline MMIO to sc7280 unless supplied per-device. Never select those tables or scan addresses for SM8650 just to pass the guard.
- Reported 109.6 FPS is donor-specific, not a OnePlus 12 measurement. Waffle target remains stable 60 FPS.

Next haptic experiment H02 reads fault, HPWR interface, brake, closed-loop brake, auto-resonance and calibration config in addition to H01 identity. Native enable_play clears faults and configures open-loop power before PLAY_EN. Native stop clears PLAY_EN then polls HPWR_DISABLED, with a module-toggle recovery on timeout. These dependencies are not implemented by writing only PLAY_EN. H02 does not start the motor or establish readiness/ownership for writes.

Audio next: establish native context-bank ownership/attach and bounded silent DMA mapping before PCM and amplifiers; do not repeat A16 global-disable hypothesis, which was refuted by CLIENTPD=0.
