#!/usr/bin/env python3
"""Verify the PJD110 CPU/GIC profile against the two stock base DTBs."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

STOCK_HASHES = {
    "9bc1713b91598db5c996b98c4f93cad93a5fe9ae14e20214afb438cf58e25e42",
    "2b27ad558c044b7ed7c2862413133659ad1f36a235597164bd24f9871038cc44",
}


def parse_fdt(data):
    magic, total, off, strings, _, version, _, _, string_size, struct_size = struct.unpack_from(">10I", data)
    if magic != 0xd00dfeed or total > len(data) or version < 17:
        raise ValueError("Unsupported FDT header")
    if off + struct_size > total or strings + string_size > total:
        raise ValueError("FDT block outside tree")
    end = off + struct_size
    names = data[strings:strings + string_size]
    stack, nodes = [], {}
    while off + 4 <= end:
        token, = struct.unpack_from(">I", data, off)
        off += 4
        if token == 1:
            stop = data.index(b"\0", off, end)
            stack.append(data[off:stop].decode("ascii"))
            off = (stop + 4) & ~3
            nodes["/".join(stack) or "/"] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from(">II", data, off)
            off += 8
            if off + length > end or nameoff >= len(names) or not stack:
                raise ValueError("Invalid FDT property")
            name = names[nameoff:names.index(b"\0", nameoff)].decode("ascii")
            nodes["/".join(stack) or "/"][name] = data[off:off + length]
            off = (off + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9 and not stack:
            return nodes
        else:
            raise ValueError(f"Unexpected FDT token {token}")
    raise ValueError("Truncated FDT")


def verify(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest not in STOCK_HASHES:
        raise ValueError(f"{path}: not one of the recorded PJD110 stock DTBs")
    nodes = parse_fdt(data)
    soc, revision = struct.unpack(">II", nodes["/"]["qcom,msm-id"])
    cpus = sorted(struct.unpack(">Q", props["reg"])[0]
                  for name, props in nodes.items() if name.startswith("/cpus/cpu@") and
                  props.get("device_type") == b"cpu\0")
    gic = nodes["/soc/interrupt-controller@17100000"]
    registers = struct.unpack(">4I", gic["reg"])
    stride, = struct.unpack(">Q", gic["redistributor-stride"])
    methods = [props["method"] for props in nodes.values()
               if b"arm,psci-1.0" in props.get("compatible", b"").split(b"\0")]
    frequency, = struct.unpack(">I", nodes["/soc/timer"]["clock-frequency"])
    if (soc != 557 or revision not in (0x10000, 0x20000) or cpus != list(range(0, 0x800, 0x100)) or
            registers != (0x17100000, 0x10000, 0x17180000, 0x200000) or
            stride != 0x40000 or methods != [b"smc\0"] or frequency != 19200000):
        raise ValueError(f"{path}: unexpected CPU/GIC/PSCI/timer profile")
    for name, props in nodes.items():
        if name.startswith("/cpus/cpu@") and props.get("device_type") == b"cpu\0":
            if props.get("enable-method") != b"psci\0":
                raise ValueError(f"{name}: unsupported CPU enable method")
    return {"file": str(path.resolve()), "sha256": digest, "soc_id": soc,
            "revision": hex(revision), "mpidrs": [hex(cpu) for cpu in cpus],
            "gic_registers": [hex(value) for value in registers],
            "gic_stride": hex(stride), "psci": "smc", "timer_hz": frequency}


def merge_ranges(ranges):
    merged = []
    for lo, hi in sorted(ranges):
        if not (0 <= lo < hi <= 1 << 40):
            raise ValueError("Invalid physical RAM range")
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def memory_ranges(nodes, prefix):
    ranges = []
    for name, props in nodes.items():
        if (name == prefix or name.startswith(prefix + "/")) and "reg" in props:
            for lo, size in struct.iter_unpack(">QQ", props["reg"]):
                if size:
                    ranges.append((lo, lo + size))
    return merge_ranges(ranges)


def live_memory(path, stock_paths):
    data = path.read_bytes()
    nodes = parse_fdt(data)
    if b"waffle" not in nodes["/"].get("model", b"") or b"qcom,pineapple\0" not in nodes["/"].get("compatible", b""):
        raise ValueError("Expected a live PJD110/waffle device tree")
    if struct.unpack_from(">I", nodes["/"]["qcom,msm-id"])[0] != 557:
        raise ValueError("Expected SM8650 SoC ID 557")
    cpus = sorted(struct.unpack(">Q", props["reg"])[0] for name, props in nodes.items()
                  if name.startswith("/cpus/cpu@") and props.get("device_type") == b"cpu\0")
    gic = nodes["/soc/interrupt-controller@17100000"]
    if cpus != list(range(0, 0x800, 0x100)) or struct.unpack(">4I", gic["reg"]) != (0x17100000, 0x10000, 0x17180000, 0x200000):
        raise ValueError("Unexpected live CPU/GIC profile")
    ram = memory_ranges(nodes, "/memory")
    if not ram:
        raise ValueError("Live tree has no concrete RAM banks")
    reserved = memory_ranges(nodes, "/reserved-memory")
    for stock in stock_paths:
        reserved += memory_ranges(parse_fdt(stock.read_bytes()), "/reserved-memory")
    # Include the FDT memreserve block as well as reserved-memory nodes.
    offset, = struct.unpack_from(">I", data, 16)
    while offset + 16 <= len(data):
        address, size = struct.unpack_from(">QQ", data, offset)
        offset += 16
        if not address and not size:
            break
        if size:
            reserved.append((address, address + size))
    else:
        raise ValueError("Unterminated FDT reservation map")
    reserved = merge_ranges(reserved)
    return {"file": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
            "ram": ram, "reserved": reserved}


def memory_header(profile):
    lines = ["/* Generated by tools/check-waffle-dtb.py from the live PJD110 FDT",
             " * plus both verified stock DTB revisions. Do not edit by hand.",
             f" * Live SHA256: {profile['sha256']}", " */",
             "#ifndef WAFFLE_MEMORY_MAP_H", "#define WAFFLE_MEMORY_MAP_H",
             "struct waffle_memory_range { uint64_t lo, hi; };"]
    for key in ("ram", "reserved"):
        lines.append(f"static const struct waffle_memory_range waffle_{key}[] = {{")
        lines += [f"    {{0x{lo:x}ULL, 0x{hi:x}ULL}}," for lo, hi in profile[key]]
        lines.append("};")
    lines += ["#endif", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtbs", type=Path, nargs=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live-dtb", type=Path)
    parser.add_argument("--memory-header", type=Path)
    parser.add_argument("--memory-output", type=Path)
    args = parser.parse_args()
    profiles = [verify(path) for path in args.dtbs]
    if {profile["sha256"] for profile in profiles} != STOCK_HASHES:
        parser.error("Supply both distinct stock DTB revisions")
    if args.memory_header or args.memory_output:
        if not args.live_dtb:
            parser.error("A captured --live-dtb is required to generate the RAM allowlist")
        profile = live_memory(args.live_dtb, args.dtbs)
        if args.memory_header:
            args.memory_header.write_text(memory_header(profile))
        if args.memory_output:
            args.memory_output.parent.mkdir(parents=True, exist_ok=True)
            args.memory_output.write_text(json.dumps(profile, indent=2) + "\n")
    output = json.dumps(profiles, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end="")
