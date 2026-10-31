#!/usr/bin/env python3
"""Read the connected PJD110's GPU metadata and firmware; no device writes/reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="/home/qarzis/platform-tools/adb")
    p.add_argument("--serial", default="1c62e9aa")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    adb = [args.adb, "-s", args.serial]

    def read(command, root=True):
        remote = shlex.join(["su", "-c", command]) if root else command
        return subprocess.run(adb + ["exec-out", remote], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout

    if read("getprop ro.soc.model", False).strip() != b"SM8650":
        raise SystemExit("Refusing capture: phone does not identify as SM8650")
    if read("id -u").strip() != b"0":
        raise SystemExit("Root read access is required to capture GPU diagnostics")
    args.output.mkdir(parents=True, exist_ok=False)
    captures = {
        "properties.txt": "getprop ro.soc.model; getprop ro.product.model; getprop ro.build.fingerprint",
        "android-live.dtb": "cat /sys/firmware/fdt",
        "kgsl.txt": "for f in gpu_model gpu_available_frequencies gpuclk max_gpuclk gpubusy; do "
                    "echo $f; cat /sys/class/kgsl/kgsl-3d0/$f; done",
        "clocks.txt": "test -r /sys/kernel/debug/clk/clk_summary && cat /sys/kernel/debug/clk/clk_summary",
        "regulators.txt": "test -r /sys/kernel/debug/regulator/regulator_summary && cat /sys/kernel/debug/regulator/regulator_summary",
    }
    manifest = {"serial": args.serial, "files": {}, "missing": []}
    for name, command in captures.items():
        try:
            data = read(command)
        except subprocess.CalledProcessError:
            manifest["missing"].append(name)
            continue
        if not data:
            manifest["missing"].append(name)
            continue
        (args.output / name).write_bytes(data)
        manifest["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    for name in ("gmu_gen70900.bin", "gen70900_sqe.fw", "gen70900_aqe.fw", "gen70900_zap.mbn",
                 "gen70900_zap.mdt", "gen70900_zap.b00", "gen70900_zap.b01", "gen70900_zap.b02"):
        for directory in ("/vendor/firmware", "/vendor/firmware_mnt/image"):
            path = f"{directory}/{name}"
            try:
                data = read(f"test -f {shlex.quote(path)} && cat {shlex.quote(path)}")
            except subprocess.CalledProcessError:
                continue
            if not data:
                continue
            if len(data) > 16 * 1024 * 1024:
                raise SystemExit(f"Unexpected firmware size: {name}: {len(data)}")
            (args.output / name).write_bytes(data)
            manifest["files"][name] = {"source": path, "size": len(data),
                                       "sha256": hashlib.sha256(data).hexdigest()}
            break
        else:
            manifest["missing"].append(name)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Captured {len(manifest['files'])} files; {len(manifest['missing'])} unavailable")


if __name__ == "__main__":
    main()
