#!/usr/bin/env python3
"""Check GPU GL readback, IOSurface pixels and existing display-worker evidence.

This cannot establish optical panel visibility or direct GPU scanout.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def validate(text, eagl=False, frames=False, hook=False, fullsize=False):
    hook = hook or fullsize
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("waffle_runner", root / "scripts/run_waffle_ios.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.validate_gl_log(text)
    if eagl or frames or hook:
        for marker in (
            "waffle-gl-eagl: begin actual_adapter=gl_osmesa API=2 texture_FBO=1",
            "waffle-gl-eagl: FBO_status=8cd5",
            "waffle-gl-eagl: result=1 actual_adapter=gl_osmesa API=2",
            "waffle-gl-user: renderer=FD750 version=OpenGL ES",
        ):
            if marker not in text:
                raise RuntimeError("Actual EAGL adapter proof missing: " + marker)
    if frames:
        observed = {}
        for frame, wrong, error, outside, inside in re.findall(
            r"waffle-gl-frames: frame=(\d+) checked=256 wrong=(\d+) GL_error=([0-9a-f]+) outside=([0-9a-f]{8}) inside=([0-9a-f]{8})", text
        ):
            frame = int(frame)
            value = tuple(int(v, base) for v, base in ((wrong, 10), (error, 16), (outside, 16), (inside, 16)))
            if frame in observed and observed[frame] != value:
                raise RuntimeError("Conflicting frame readback")
            observed[frame] = value
        expected = {i: (0, 0, 0xffff0000 if i % 2 == 0 else 0xff000000, 0xff0040ff) for i in range(64)}
        if observed != expected or "waffle-gl-frames: frames=64 checked=16384 wrong=0 result=1" not in text:
            raise RuntimeError("Incomplete, stale or incorrect alternating frame readback")
        if runner.gl_completed_fences(text) < 64:
            raise RuntimeError("Fewer GPU submissions than rendered frames")
    for marker in (
        "waffle-gl-present: begin CPU_readback=1 IOSurface_import=0",
        "waffle-gl-present: checked=256 wrong=0 padding_wrong=0 GL_error=0 top_down=1",
        "waffle-gl-present: swap_accepted=1 error=0 hold_seconds=5",
        "waffle-gl-present: result=1 CPU_readback=1",
    ):
        if marker not in text:
            raise RuntimeError("Presentation proof missing: " + marker)
    s = re.search(r"waffle-gl-present: surface=(\d+) width=(\d+) height=(\d+) stride=(\d+) bytes=(\d+)", text)
    p = re.search(r"waffle-gl-present: swap=(\d+) surface=(\d+) display=(\d+)x(\d+) destination=(\d+),(\d+),(\d+),(\d+)", text)
    if not s or not p:
        raise RuntimeError("Missing surface or swap geometry")
    sid, sw, sh, stride, size = map(int, s.groups())
    expected_surface = (750, 1624) if fullsize else (16, 16)
    expected_destination = (750, 1624) if fullsize else (256, 256)
    swap, presented, width, height, x, y, dw, dh = map(int, p.groups())
    if not sid or presented != sid or (sw, sh) != expected_surface or stride < sw * 4 or stride > 16384 or stride % 4 or size < stride * sh:
        raise RuntimeError("Invalid IOSurface identity or allocation")
    if hook:
        for marker in (
            "waffle-gl-hook: begin actual_library=libredwood-gl private_table=1 public_GL_TLS=0",
            "waffle-gl-hook: actual_EAGLContext=1 table_nonnull=1 context_nonnull=1",
            "waffle-gl-hook: input_version_directive=0 shader_translation=actual_hook",
            f"waffle-gl-hook: attachImage=1 surface={sid} inverted=1",
            "waffle-gl-hook: IOSurface_readback_owner=EAGL_hook probe_writes=0",
            "redwood-gl: -[EAGLContext getMacroContextPrivate]",
            "redwood-gl: -[EAGLContext attachImage:toCoreSurface:invertedRender:]",
            "redwood-gl: 8 of 8 methods of EAGLContext are ours",
        ):
            if marker not in text:
                raise RuntimeError("Actual EAGL hook proof missing: " + marker)
    if (dw, dh) != expected_destination or width < dw or height < dh or (x, y) != ((width - dw) // 2, (height - dh) // 2):
        raise RuntimeError("Invalid display destination")
    worker = (f"MiniIOMobileFramebuffer: swap {swap} layer 0: surface {sid} ({sw}x{sh} 'BGRA') "
              f"from 0,0 {sw}x{sh} to {x},{y} {dw}x{dh}, layers set 0x1")
    if worker not in text:
        raise RuntimeError("Display worker did not resolve the exact submitted IOSurface")
    if f"GPU is not done with surface {sid}" in text:
        raise RuntimeError("Display worker timed out waiting for surface")
    if fullsize and "waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1" not in text:
        raise RuntimeError("Full surface pixel correctness not established")
    return dict(full_surface_pixels_checked=1218000 if fullsize else 256, surface=sid, swap=swap, stride=stride, pixels_checked=256, pixels_wrong=0,
                actual_EAGL_GL_adapter=eagl or frames or hook, actual_EAGL_hook=hook,
                consecutive_frames=64 if frames else 1,
                display_worker_resolved_surface=True, CPU_readback=True,
                optical_visibility_verified=False, direct_GPU_scanout=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--eagl", action="store_true", help="Require the actual EAGL API2 GL adapter and texture FBO")
    parser.add_argument("--frames", action="store_true", help="Require64 correct alternating frames and actual GPU completions")
    parser.add_argument("--hook", action="store_true", help="Require the actual EAGL private table and hook-owned IOSurface readback")
    parser.add_argument("--fullsize", action="store_true", help="Require all750x1624 actual hook-owned pixels and fullscreen display")
    args = parser.parse_args()
    print(json.dumps(validate(args.log.read_text(errors="replace"), args.eagl, args.frames, args.hook, args.fullsize), indent=2))
