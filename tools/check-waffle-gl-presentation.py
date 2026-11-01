#!/usr/bin/env python3
"""Check GPU GL readback, IOSurface pixels and existing display-worker evidence.

This cannot establish optical panel visibility or direct GPU scanout.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def validate(text):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("waffle_runner", root / "scripts/run_waffle_ios.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.validate_gl_log(text)
    for marker in (
        "waffle-gl-present: begin CPU_readback=1 IOSurface_import=0",
        "waffle-gl-present: checked=256 wrong=0 padding_wrong=0 GL_error=0 top_down=1",
        "waffle-gl-present: swap_accepted=1 error=0 hold_seconds=5",
        "waffle-gl-present: result=1 CPU_readback=1",
    ):
        if marker not in text:
            raise RuntimeError("Presentation proof missing: " + marker)
    s = re.search(r"waffle-gl-present: surface=(\d+) width=16 height=16 stride=(\d+) bytes=(\d+)", text)
    p = re.search(r"waffle-gl-present: swap=(\d+) surface=(\d+) display=(\d+)x(\d+) destination=(\d+),(\d+),256,256", text)
    if not s or not p:
        raise RuntimeError("Missing surface or swap geometry")
    sid, stride, size = map(int, s.groups())
    swap, presented, width, height, x, y = map(int, p.groups())
    if not sid or presented != sid or stride < 64 or stride > 4096 or stride % 4 or size < stride * 16:
        raise RuntimeError("Invalid IOSurface identity or allocation")
    if width < 256 or height < 256 or (x, y) != ((width - 256) // 2, (height - 256) // 2):
        raise RuntimeError("Invalid display destination")
    worker = (f"MiniIOMobileFramebuffer: swap {swap} layer 0: surface {sid} (16x16 'BGRA') "
              f"from 0,0 16x16 to {x},{y} 256x256, layers set 0x1")
    if worker not in text:
        raise RuntimeError("Display worker did not resolve the exact submitted IOSurface")
    if f"GPU is not done with surface {sid}" in text:
        raise RuntimeError("Display worker timed out waiting for surface")
    return dict(surface=sid, swap=swap, stride=stride, pixels_checked=256, pixels_wrong=0,
                display_worker_resolved_surface=True, CPU_readback=True,
                optical_visibility_verified=False, direct_GPU_scanout=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.log.read_text(errors="replace")), indent=2))
