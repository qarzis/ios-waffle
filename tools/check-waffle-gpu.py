#!/usr/bin/env python3
"""Check the initial Adreno750 register profile against stock and live FDTs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("waffle_fdt", ROOT / "tools/check-waffle-dtb.py")
fdt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fdt)


def inspect(path):
    data = path.read_bytes()
    nodes = fdt.parse_fdt(data)
    if struct.unpack_from(">II", nodes["/"]["qcom,msm-id"])[0] != 557:
        raise ValueError(f"{path}: not SM8650")
    expected = {
        "/soc/clock-controller@100000": (0x100000, 0x1f4200),
        "/soc/clock-controller@3d90000": (0x3d90000, 0x9800),
        "/soc/kgsl-smmu@3da0000": (0x3da0000, 0x40000),
        "/soc/kgsl-smmu@3da0000/gpu_qtb@3de8000": (0x3de8000, 0x1000),
    }
    gpu = nodes["/soc/qcom,kgsl-3d0@3d00000"]
    gmu = nodes["/soc/qcom,gmu@3d69000"]
    chip, = struct.unpack(">I", gpu["qcom,chipid"])
    if chip not in (0x43051400, 0x43051401):
        raise ValueError(f"{path}: unknown GPU chip ID {chip:x}")
    compatible = f"qcom,adreno-gpu-gen7-9-{chip & 1}".encode()
    if compatible not in gpu["compatible"].split(b"\0"):
        raise ValueError(f"{path}: GPU compatible does not match chip ID")
    registers = {}
    for node, wanted in expected.items():
        got = struct.unpack_from(">II", nodes[node]["reg"])
        if got != wanted:
            raise ValueError(f"{path}: {node} has {got}, expected {wanted}")
        registers[node] = [hex(x) for x in got]
    for props, wanted in ((gpu, {"kgsl_3d0_reg_memory": (0x3d00000, 0x40000),
                                "rscc": (0x3d50000, 0x10000), "cx_misc": (0x3d9e000, 0x2000)}),
                           (gmu, {"gmu": (0x3d68000, 0x37000), "gmu_pdc": (0xb280000, 0x10000)})):
        names = props["reg-names"].rstrip(b"\0").decode().split("\0")
        values = list(struct.iter_unpack(">II", props["reg"]))
        if len(names) != len(values):
            raise ValueError(f"{path}: malformed reg-names")
        actual = dict(zip(names, values))
        for name, target in wanted.items():
            if actual.get(name) != target:
                raise ValueError(f"{path}: {name} differs from SM8650 profile")
            registers[name] = [hex(x) for x in target]
    llcc = nodes["/soc/cache-controller@25000000"]
    if (b"qcom,pineapple-llcc" not in llcc["compatible"].split(b"\0") or
            b"qcom,llcc-v50" not in llcc["compatible"].split(b"\0") or
            struct.unpack(">IIII", llcc["reg"]) != (0x25000000, 0x800000, 0x25800000, 0x200000) or
            llcc["reg-names"].rstrip(b"\0").split(b"\0") != [b"llcc_base", b"llcc_broadcast_base"]):
        raise ValueError(f"{path}: LLCC differs from the bounded SM8650 profile")
    registers["llcc_base"] = ["0x25000000", "0x800000"]
    registers["llcc_broadcast_base"] = ["0x25800000", "0x200000"]
    return {"file": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
            "chip_id": hex(chip), "compatible": compatible.decode(), "registers": registers}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dtbs", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = [inspect(path) for path in args.dtbs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"GPU profile agrees with {len(result)} device trees; hardware access remains untested")


if __name__ == "__main__":
    main()
