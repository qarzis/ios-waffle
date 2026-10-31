#!/usr/bin/env python3
"""Bind RAM-log pages to the staged kernel/probe and reject stale journals."""
from pathlib import Path
import os
import struct
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from waffle_ramlogs import create_manifest

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    run = root / "run"
    run.mkdir()
    kernel = root / "kernel"
    kernel.write_bytes(b"test kernel")
    body = bytearray()
    for name, data in ((b"kernel", kernel.read_bytes()), (b"cmdline", b"-v waffle_gpu=58\0")):
        body += struct.pack("<16sII", name, len(data), 0) + data + b"\0" * ((-len(data)) & 15)
    body += bytes(24)
    payload = struct.pack("<II", 0x50554e58, len(body)) + body
    (run / "payload.xnup").write_bytes(payload)
    (run / "host.log").write_text("oem run 0\nOKAY\n")
    good = "".join(f"RAM_LOG GMU_LOG {i} pa={0x8c1000000+i*0x8000:x} bytes=4000\n" for i in range(4))
    good += "RAM_LOG HFI 0 pa=8c2000000 bytes=4000\nRAM_LOG_MANIFEST complete probe=58 pages=5\n"
    log = run / "kernel-1.log"
    log.write_text(good + good)
    output = root / "manifest"
    assert create_manifest(run, kernel, output, 58)["bytes"] == 81920
    output.unlink()

    def denied(text=good, probe=58):
        log.write_text(text)
        try:
            create_manifest(run, kernel, output, probe)
        except ValueError:
            assert not output.exists()
            return
        raise AssertionError("invalid run accepted")

    denied(probe=59)
    denied(good.replace("8c2000000", "8c1000000"))
    denied(good.replace("8c2000000", "8c2000001"))
    denied(good.replace("8c2000000", "c300000"))
    denied(good.replace("bytes=4000", "bytes=8000"))
    denied(good + "RAM_LOG HFI 0 pa=8c3000000 bytes=4000\n")
    denied(good.replace("RAM_LOG_MANIFEST complete", "incomplete"))
    kernel.write_bytes(b"different kernel")
    denied()
    kernel.write_bytes(b"test kernel")
    (run / "host.log").write_text("transfer only")
    denied()
    (run / "host.log").write_text("oem run 0\nOKAY\n")
    log.write_text(good)
    os.utime(log, (time.time()-1000, time.time()-1000))
    try:
        create_manifest(run, kernel, output, 58)
    except ValueError:
        pass
    else:
        raise AssertionError("stale run accepted")
print("RAM-log run/kernel/probe binding, stale/duplicate/range/size refusals passed")
