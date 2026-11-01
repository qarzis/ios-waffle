# OnePlus 12 GPU progress

Adreno 750 runs actual CoreAnimation/backboardd composition through Darwin Mesa.
The latest RAM-only UI test ran for **240 seconds**, completing **17,525 GPU
submissions** and a clean GPU shutdown. Earlier captures show desktop and Sileo
while the GPU compositor was active.

This remains a bounded test. Indefinite operation, FPS, and Metal are not qualified.
Some widgets have rendering defects. VA fragmentation and descriptor lifetime
remain under investigation. The normal image still selects softpipe unless the isolated
GPU test is enabled.

| Verified test | Result | Evidence |
| --- | --- | --- |
| E21: compute shader | First verified shader execution | [Report](../work/waffle/gpu/forensic-audit/E21-result.json) |
| E29–E33: Mesa buffers and commands | GLSL compute, userspace submission, direct BO mappings and GPU completion tokens | [E33 report](../work/waffle/gpu/forensic-audit/E33-result.json) |
| E39: actual Mesa OpenGL | FD750 triangle; all 256 pixels correct | [Report](../work/waffle/gpu/forensic-audit/E39-result.json) |
| E40–E41: IOSurface and GL adapter | GPU result read into IOSurface and resolved by the display worker; actual EAGL GL adapter tested | [E41 report](../work/waffle/gpu/forensic-audit/E41-result.json) |
| E42: repeated GLES frames | 64 alternating frames; 16,384 correct pixels, 133 GPU completions, stable 25 BOs | [Report](../work/waffle/gpu/forensic-audit/E42-result.json) |
| E43: actual EAGL hook | Actual EAGLContext, private dispatch table and attachImage; hook performs IOSurface readback | [Report](../work/waffle/gpu/forensic-audit/E43-result.json) |
| E44: full logical display size | 750 × 1624, all 1,218,000 pixels correct; 205 GPU completions, 28 BOs, complete shutdown and Android recovery | [Report](../work/waffle/gpu/forensic-audit/E44-hardware-result.json), [kernel log](../work/waffle/runs/20261101T130419Z/kernel-final.log) |

| New verified test | Result | Evidence |
| --- | --- | --- |
| E55: BO reclamation | CPU mapping revoke, owned PTE removal, both ASIDs synchronized before release; actual GPU VA reuse and 256 reference pixels pass | [Control](../work/waffle/gpu/forensic-audit/E55-control-result.json) |
| E57: UI compositor | Desktop captured during GPU composition; planned 60-second stop and complete GPU cleanup | [Report](../work/waffle/gpu/forensic-audit/E57-result.json) |
| E58: sustained UI | 240 seconds, all 16,351 completion tokens verified; 2,682 early BO releases plus 1,697 at shutdown | [Report](../work/waffle/gpu/forensic-audit/E58-result.json), [GPU event journal](../work/waffle/runs/20261101T210014Z/ui-gpu-events.log) |
| E59: separate VA budget | 256 MiB virtual placement, unchanged 128 MiB physical budget; small GL control and 240-second UI test pass component checks | [Report](../work/waffle/gpu/forensic-audit/E59-result.json) |
| E61: inverted readback A/B | Same 750 × 1624 scene, all 1,218,000 pixels correct; readback 68,126 → 5,408 µs, 1,624 → 1 GL reads | [Comparison](../work/waffle/gpu/forensic-audit/E61-comparison.json) |
| E61: UI with qualified readback hook | 240 seconds, 17,525 GPU completions, clean stop; backboardd used the existing one-read path, so no UI FPS gain is established | [Report](../work/waffle/gpu/forensic-audit/E61-UI-result.json) |

The readback timing is one controlled frame per policy, not an FPS benchmark.
E61 also logged GEM_NEW EINVAL without enough request details to establish why;
no allocation-budget or submission failure was logged. Original outer runner
failures due to lost rolling-console startup evidence remain recorded.

## Current implementation

One owning backboardd process uses synchronous GPU submissions. Large requests
are partitioned in order into complete-root windows. The physical BO budget is
128 MiB, the per-BO bound is 8 MiB, and 8,192 descriptor records are available.
Virtual placement spans 256 MiB;
physical residency remains limited to 128 MiB.
Closed BOs are revoked before release. GPU fences remain monotonic; serialized
HFI tags cycle independently of them. The former 1,024-submission diagnostic cap
has been removed and crossed on hardware.

Presentation still reads GPU-rendered data into IOSurface and uses the existing
CPU display path. This is not direct GPU scanout. Other processes can still use
softpipe. A composite UI capture is not a pixel-reference test of every app.

## Remaining work

- Qualify GPU access beyond the old 128 MiB VA boundary. E59 separates VA from
  physical residency and passes the measured fragmentation host model, but its
  hardware workload did not allocate above that boundary.
- Reuse descriptor records with stale-handle protection before indefinite sessions.
- Remove diagnostic process/loader timers only after persistent-mode validation.
- Measure and improve readback, submission and logging costs; no measured FPS claim yet.
- Port hakios-metal's A6xx/compiler/transport paths to A750 after the GPU baseline.

The original E58 outer runner exit was 1 because its final rolling console lost
startup markers. That failure is retained. The event journal verifies all 16,351
GPU tokens, and the final raw snapshot verifies the planned stop and successful
parent cleanup. The phone returned to Android, independently confirmed by ADB.
The [architecture review](../work/waffle/gpu/forensic-audit/E58-architecture-review.md)
records this evidence and its limits.

## Recheck the published evidence

These commands validate logs or run host models; they do not access a phone:

```sh
python3 tools/check-waffle-gl-presentation.py work/waffle/runs/20261101T130419Z/kernel-final.log --fullsize
python3 tools/tests/waffle-fullsize-budget-host.py
python3 tools/tests/waffle-gl-log-host.py
```

Host-only no-op frontend traces are explicitly marked as architecture evidence,
not GPU execution. The [chronological debug log](../GPU_DEBUG_LOG.md) records
hypotheses, failures, controls and measured hardware results. Build images,
iOS assets and captured firmware are not distributed here.
