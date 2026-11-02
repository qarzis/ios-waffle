#!/usr/bin/env python3
"""Compare native ADSP firmware and live DT resources with the XNU driver."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct


def cells(value):
    if len(value) % 4:
        raise ValueError("Invalid DT cell array")
    return struct.unpack(">" + "I" * (len(value) // 4), value)


def image(path, base, capacity):
    data = path.read_bytes()
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError(f"{path}: expected little-endian ELF32")
    phoff = struct.unpack_from("<I", data, 28)[0]
    entsize, count = struct.unpack_from("<HH", data, 42)
    if phoff != 52 or entsize != 32 or not 3 <= count <= 64 or phoff + count * entsize > len(data):
        raise ValueError(f"{path}: unsupported program header table")
    headers = [struct.unpack_from("<8I", data, phoff + i * entsize) for i in range(count)]
    hashes = [h for h in headers if (h[6] >> 24) & 7 == 2]
    if len(hashes) != 1 or headers[0][0] == 1 or headers[0][4] < phoff + count * entsize:
        raise ValueError(f"{path}: invalid Qualcomm metadata layout")
    if headers[0][4] + hashes[0][4] != len(data):
        raise ValueError(f"{path}: metadata size mismatch")
    loads = [(i, h) for i, h in enumerate(headers) if h[0] == 1 and h[5] and (h[6] >> 24) & 7 != 2]
    if not loads:
        raise ValueError(f"{path}: no load segments")
    lowest = min(h[3] for _, h in loads)
    relocate = any(h[6] & (1 << 27) for _, h in loads)
    origin = lowest if relocate else base
    highest = max(h[3] + h[5] for _, h in loads)
    span = ((highest + 4095) & ~4095) - origin
    if not 0 < span <= capacity or base + span > 1 << 32:
        raise ValueError(f"{path}: firmware span {span:#x} exceeds DT capacity {capacity:#x}")
    segments = []
    for i, h in loads:
        _, _, _, physical, filesz, memsz, _, _ = h
        if filesz > memsz or physical < origin or physical - origin + memsz > capacity:
            raise ValueError(f"{path}: invalid segment {i}")
        item = {"index": i, "destination": base + physical - origin, "file_size": filesz, "memory_size": memsz}
        if filesz:
            blob = path.with_suffix(f".b{i:02d}")
            payload = blob.read_bytes()
            if len(payload) != filesz:
                raise ValueError(f"{blob}: size mismatch")
            item["sha256"] = hashlib.sha256(payload).hexdigest()
        segments.append(item)
    return {"base": base, "capacity": capacity, "span": span, "relocatable": relocate,
            "metadata_sha256": hashlib.sha256(data).hexdigest(), "segments": segments}


def audit(dtb, firmware, driver):
    parser = runpy.run_path(str(Path(__file__).with_name("check-waffle-dtb.py")))["parse_fdt"]
    data = dtb.read_bytes()
    nodes = parser(data)
    by_handle = {cells(d["phandle"])[0]: (p, d) for p, d in nodes.items() if "phandle" in d}

    def compatible(value):
        matches = [(p, d) for p, d in nodes.items() if value.encode() in d.get("compatible", b"").split(b"\0")]
        if len(matches) != 1:
            raise ValueError(f"Expected one {value}, got {len(matches)}")
        return matches[0]

    dsp_path, dsp = compatible("qcom,pineapple-adsp-pas")
    regions = cells(dsp["memory-region"])
    if len(regions) != 2:
        raise ValueError("Expected ADSP and ADSP DTB memory regions")
    images = {}
    for name, handle in zip(("adsp", "adsp_dtb"), regions):
        _, region = by_handle[handle]
        hi, lo, size_hi, size_lo = cells(region["reg"])
        if "no-map" not in region:
            raise ValueError(f"{name}: region must be reserved no-map")
        images[name] = image(firmware / f"{name}.mdt", hi << 32 | lo, size_hi << 32 | size_lo)
    a, b = images.values()
    if max(a["base"], b["base"]) < min(a["base"] + a["capacity"], b["base"] + b["capacity"]):
        raise ValueError("ADSP and DTB reservations overlap")
    edge = nodes[dsp_path + "/glink-edge"]
    _, ipcc = by_handle[cells(edge["mboxes"])[0]]
    if b"qcom,ipcc" not in ipcc.get("compatible", b"").split(b"\0"):
        raise ValueError("ADSP mailbox does not reference IPCC")
    _, qmp = by_handle[cells(dsp["qcom,qmp"])[0]]
    _, command = compatible("qcom,cmd-db")
    _, shared = compatible("qcom,smem")
    _, hwlock = by_handle[cells(shared["hwlocks"])[0]]
    lock_id = cells(shared["hwlocks"])[1]
    lock_syscon, lock_offset, lock_stride = cells(hwlock["syscon"])
    _, syscon = by_handle[lock_syscon]
    rsc = nodes["/soc/rsc@17a00000"]
    drv = nodes["/soc/rsc@17a00000/drv@2"]
    rsc_regs = cells(rsc["reg"])
    drv_id = cells(drv["qcom,drv-id"])[0]
    profile = {"adsp_base": a["base"], "adsp_size": a["capacity"],
               "dtb_base": b["base"], "dtb_size": b["capacity"],
               "ipcc": cells(ipcc["reg"])[0], "aoss": cells(qmp["reg"])[0],
               "cmd_db": cells(command["reg"])[1], "smem": cells(shared["reg"])[1],
               "rsc": rsc_regs[drv_id * 2], "tcs_offset": cells(drv["qcom,tcs-offset"])[0],
               "smem_lock": cells(syscon["reg"])[0] + lock_offset + lock_id * lock_stride}
    source = driver.read_text()
    constants = {key: int(value, 16) for key, value in re.findall(r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+)", source, re.M)}
    blocks = {key: int(value, 16) for key, value in re.findall(r'static struct block (\w+) = \{ "[^"]+", (0x[0-9a-fA-F]+)', source)}
    pairs = {"adsp_base": "ADSP_MEMORY", "adsp_size": "ADSP_MEMORY_SIZE", "dtb_base": "DTB_MEMORY",
             "dtb_size": "DTB_MEMORY_SIZE", "cmd_db": "CMD_DB_PHYS", "smem": "SMEM_PHYS", "tcs_offset": "RSC_TCS_BASE"}
    mismatches = []
    for key, expected in profile.items():
        actual = constants.get(pairs[key]) if key in pairs else blocks.get(key)
        if actual != expected:
            mismatches.append({"resource": key, "driver": actual, "live_dt": expected})
    return {"dtb_sha256": hashlib.sha256(data).hexdigest(), "driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
            "profile": profile, "images": images, "driver_mismatches": mismatches,
            "native_firmware_fits_dt": True, "driver_matches_dt": not mismatches,
            "hardware_boot_tested": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtb", type=Path, required=True)
    ap.add_argument("--firmware", type=Path, required=True)
    ap.add_argument("--driver", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = audit(args.dtb, args.firmware, args.driver)
    except (ValueError, OSError, KeyError, struct.error) as error:
        ap.exit(2, f"Audio preflight failed: {error}\n")
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for mismatch in result["driver_mismatches"]:
        print(f'{mismatch["resource"]}: driver={mismatch["driver"]!r}, live_dt={mismatch["live_dt"]:#x}')
    print("Native firmware fits DT; hardware boot has not been tested.")
    return 0 if result["driver_matches_dt"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
