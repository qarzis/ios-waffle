#!/usr/bin/env python3
"""Build an XNU diagnostic/RAM-userland loader in a separate waffle Mu checkout.

This does not boot or flash a phone. Peripheral support is experimental.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837"


def run(command, **kwargs):
    print("Running:", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mu", type=Path, required=True, help="Separate Mu tree with the existing PJD110 platform")
    parser.add_argument("--dtb", type=Path, action="append", required=True, help="Both recorded stock DTBs; repeat twice")
    parser.add_argument("--live-dtb", type=Path, required=True, help="Live FDT captured from this PJD110 Android")
    parser.add_argument("--output", type=Path, default=ROOT / "work/waffle/diagnostic")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--userland", action="store_true", help="Enable bounded RAM userland tests")
    parser.add_argument("--ui-soak-loader",action="store_true",help="Allow exact660-second return for the qualified mode13 chain")
    args = parser.parse_args()
    if args.ui_soak_loader and not args.userland:parser.error("--ui-soak-loader requires --userland")
    mu, output = args.mu.resolve(), args.output.resolve()
    loader_dir = mu / "Platforms/OnePlus/wafflePkg/Applications/XnuRamLoader"
    if not (loader_dir / "XnuRamLoader.inf").is_file():
        parser.error("The supplied Mu tree has no waffle XnuRamLoader application")
    if not (1 <= args.jobs <= 32):
        parser.error("--jobs must be in 1..32")
    if mu == ROOT.parent / "Mu-Silicium":
        parser.error("Use a separate Mu copy to preserve the existing transport image")
    output.mkdir(parents=True, exist_ok=True)
    run([sys.executable, ROOT / "tools/check-waffle-dtb.py", *args.dtb,
         "--output", output / "hardware-provenance.json", "--live-dtb", args.live_dtb.resolve(),
         "--memory-header", ROOT / "loader/waffle-memory-map.h",
         "--memory-output", output / "memory-provenance.json"], cwd=ROOT)
    shutil.copyfile(args.live_dtb, output / "android-live.dtb")
    run([sys.executable, ROOT / "tools/check-waffle-gpu.py", *args.dtb, args.live_dtb,
         "--output", output / "gpu-provenance.json"], cwd=ROOT)
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-vsync-phase-host.c", "-o", output / "test-vsync-phase"])
    run([output / "test-vsync-phase"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-survey-host.c", "-o", output / "test-display-survey"])
    run([output / "test-display-survey"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-smmu-host.c", "-o", output / "test-display-smmu"])
    run([output / "test-display-smmu"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-flush-host.c", "-o", output / "test-display-flush"])
    run([output / "test-display-flush"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-flip-host.c", "-o", output / "test-display-flip"])
    run([output / "test-display-flip"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-present-host.c", "-o", output / "test-display-present"])
    run([output / "test-display-present"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-display-source-host.c", "-o", output / "test-display-source"])
    run([output / "test-display-source"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-policy.c", "-o", output / "test-policy"], cwd=ROOT)
    run([output / "test-policy"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-adsp-rpmh-host.c", "-o", output / "test-adsp-rpmh"], cwd=ROOT)
    run([output / "test-adsp-rpmh"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", ROOT / "kernel/files/bsd/sys", ROOT / "tools/tests/waffle-audio-smmu-survey-host.c",
         "-o", output / "test-audio-smmu-survey"])
    run([output / "test-audio-smmu-survey"])
    run([sys.executable, ROOT / "tools/tests/waffle-adsp-scm-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpr-reply-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-glink-intent-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-framebuffer-clipping-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-display-usecount-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-display-retire-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-log-batch-host.py"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", ROOT / "kernel/files/bsd", ROOT / "tools/tests/waffle-battery-readonly-host.c",
         "-o", output / "test-battery-readonly"])
    run([output / "test-battery-readonly"])
    run([sys.executable, ROOT / "tools/tests/waffle-battery-mailbox-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-battery-cli-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-battery-report-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-iosurface-seed-host.py"])
    for variant,flags in (("user",["-DWAFFLE_USERLAND=1"]),("soak",["-DWAFFLE_USERLAND=1","-DWAFFLE_UI_SOAK_TEST=1"])):
        run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",*flags,
             ROOT / "tools/tests/waffle-policy.c","-o",output / f"test-policy-{variant}"])
        run([output / f"test-policy-{variant}"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-touch.c", "-o", output / "test-touch"], cwd=ROOT)
    run([output / "test-touch"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         ROOT / "tools/tests/waffle-compact-va.c", "-o", output / "test-compact-va"])
    run([output / "test-compact-va"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-192mb-backing-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-10mb-object-host.py"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", ROOT / "tools/tests/waffle-slider-host.c", "-o", output / "test-slider"])
    run([output / "test-slider"])
    run([sys.executable, ROOT / "tools/tests/waffle-slider-power-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-slider-config-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gmu-clock-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gmu-native-clock-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-firmware-power-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-pll1-native-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-aop-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-aop-session-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-aop-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-aop-owner-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-llcc-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ramlog-export-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ramlog-raw-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ramlog-run.py"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-gmu-fw.c", "-o", output / "test-gmu-fw"])
    firmware = ROOT / "work/waffle/gpu/android-capture2/gmu_gen70900.bin"
    run([output / "test-gmu-fw", *([firmware] if firmware.is_file() else [])])
    if args.userland:
        run(["cc", "-DWAFFLE_USERLAND=1", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-fsanitize=address,undefined", "-g", ROOT / "tools/tests/waffle-policy.c",
             "-o", output / "test-userland-policy"], cwd=ROOT)
        run([output / "test-userland-policy"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-hfi.c", "-o", output / "test-hfi"])
    run([output / "test-hfi"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-tables.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-powerseq-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gx-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-context-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ucode-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ucode-access-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-cp-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hwsched-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-raw-fault-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-smmu-stall-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ecats-access-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-measure-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-log-retrieval-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-smmu-fault-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-publication-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-post-prepare-query-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-features-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-pool-permissions-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-dcvs-votes-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-acd-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-scm-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-scm-aperture-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-zap-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-zap-load-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-writeback-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-submit-session-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-general-submit-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-root-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-window-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-request-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-general-drm-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-describe-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-transport-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-backing-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-registry-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-smmu-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-map-audit-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-write-cdev-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-read-cdev-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-import-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-sample-submit-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-import-shim-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-resource-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-surface-binding-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-submit-lifetime-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gl-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-queue-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-readback-benchmark-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-submit-profile-log-host.py"])
    run([sys.executable, ROOT / "tools/build-waffle-gl-probe.py", "--output", output / "gl-probe"])
    run([sys.executable, ROOT / "tools/tests/waffle-compute-payload-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-image-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-copy-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-present-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-copy-jobs-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-service-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-user-host.py"])
    run([sys.executable, ROOT / "tools/build-waffle-user-probe.py", "--output", output / "user-probe"])
    run([sys.executable, ROOT / "tools/build-waffle-user-probe.py", "--msm", "--output", output / "msm-probe"])
    run([sys.executable, ROOT / "tools/tests/waffle-msm-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-mesa-transport-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-memory-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-registry-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-registry-smmu-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-registry-storage-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-reclaim-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-reclaim-smmu-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-reclaim-cdev-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-reclaim-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-generation-handles-candidate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-registry-reuse-candidate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-generation-log-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gl-recycle-probe-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-queue-issued-limit-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-queue-generations-candidate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gl-queue-probe-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-issued-record-limit-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-live-heap-candidate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-va-fragmentation-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-runner-options-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-table-budget-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-fullsize-budget-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-bo-budget-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-context-pool-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-ui-heap-candidate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-map-helper-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-mapped-bo-host.py"])
    run([sys.executable, ROOT / "tools/build-waffle-user-probe.py", "--msm", "--mesa-transport", "--mapped", "--output", output / "mapped-probe"])
    run([sys.executable, ROOT / "tools/tests/waffle-image-gate-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-dynamic-bo-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-data-bo-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-user-va-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-glsl-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gmu-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-tcm-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-smmu-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-board-power-owner-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-secure-context-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-protected-pool-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-start-tables-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gen7-config-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hwcg-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-cp-init-host.py"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-gen7-transaction.c", "-o", output / "test-gen7-transaction"])
    run([output / "test-gen7-transaction"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-gen7-cp-lifecycle.c", "-o", output / "test-gen7-cp-lifecycle"])
    run([output / "test-gen7-cp-lifecycle"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-gen7-boot.c", "-o", output / "test-gen7-boot"])
    run([output / "test-gen7-boot"])
    xnu = ROOT / "xnu-src/xnu-8796.121.2"
    if "bsd/dev/waffle_synaptics.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks the waffle touch build entry; apply the current kernel/kernel.patch")
    if "bsd/dev/waffle_adreno.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks the waffle GPU build entry; apply the current kernel/kernel.patch")
    if "bsd/dev/waffle_smmu.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks the waffle SMMU build entry; apply the current kernel/kernel.patch")
    if "bsd/dev/waffle_gmu.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks the waffle GMU build entry; apply the current kernel/kernel.patch")
    if "bsd/dev/waffle_gpu_service.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks waffle GPU service build entry; apply current kernel/kernel.patch")
    if "bsd/dev/waffle_gpu_user.c" not in (xnu / "bsd/conf/files").read_text():
        raise ValueError("Prepared XNU lacks waffle GPU user build entry")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_vsync_phase.h", xnu / "bsd/sys/waffle_vsync_phase.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_survey.h", xnu / "bsd/sys/waffle_display_survey.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_smmu.h", xnu / "bsd/sys/waffle_display_smmu.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_flush.h", xnu / "bsd/sys/waffle_display_flush.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_flip.h", xnu / "bsd/sys/waffle_display_flip.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_present.h", xnu / "bsd/sys/waffle_display_present.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_display_source.h", xnu / "bsd/sys/waffle_display_source.h")
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_battery_readonly.h", xnu / "bsd/sys/waffle_battery_readonly.h")
    for relative in ("bsd/dev/macan_battery.c", "iokit/Kernel/MacanBattery.cpp", "bsd/sys/macan_input.h"):
        shutil.copyfile(ROOT / "kernel/files" / relative, xnu / relative)
    # These board overlays may change after XNU was first prepared. Compile
    # the source included in the artifact snapshot, rather than stale copies.
    shutil.copyfile(ROOT / "kernel/files/bsd/sys/waffle_audio_smmu_survey.h",
                    xnu / "bsd/sys/waffle_audio_smmu_survey.h")
    for relative in ("iokit/Kernel/MiniIOSurface.cpp", "iokit/Kernel/MiniIOSurface.h"):
        shutil.copyfile(ROOT / "kernel/files" / relative, xnu / relative)
    for relative in ("iokit/Kernel/MiniIOMobileFramebuffer.cpp", "bsd/dev/macan_torch.c", "bsd/dev/macan_audio.c", "bsd/dev/macan_buttons.c", "bsd/sys/waffle_slider.h", "iokit/Kernel/WaffleGPUMemory.cpp", "bsd/sys/waffle_gpu_submit.h", "bsd/sys/waffle_gpu_memory.h", "bsd/sys/waffle_gpu_surface.h", "bsd/sys/waffle_gpu_surface_write.h", "bsd/sys/waffle_gpu_surface_read.h", "bsd/sys/waffle_gpu_registry.h", "bsd/sys/waffle_gpu_handles.h", "bsd/sys/waffle_gpu_reclaim.h", "iokit/Kernel/WaffleGPUMap.cpp", "bsd/sys/waffle_gpu_map.h", "bsd/dev/waffle_synaptics.c", "bsd/dev/waffle_adreno.c", "bsd/dev/waffle_gpu_service.c", "bsd/dev/waffle_gpu_drm.c", "bsd/dev/waffle_gpu_msm.c", "bsd/sys/waffle_gpu_msm.h", "bsd/dev/waffle_gpu_user.c", "bsd/sys/waffle_gpu_user.h", "bsd/sys/waffle_gpu_service.h", "bsd/dev/waffle_smmu.c", "bsd/sys/waffle_gpu.h", "bsd/sys/waffle_gpu_pll.h", "bsd/sys/waffle_gmu_clock.h", "bsd/sys/waffle_gpu_va.h", "bsd/sys/waffle_aop.h",
                     "bsd/dev/waffle_gmu.c", "bsd/sys/waffle_gpu_measure.h", "bsd/sys/waffle_hfi.h", "bsd/sys/waffle_hfi_tables.h", "bsd/sys/waffle_gmu.h", "bsd/sys/waffle_smmu.h", "bsd/sys/waffle_scm.h", "bsd/sys/waffle_zap.h", "bsd/sys/waffle_zap_load.h", "bsd/sys/waffle_gpu_writeback.h", "bsd/sys/waffle_gpu_compute.h", "bsd/sys/waffle_gpu_image.h", "bsd/sys/waffle_gpu_copy.h", "bsd/sys/waffle_gpu_job.h", "bsd/sys/waffle_gpu_data.h", "bsd/sys/waffle_gpu_buffer.h", "bsd/sys/waffle_gpu_glsl.h", "bsd/sys/waffle_gpu_present.h", "bsd/sys/waffle_gmu_firmware.h", "bsd/dev/macan_touch_report.h",
                     "bsd/sys/waffle_gen7_config.h", "bsd/sys/waffle_gen7_tables.h",
                     "bsd/sys/waffle_gen7_hwcg.h", "bsd/sys/waffle_gen7_cp.h", "bsd/sys/waffle_gen7_boot.h",
                     "bsd/dev/macan_input.c", "bsd/dev/macan_audio.c", "bsd/dev/macan_buttons.c", "bsd/dev/macan_adsp.c", "bsd/sys/waffle_adsp_power.h", "bsd/sys/waffle_adsp_rpmh.h", "bsd/sys/waffle_apm.h", "bsd/sys/waffle_glink_intent.h",
                     "osfmk/arm64/loader_return.c"):
        shutil.copyfile(ROOT / "kernel/files" / relative, xnu / relative)
    with (output / "kernel-build.log").open("w") as log:
        # Only build the monolithic kernel. The iig shim does not provide all
        # DriverKit exports required by the separate symbolset/config targets.
        run(["bash", ROOT / "tools/xnu-build.sh", f"-j{args.jobs}", "build"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    symbols = subprocess.check_output(["llvm-nm", str(KERNEL)], text=True)
    for symbol in ("_gicr_stride", "_loader_stub_slot", "_loader_checkpoint", "_psci_smp_start_cpu"):
        if not any(line.split()[-1:] == [symbol] for line in symbols.splitlines()):
            raise ValueError(f"Missing required kernel symbol: {symbol}")
    data = KERNEL.read_bytes()
    kernel_output = output / "kernel"
    kernel_output.write_bytes(data)
    header = output / "waffle-kernel.h"
    header.write_text(f"#define WAFFLE_KERNEL_SIZE {len(data)}u\n"
                      f"#define WAFFLE_KERNEL_CRC32 0x{zlib.crc32(data):08x}u\n" +
                      ("#define WAFFLE_USERLAND 1\n" if args.userland else "")+
                      ("#define WAFFLE_UI_SOAK_TEST 1\n" if args.ui_soak_loader else ""))
    run(["bash", ROOT / "loader/build.sh"], cwd=ROOT,
        env=os.environ | {"XNU_PLATFORM": "waffle", "WAFFLE_KERNEL_HEADER": str(header)})
    shutil.copyfile(ROOT / "loader/loader-waffle.efi", loader_dir / "loader-waffle.efi")
    shutil.copyfile(ROOT / "loader/loader-waffle.efi", output / "loader-waffle.efi")
    with (output / "uefi-build.log").open("w") as log:
        run([sys.executable, "build_uefi.py", "-d", "waffle", "-r", "DEBUG"],
            cwd=mu, stdout=log, stderr=subprocess.STDOUT)
    image = output / "HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img"
    shutil.copyfile(mu / "Mu-waffle.img", image)
    # oem selftest / oem run N select the checkpoint without uploading another
    # identical copy of the kernel for each step.
    run([sys.executable, ROOT / "loader/mkpayload.py", "-o", output / "xnu-diagnostic.xnup",
         "--usb", "--checkpoint", 1, "--cmdline", "-v bootcpu=1 loader_return_after=10",
         f"kernel={kernel_output}"], cwd=ROOT)
    manifest = {
        "target": "OnePlus 12 PJD110 / SM8650, 16 GB",
        "status": "bounded RAM userland test enabled" if args.userland else "early XNU checkpoint diagnostic",
        "hardware_tested": False,
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_diff": "source.patch",
        "kernel_sha256": hashlib.sha256(data).hexdigest(),
        "kernel_crc32": f"{zlib.crc32(data):08x}",
        "boot_image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "kernel_build_target": "build (DriverKit symbolsets excluded)",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT))
    source = output / "source"
    for relative in ("kernel/files/bsd/sys/waffle_display_source.h", "tools/tests/waffle-display-source-host.c", "kernel/files/bsd/sys/waffle_display_present.h", "tools/tests/waffle-display-present-host.c", "kernel/files/bsd/sys/waffle_display_flip.h", "tools/tests/waffle-display-flip-host.c", "kernel/files/bsd/sys/waffle_display_flush.h", "tools/tests/waffle-display-flush-host.c", "kernel/files/bsd/sys/waffle_display_smmu.h", "tools/tests/waffle-display-smmu-host.c", "kernel/files/bsd/sys/waffle_vsync_phase.h", "tools/tests/waffle-vsync-phase-host.c", "kernel/files/bsd/sys/waffle_display_survey.h", "tools/tests/waffle-display-survey-host.c", "kernel/files/bsd/sys/waffle_audio_smmu_survey.h",
                     "tools/tests/waffle-audio-smmu-survey-host.c"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in ("kernel/files/iokit/Kernel/MiniIOSurface.cpp",
                     "kernel/files/bsd/dev/macan_battery.c", "kernel/files/iokit/Kernel/MacanBattery.cpp", "kernel/files/bsd/sys/macan_input.h",
                     "kernel/files/bsd/sys/waffle_battery_readonly.h", "tools/tests/waffle-battery-readonly-host.c",
                     "tools/tests/waffle-battery-mailbox-host.py",
                     "tools/tests/waffle-battery-cli-host.py",
                     "tools/tests/waffle-battery-report-host.py",
                     "kernel/files/iokit/Kernel/MiniIOSurface.h",
                     "tools/tests/waffle-framebuffer-clipping-host.py",
                     "tools/tests/waffle-display-usecount-host.py", "tools/tests/waffle-display-retire-host.py", "tools/tests/waffle-log-batch-host.py",
                     "tools/tests/waffle-iosurface-seed-host.py",
                     "tools/tests/waffle-10mb-object-host.py"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in ("tools/tests/waffle-slider-host.c", "tools/tests/waffle-slider-power-host.py", "tools/tests/waffle-slider-config-host.py", "kernel/files/bsd/sys/waffle_slider.h", "kernel/files/bsd/dev/macan_buttons.c", "tools/tests/waffle-192mb-backing-host.py", "kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp", "kernel/files/bsd/dev/macan_torch.c", "kernel/files/bsd/dev/macan_audio.c", "loader/platform.h", "loader/identity.h", "loader/waffle.h", "loader/loader.c", "loader/build.sh", "loader/waffle-power.h", "kernel/files/bsd/sys/waffle_gpu_pll.h", "kernel/files/bsd/sys/waffle_gmu_clock.h", "tools/tests/waffle-gmu-native-clock-host.py", "tools/tests/waffle-pll1-native-host.py",
                     "tools/tests/waffle-firmware-power-host.py", "work/waffle/gpu/firmware-power-abi-audit.json",
                     "kernel/files/bsd/sys/waffle_gpu_va.h", "kernel/files/bsd/sys/waffle_gen7_config.h", "kernel/files/bsd/sys/waffle_gen7_tables.h",
                     "kernel/files/bsd/sys/waffle_gen7_hwcg.h", "kernel/files/bsd/sys/waffle_gen7_cp.h", "kernel/files/bsd/sys/waffle_gen7_boot.h",
                     "tools/tests/waffle-gen7-boot.c", "tools/tests/waffle-ucode-access-host.py", "work/waffle/gpu/vendor/msm_kgsl-uapi.h", "work/waffle/gpu/vendor/msm_kgsl-uapi.provenance.json",
                     "tools/tests/waffle-hfi-raw-fault-host.py", "tools/tests/waffle-hfi-acd-host.py", "tools/tests/waffle-smmu-stall-host.py",
                     "tools/tests/waffle-ecats-access-host.py",
                     "tools/tests/waffle-gpu-measure-host.py", "kernel/files/bsd/sys/waffle_gpu_measure.h",
                     "tools/tests/waffle-log-retrieval-host.py",
                     "tools/tests/waffle-smmu-fault-host.py", "tools/tests/waffle-hfi-publication-host.py", "tools/tests/waffle-post-prepare-query-host.py", "tools/tests/waffle-hfi-features-host.py", "tools/tests/waffle-pool-permissions-host.py", "tools/tests/waffle-dcvs-votes-host.py",
                     "tools/tests/waffle-scm-aperture-host.py", "tools/tests/waffle-zap-host.py", "tools/tests/waffle-zap-load-host.py", "tools/tests/waffle-gpu-writeback-host.py", "tools/tests/waffle-submit-session-host.py", "tools/tests/waffle-compute-payload-host.py", "tools/tests/waffle-image-host.py", "tools/tests/waffle-copy-host.py", "tools/tests/waffle-present-host.py", "tools/tests/waffle-copy-jobs-host.py", "tools/tests/waffle-service-host.py", "tools/tests/waffle-user-host.py", "tools/build-waffle-user-probe.py", "userland/src/waffle_msm_probe.c", "tools/tests/waffle-msm-host.py", "tools/tests/waffle-image-gate-host.py", "tools/tests/waffle-map-helper-host.py", "tools/tests/waffle-mapped-bo-host.py", "tools/tests/waffle-mesa-transport-host.py", "tools/mesa/drm-shim/drm_shim.c", "tools/mesa/drm-shim/xf86drm.h", "userland/src/waffle_gpu_probe.c", "userland/libmini/mini.c", "userland/libmini/mini.h", "userland/libmini/start.S", "tools/tests/fixtures/waffle-copy256.asm", "tools/tests/fixtures/waffle-input16.ppm", "tools/tests/fixtures/waffle-copy-manifest.json", "tools/tests/fixtures/waffle-copy-source.json", "tools/tests/fixtures/waffle-ramp256.asm", "tools/tests/fixtures/waffle-image-manifest.json", "tools/tests/fixtures/waffle-image-source.json", "tools/check-waffle-compute.py", "tools/tests/fixtures/waffle-compute-opcodes.json", "tools/tests/fixtures/waffle-compute-manifest.json", "tools/tests/waffle-dynamic-bo-host.py", "tools/tests/waffle-data-bo-host.py", "tools/tests/waffle-user-va-host.py", "tools/tests/waffle-glsl-host.py", "tools/build-waffle-glsl-tools.py", "tools/waffle-glsl-compile.cc", "tools/waffle-compute-export.cc", "tools/tests/fixtures/waffle-glsl-copy.comp", "tools/tests/waffle-gmu-owner-host.py", "tools/tests/waffle-tcm-owner-host.py", "tools/tests/waffle-smmu-owner-host.py", "tools/tests/waffle-board-power-owner-host.py", "kernel/files/bsd/sys/waffle_gpu_writeback.h", "kernel/files/bsd/sys/waffle_gpu_compute.h", "kernel/files/bsd/sys/waffle_gpu_image.h", "kernel/files/bsd/sys/waffle_gpu_copy.h", "kernel/files/bsd/sys/waffle_gpu_job.h", "kernel/files/bsd/sys/waffle_gpu_data.h", "kernel/files/bsd/sys/waffle_gpu_buffer.h", "kernel/files/bsd/sys/waffle_gpu_glsl.h", "kernel/files/bsd/sys/waffle_gpu_present.h", "kernel/files/bsd/sys/waffle_zap.h", "kernel/files/bsd/sys/waffle_zap_load.h",
                     "tools/tests/waffle-gen7-cp-lifecycle.c", "tools/tests/waffle-hwcg-host.py",
                     "tools/build-waffle-gpu-start-tables.py", "tools/tests/waffle-gpu-start-tables-host.py",
                     "tools/tests/waffle-gen7-config-host.py", "tools/tests/waffle-gen7-transaction.c", "tools/tests/waffle-cp-init-host.py",
                     "loader/waffle-memory.h", "loader/waffle-memory-map.h",
                     "kernel/kernel.patch", "kernel/files/bsd/dev/macan_input.c", "kernel/files/bsd/dev/macan_audio.c", "kernel/files/bsd/dev/macan_adsp.c", "kernel/files/bsd/sys/waffle_adsp_power.h", "kernel/files/bsd/sys/waffle_adsp_rpmh.h", "kernel/files/bsd/sys/waffle_apm.h", "kernel/files/bsd/sys/waffle_glink_intent.h", "tools/tests/waffle-adsp-rpmh-host.c", "tools/tests/waffle-adsp-scm-host.py", "tools/tests/waffle-gpr-reply-host.py", "tools/tests/waffle-apm-graph-host.py", "tools/tests/waffle-glink-intent-host.py",
                     "kernel/files/bsd/dev/waffle_synaptics.c", "kernel/files/bsd/dev/macan_touch_report.h",
                     "kernel/files/iokit/Kernel/WaffleGPUMemory.cpp", "tools/tests/waffle-general-submit-host.py", "tools/tests/waffle-submit-lifetime-host.py", "tools/tests/waffle-ui-root-host.py", "tools/tests/waffle-ui-window-host.py", "tools/tests/waffle-ui-request-host.py", "work/waffle/gpu/forensic-audit/E53-first-submit.json", "kernel/files/bsd/sys/waffle_gpu_submit.h", "kernel/files/bsd/sys/waffle_gpu_memory.h", "kernel/files/bsd/sys/waffle_gpu_registry.h", "kernel/files/bsd/sys/waffle_gpu_handles.h", "tools/tests/waffle-generation-handles-candidate-host.py", "tools/tests/waffle-registry-reuse-candidate-host.py", "tools/tests/waffle-generation-log-host.py", "tools/tests/waffle-issued-record-limit-host.py", "tools/tests/fixtures/waffle-drm-before-generations.c", "kernel/files/bsd/sys/waffle_gpu_reclaim.h", "tools/tests/waffle-reclaim-host.py", "tools/tests/waffle-reclaim-smmu-host.py", "tools/tests/waffle-reclaim-cdev-host.py", "tools/tests/waffle-reclaim-owner-host.py", "work/waffle/gpu/forensic-audit/E54-memory-timeline.json", "work/waffle/gpu/forensic-audit/E55-memory-timeline.json", "tools/tests/waffle-live-heap-candidate-host.py", "tools/tests/waffle-va-fragmentation-host.py", "tools/tests/waffle-runner-options-host.py", "work/waffle/gpu/forensic-audit/E58-fragmented-state.json", "tools/tests/waffle-memory-host.py", "tools/tests/waffle-registry-host.py", "tools/tests/waffle-registry-smmu-host.py", "tools/tests/waffle-registry-storage-host.py", "tools/tests/waffle-table-budget-host.py", "tools/tests/waffle-fullsize-budget-host.py", "tools/tests/waffle-ui-bo-budget-host.py", "tools/tests/waffle-ui-context-pool-host.py", "tools/tests/waffle-ui-heap-candidate-host.py", "kernel/files/iokit/Kernel/WaffleGPUMap.cpp", "kernel/files/bsd/sys/waffle_gpu_map.h", "kernel/files/bsd/dev/waffle_adreno.c", "kernel/files/bsd/dev/waffle_gpu_service.c", "tools/tests/waffle-gl-log-host.py", "tools/tests/waffle-queue-log-host.py", "tools/tests/waffle-readback-benchmark-log-host.py", "tools/analyze-waffle-readback-benchmark.py", "tools/analyze-waffle-submit-profile.py", "tools/tests/waffle-submit-profile-log-host.py", "tools/tests/waffle-submit-width-candidate-host.py", "tools/tests/waffle-msm-abi.c", "tools/build-waffle-gl-probe.py", "userland/src/waffle_gl_probe.c", "userland/src/waffle_gl_recycle_probe.h", "tools/tests/waffle-gl-recycle-probe-host.py", "tools/tests/waffle-queue-issued-limit-host.py", "tools/tests/waffle-queue-generations-candidate-host.py", "tools/tests/waffle-gl-queue-probe-host.py", "tools/tests/fixtures/waffle-drm-before-queue-reuse.c", "userland/src/waffle_gl_init.c", "tools/tests/waffle-general-drm-host.py", "tools/tests/waffle-surface-describe-host.py", "tools/tests/waffle-surface-transport-host.py", "tools/tests/waffle-surface-backing-host.py", "tools/tests/waffle-surface-registry-host.py", "tools/tests/waffle-surface-smmu-host.py", "tools/tests/waffle-surface-map-audit-host.py", "tools/tests/waffle-surface-log-host.py", "tools/tests/waffle-surface-binding-host.py", "kernel/files/bsd/sys/waffle_gpu_surface.h", "kernel/files/bsd/sys/waffle_gpu_surface_write.h", "kernel/files/bsd/sys/waffle_gpu_surface_read.h", "tools/tests/waffle-surface-read-host.c", "tools/tests/waffle-surface-import-host.py", "tools/tests/waffle-surface-sample-submit-host.py", "userland/src/waffle_surface_sample.c", "userland/src/waffle_surface_sample.h", "tools/tests/waffle-surface-import-shim-host.py", "tools/tests/waffle-surface-resource-log-host.py", "tools/tests/waffle-surface-import-log-host.py", "tools/tests/waffle-surface-read-cdev-host.py", "tools/tests/fixtures/waffle-mem-to-mem-layout.json", "tools/tests/waffle-surface-write-host.c", "tools/tests/waffle-surface-write-cdev-host.py", "tools/mesa/drm-shim/waffle_msm_transport.h", "kernel/files/bsd/dev/waffle_gpu_drm.c", "kernel/files/bsd/dev/waffle_gpu_msm.c", "kernel/files/bsd/sys/waffle_gpu_msm.h", "kernel/files/bsd/dev/waffle_gpu_user.c", "kernel/files/bsd/sys/waffle_gpu_user.h", "kernel/files/bsd/sys/waffle_gpu_service.h", "kernel/files/bsd/sys/waffle_gpu.h", "kernel/files/bsd/sys/waffle_aop.h",
                     "kernel/files/bsd/dev/waffle_smmu.c",
                     "kernel/files/bsd/dev/waffle_gmu.c", "kernel/files/bsd/sys/waffle_gmu.h", "kernel/files/bsd/sys/waffle_smmu.h",
                     "kernel/files/bsd/sys/waffle_gmu_firmware.h", "kernel/files/bsd/sys/waffle_scm.h", "tools/tests/waffle-scm-host.py", "tools/tests/waffle-secure-context-host.py", "tools/tests/waffle-protected-pool-host.py", "tools/tests/waffle-gmu-fw.c",
                     "kernel/files/bsd/sys/waffle_hfi.h", "tools/tests/waffle-hfi.c",
                     "kernel/files/bsd/sys/waffle_hfi_tables.h", "tools/build-waffle-gpu-tables.py",
                     "tools/tests/waffle-gpu-tables.py", "tools/tests/waffle-powerseq-host.py", "tools/tests/waffle-gx-host.py", "tools/tests/waffle-context-host.py", "work/waffle/gpu/vendor/kernel-drivers-iommu-io-pgtable-arm.h", "work/waffle/gpu/vendor/kernel-drivers-iommu-io-pgtable-arm.provenance.json", "tools/tests/waffle-ucode-host.py", "tools/tests/waffle-cp-host.py",
                     "tools/tests/waffle-gpu-host.py", "tools/tests/waffle-gmu-clock-host.py", "tools/tests/waffle-aop-host.py", "tools/tests/waffle-aop-session-host.py", "tools/tests/waffle-aop-owner-host.py", "tools/tests/waffle-aop-owner-log-host.py", "tools/tests/fixtures/waffle-aop-transaction-e18.inc", "tools/tests/fixtures/waffle-aop-transaction-e18.provenance.json", "tools/tests/waffle-llcc-host.py", "tools/tests/waffle-ramlog-export-host.py", "tools/tests/waffle-ramlog-raw-host.py", "tools/tests/waffle-ramlog-run.py", "tools/waffle_ramlogs.py", "tools/tests/waffle-compact-va.c",
                     "kernel/files/osfmk/arm64/loader_return.c", "tools/tests/waffle-touch.c",
                     "kernel/files/bsd/dev/macan_buttons.c",
                     "tools/check-waffle-dtb.py", "tools/build-waffle-diagnostic.py", "tools/tests/waffle-policy.c", "tools/tests/waffle-hwsched-host.py", "tools/tests/fixtures/waffle-hfi-start-allocations.json",
                     "tools/check-waffle-gpu.py", "tools/capture-waffle-gpu.py", "docs/waffle-gpu.md",
                     "tools/validate-waffle-diagnostic.py", "docs/waffle-bringup.md"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (output / (image.name + ".sha256")).write_text(f"{manifest['boot_image_sha256']}  {image.name}\n")
    print(f"Diagnostic artifacts: {output}", flush=True)


if __name__ == "__main__":
    main()
