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
    args = parser.parse_args()
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
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-policy.c", "-o", output / "test-policy"], cwd=ROOT)
    run([output / "test-policy"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
         ROOT / "tools/tests/waffle-touch.c", "-o", output / "test-touch"], cwd=ROOT)
    run([output / "test-touch"])
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         ROOT / "tools/tests/waffle-compact-va.c", "-o", output / "test-compact-va"])
    run([output / "test-compact-va"])
    run([sys.executable, ROOT / "tools/tests/waffle-gpu-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gmu-clock-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-gmu-native-clock-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-firmware-power-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-pll1-native-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-aop-host.py"])
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
    run([sys.executable, ROOT / "tools/tests/waffle-smmu-fault-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-publication-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-post-prepare-query-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-features-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-pool-permissions-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-dcvs-votes-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-hfi-acd-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-scm-host.py"])
    run([sys.executable, ROOT / "tools/tests/waffle-scm-aperture-host.py"])
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
    # These board overlays may change after XNU was first prepared. Compile
    # the source included in the artifact snapshot, rather than stale copies.
    for relative in ("bsd/dev/waffle_synaptics.c", "bsd/dev/waffle_adreno.c", "bsd/dev/waffle_smmu.c", "bsd/sys/waffle_gpu.h", "bsd/sys/waffle_gpu_pll.h", "bsd/sys/waffle_gmu_clock.h", "bsd/sys/waffle_gpu_va.h", "bsd/sys/waffle_aop.h",
                     "bsd/dev/waffle_gmu.c", "bsd/sys/waffle_hfi.h", "bsd/sys/waffle_hfi_tables.h", "bsd/sys/waffle_gmu.h", "bsd/sys/waffle_scm.h", "bsd/sys/waffle_gmu_firmware.h", "bsd/dev/macan_touch_report.h",
                     "bsd/sys/waffle_gen7_config.h", "bsd/sys/waffle_gen7_tables.h",
                     "bsd/sys/waffle_gen7_hwcg.h", "bsd/sys/waffle_gen7_cp.h", "bsd/sys/waffle_gen7_boot.h",
                     "bsd/dev/macan_input.c", "bsd/dev/macan_audio.c", "bsd/dev/macan_buttons.c",
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
                      ("#define WAFFLE_USERLAND 1\n" if args.userland else ""))
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
    for relative in ("loader/platform.h", "loader/waffle.h", "loader/loader.c", "loader/build.sh", "loader/waffle-power.h", "kernel/files/bsd/sys/waffle_gpu_pll.h", "kernel/files/bsd/sys/waffle_gmu_clock.h", "tools/tests/waffle-gmu-native-clock-host.py", "tools/tests/waffle-pll1-native-host.py",
                     "tools/tests/waffle-firmware-power-host.py", "work/waffle/gpu/firmware-power-abi-audit.json",
                     "kernel/files/bsd/sys/waffle_gpu_va.h", "kernel/files/bsd/sys/waffle_gen7_config.h", "kernel/files/bsd/sys/waffle_gen7_tables.h",
                     "kernel/files/bsd/sys/waffle_gen7_hwcg.h", "kernel/files/bsd/sys/waffle_gen7_cp.h", "kernel/files/bsd/sys/waffle_gen7_boot.h",
                     "tools/tests/waffle-gen7-boot.c", "tools/tests/waffle-ucode-access-host.py", "work/waffle/gpu/vendor/msm_kgsl-uapi.h", "work/waffle/gpu/vendor/msm_kgsl-uapi.provenance.json",
                     "tools/tests/waffle-hfi-raw-fault-host.py", "tools/tests/waffle-hfi-acd-host.py", "tools/tests/waffle-smmu-stall-host.py",
                     "tools/tests/waffle-ecats-access-host.py",
                     "tools/tests/waffle-smmu-fault-host.py", "tools/tests/waffle-hfi-publication-host.py", "tools/tests/waffle-post-prepare-query-host.py", "tools/tests/waffle-hfi-features-host.py", "tools/tests/waffle-pool-permissions-host.py", "tools/tests/waffle-dcvs-votes-host.py",
                     "tools/tests/waffle-scm-aperture-host.py",
                     "tools/tests/waffle-gen7-cp-lifecycle.c", "tools/tests/waffle-hwcg-host.py",
                     "tools/build-waffle-gpu-start-tables.py", "tools/tests/waffle-gpu-start-tables-host.py",
                     "tools/tests/waffle-gen7-config-host.py", "tools/tests/waffle-gen7-transaction.c", "tools/tests/waffle-cp-init-host.py",
                     "loader/waffle-memory.h", "loader/waffle-memory-map.h",
                     "kernel/kernel.patch", "kernel/files/bsd/dev/macan_input.c", "kernel/files/bsd/dev/macan_audio.c",
                     "kernel/files/bsd/dev/waffle_synaptics.c", "kernel/files/bsd/dev/macan_touch_report.h",
                     "kernel/files/bsd/dev/waffle_adreno.c", "kernel/files/bsd/sys/waffle_gpu.h", "kernel/files/bsd/sys/waffle_aop.h",
                     "kernel/files/bsd/dev/waffle_smmu.c",
                     "kernel/files/bsd/dev/waffle_gmu.c", "kernel/files/bsd/sys/waffle_gmu.h",
                     "kernel/files/bsd/sys/waffle_gmu_firmware.h", "kernel/files/bsd/sys/waffle_scm.h", "tools/tests/waffle-scm-host.py", "tools/tests/waffle-secure-context-host.py", "tools/tests/waffle-protected-pool-host.py", "tools/tests/waffle-gmu-fw.c",
                     "kernel/files/bsd/sys/waffle_hfi.h", "tools/tests/waffle-hfi.c",
                     "kernel/files/bsd/sys/waffle_hfi_tables.h", "tools/build-waffle-gpu-tables.py",
                     "tools/tests/waffle-gpu-tables.py", "tools/tests/waffle-powerseq-host.py", "tools/tests/waffle-gx-host.py", "tools/tests/waffle-context-host.py", "work/waffle/gpu/vendor/kernel-drivers-iommu-io-pgtable-arm.h", "work/waffle/gpu/vendor/kernel-drivers-iommu-io-pgtable-arm.provenance.json", "tools/tests/waffle-ucode-host.py", "tools/tests/waffle-cp-host.py",
                     "tools/tests/waffle-gpu-host.py", "tools/tests/waffle-gmu-clock-host.py", "tools/tests/waffle-aop-host.py", "tools/tests/waffle-llcc-host.py", "tools/tests/waffle-ramlog-export-host.py", "tools/tests/waffle-ramlog-raw-host.py", "tools/tests/waffle-ramlog-run.py", "tools/waffle_ramlogs.py", "tools/tests/waffle-compact-va.c",
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
