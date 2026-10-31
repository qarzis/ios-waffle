"""Derive a bounded RAM-log manifest from one recent live XNU journal."""
from pathlib import Path
import hashlib
import json
import re
import struct
import time


def create_manifest(run, kernel, output, probe):
    run, kernel, output = Path(run), Path(kernel), Path(output)
    payload = (run / "payload.xnup").read_bytes()
    if len(payload) < 8 or len(payload) > 0x3f00000:
        raise ValueError("Invalid staged payload size")
    if struct.unpack_from("<II", payload) != (0x50554e58, len(payload) - 8):
        raise ValueError("Invalid staged payload header")
    offset, entries = 8, {}
    while offset + 24 <= len(payload):
        name, size, reserved = struct.unpack_from("<16sII", payload, offset)
        offset += 24
        name = name.rstrip(b"\0")
        if not name:
            if size or reserved or offset != len(payload):
                raise ValueError("Invalid staged payload terminator")
            break
        if reserved or name in entries or offset + size > len(payload):
            raise ValueError("Invalid staged payload entry")
        entries[name] = payload[offset:offset + size]
        offset += (size + 15) & ~15
    else:
        raise ValueError("Missing staged payload terminator")
    if entries.get(b"kernel") != kernel.read_bytes():
        raise ValueError("Kernel differs from the staged run")
    if not re.search(rb"(?:^| )waffle_gpu=" + str(probe).encode() + rb"(?: |\0|$)", entries.get(b"cmdline", b"")):
        raise ValueError("Probe differs from the staged run")
    if "oem run 0\nOKAY" not in (run / "host.log").read_text(errors="replace"):
        raise ValueError("No accepted loader launch in this run")
    candidates = sorted(run.glob("kernel-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    marker = f"RAM_LOG_MANIFEST complete probe={probe} pages=5"
    for log in candidates:
        text = log.read_text(errors="replace")
        if marker not in text:
            continue
        age = time.time() - log.stat().st_mtime
        if not -5 <= age <= 900:
            raise ValueError("RAM-log journal is stale")
        entries = {}
        for kind, index, pa, size in re.findall(r"RAM_LOG (GMU_LOG|HFI) ([0-9]+) pa=([0-9a-f]+) bytes=([0-9a-f]+)", text):
            key = (kind, int(index))
            value = (int(pa, 16), int(size, 16))
            if key in entries and entries[key] != value:
                raise ValueError("Conflicting RAM-log addresses")
            entries[key] = value
        keys = [("GMU_LOG", i) for i in range(4)] + [("HFI", 0)]
        if set(entries) != set(keys):
            raise ValueError("Expected four GMU pages and one HFI page")
        seen = set()
        for address, size in entries.values():
            if size != 0x4000 or address & 0x3fff or not 0x8c0000000 <= address <= 0xbffffc000 or address in seen:
                raise ValueError("RAM-log page outside permitted XNU heap bank, duplicated or unaligned")
            seen.add(address)
        data = "".join(f"{kind} {index} {entries[kind,index][0]:016x} 4000\n" for kind, index in keys)
        output.write_text(data)
        output.chmod(0o600)
        report = {"probe": probe, "source_log": str(log.resolve()), "run": str(run.resolve()),
                  "source_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                  "kernel_sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(),
                  "manifest_sha256": hashlib.sha256(data.encode()).hexdigest(),
                  "pages": 5, "bytes": 81920, "age_seconds": age}
        output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    raise ValueError("No complete current RAM-log manifest in the live journal")
