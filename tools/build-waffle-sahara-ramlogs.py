#!/usr/bin/env python3
"""Build the bounded RAM-log client using unchanged pinned QDL USB objects."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
qdl = root / "work/waffle/gpu/qdl-source"
output = root / "work/waffle/gpu/ramlog-client"
output.mkdir(exist_ok=True)
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=qdl, text=True).strip() == "d66c6efd72759be5dbb6c7199cd8bd1d9f2674ec"
assert not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=qdl)
for name in ("waffle-ramlog-manifest", "waffle-sahara-ramlogs"):
    target = output / (name + "-test")
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    root / "tools/tests" / (name + ".c"), "-o", target], check=True)
    subprocess.run([target], check=True)
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "libusb-1.0", "libxml-2.0"], text=True))
binary = output / "waffle-sahara-ramlogs"
objects = [qdl / "build/qdl.p/src_usb.c.o", qdl / "build/libqdl_common.a"]
subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-g",
                "-I", qdl / "include", "-I", qdl / "src", "-I", qdl / "build",
                root / "tools/waffle-sahara-ramlogs.c", *objects, *flags, "-o", binary], check=True)
symbols = subprocess.check_output(["nm", str(binary)], text=True)
assert "firehose_" not in symbols and "sahara_run" not in symbols
paths = [root / "tools/waffle-sahara-ramlogs.c", root / "tools/waffle-sahara-ramlogs.h",
         root / "tools/waffle-ramlog-manifest.h", *objects, binary]
report = {"qdl_commit": "d66c6efd72759be5dbb6c7199cd8bd1d9f2674ec",
          "sahara_commands": ["HELLO_RESP", "MEM_READ64", "RESET"],
          "log_pages": 5, "log_bytes": 81920, "hardware_tested": False,
          "sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"binary": str(binary.relative_to(root)), "host_tests": "passed", "hardware_tested": False}))
