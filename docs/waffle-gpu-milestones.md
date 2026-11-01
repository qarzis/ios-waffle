# OnePlus 12 GPU progress

Adreno 750 now renders through actual Darwin Mesa and the existing EAGL hook
under XNU. A 750 × 1624 offscreen frame passed all 1,218,000 pixel checks and
was handed to the existing display driver through IOSurface.
**SpringBoard GPU acceleration and Metal are not working yet.**

| Verified test | Result | Evidence |
| --- | --- | --- |
| E21: compute shader | First verified shader execution | [Report](../work/waffle/gpu/forensic-audit/E21-result.json) |
| E29–E33: Mesa buffers and commands | GLSL compute, userspace submission, direct BO mappings and GPU completion tokens | [E33 report](../work/waffle/gpu/forensic-audit/E33-result.json) |
| E39: actual Mesa OpenGL | FD750 triangle; all 256 pixels correct | [Report](../work/waffle/gpu/forensic-audit/E39-result.json) |
| E40–E41: IOSurface and GL adapter | GPU result read into IOSurface and resolved by the display worker; actual EAGL GL adapter tested | [E41 report](../work/waffle/gpu/forensic-audit/E41-result.json) |
| E42: repeated GLES frames | 64 alternating frames; 16,384 correct pixels, 133 GPU completions, stable 25 BOs | [Report](../work/waffle/gpu/forensic-audit/E42-result.json) |
| E43: actual EAGL hook | Actual EAGLContext, private dispatch table and attachImage; hook performs IOSurface readback | [Report](../work/waffle/gpu/forensic-audit/E43-result.json) |
| E44: full logical display size | 750 × 1624, all 1,218,000 pixels correct; 205 GPU completions, 28 BOs, complete shutdown and Android recovery | [Report](../work/waffle/gpu/forensic-audit/E44-hardware-result.json), [kernel log](../work/waffle/runs/20261101T130419Z/kernel-final.log) |

## Current implementation

The controlled root-only backend provides owned BOs, persistent userspace
mappings, multiple logical queues on one serialized hardware context, bounded
command submission and GPU-written completion tokens. The SMMU table pool is
bounded at 64 tables. Full-size Mesa targets require a 5 MiB BO; the per-BO limit
is now 8 MiB, with the total GPU heap unchanged at 32 MiB and 32 BOs.

Presentation currently uses CPU readback from GPU-rendered resources into
IOSurface, followed by the existing CPU display path. The E44 probe only reads
and checks the surface; the real EAGL hook fills it. Display-worker logs prove
surface identity and geometry. They do not establish optical panel observation
or direct GPU scanout.

E43 initially failed because the hook prepends GLSL 300 while the test supplied
its own version directive. The successful retry uses versionless legacy input
and the unchanged hook. Explicit-version shader support remains a known limit.
The [failed report](../work/waffle/gpu/forensic-audit/E43-first-result.json) is retained.

## Remaining work

- Multiple real EAGL contexts and context switching are not yet qualified.
- Actual CoreAnimation/SpringBoard composition has not been tested through this backend.
  Normal waffle startup still explicitly selects Mesa softpipe.
- The backend remains a bounded diagnostic: one owning process, retained BO
  backing, queue limits and a 1,024-job session limit. E44's inverted row readback
  generated 205 submissions for one frame; continuous UI operation needs work.
- Shared IOSurface GPU imports, direct scanout, production lifetime/recovery and
  Metal remain unqualified or absent.

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
