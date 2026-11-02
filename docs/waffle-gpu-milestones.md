# OnePlus 12 GPU progress

Adreno 750 runs actual CoreAnimation/backboardd composition through Darwin Mesa.
The longest bounded RAM-only UI session completed its planned **600-second** window,
**1,670 GPU submissions**, and full GPU shutdown. It was mostly idle after
desktop startup, with periodic clock updates. This is not a continuous load or
FPS benchmark. Native captures show the desktop, icons and Calendar text.

Indefinite operation, broad app coverage and Metal remain unfinished. The normal
image still selects softpipe unless the isolated GPU test is enabled.

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
| E60: BO generations | Reclaimed descriptor slots reused; old handles refused; 9,000 real BO recycle cycles, last-buffer GPU writeback and 256 correct GL reference pixels | [Report](../work/waffle/gpu/forensic-audit/E60-recycle9000-result.json) |
| E61: inverted readback A/B | Same 750 × 1624 scene, all 1,218,000 pixels correct; readback 68,126 → 5,408 µs, 1,624 → 1 GL reads | [Comparison](../work/waffle/gpu/forensic-audit/E61-comparison.json) |
| E61: UI with qualified readback hook | 240 seconds, 17,525 GPU completions, clean stop; backboardd used the existing one-read path, so no UI FPS gain is established | [Report](../work/waffle/gpu/forensic-audit/E61-UI-result.json) |
| E62: 10-minute UI session | Planned 600-second stop, 1,670 GPU completions; all 1,349 BO lifetimes/generations validate, full cleanup and Android recovery | [Report](../work/waffle/gpu/forensic-audit/E62-result.json) |

| E63: queue generations | 100 queue cycles; stale queue refused, reused queue GPU writeback and 256 correct GL pixels; 9,000 BO cycles and full cleanup | [Report](../work/waffle/gpu/forensic-audit/E63-result.json) |

The readback timing is one controlled frame per policy, not an FPS benchmark.
E61 also logged GEM_NEW EINVAL without enough request details to establish why;
no allocation-budget or submission failure was logged. Original outer runner
failures due to lost rolling-console startup evidence remain recorded.

The E60/E62 outer runner exits remain 1: final rolling logs miss startup/BO
markers. E62's separate literal-snapshot check validates every BO lifetime and
generation, but its full UI check lacks the display-worker surface log. GOP
captures are retained locally; exact submitted-surface correlation is unverified.

## Current implementation

One owning backboardd process uses synchronous GPU submissions. Large requests
are partitioned in order into complete-root windows. The physical BO budget is
192 MiB, the per-BO bound is 8 MiB, and 8,192 descriptor records are available.
Virtual placement spans 256 MiB;
physical residency remains limited to 192 MiB.
Closed BOs are revoked before release. Descriptor slots are reused with
32-bit generation handles; exhausted generations are quarantined before wrap. GPU fences remain monotonic; serialized
HFI tags cycle independently of them. The former 1,024-submission diagnostic cap
has been removed and crossed on hardware.

Presentation still reads GPU-rendered data into IOSurface and uses the existing
CPU display path. This is not direct GPU scanout. Other processes can still use
softpipe. A composite UI capture is not a pixel-reference test of every app.

## Remaining work

- Extend reference-pixel coverage of the enlarged working set. E77/E78 exercised
  residency above 128 MiB, but their UI captures are not full pixel-reference tests.
- Qualify sustained interactive load after the focused queue-generation test.
- Qualify sustained interactive load and persistent mode before removing timers.
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

## Performance experiments

Two candidate changes were rejected and removed from the active runtime. In the
same 240-frame, 750 × 1624 scene (all 292,320,000 reference pixels correct per
policy), RAM staging increased median frame-processing time from 4.110 to
5.174 ms. Wider private-buffer accesses measured 4.144 ms against the profiled
scalar baseline at 4.103 ms, with no qualified gain. These are offscreen timings,
not panel FPS. The verified scalar path is restored; queue/BO fixes remain.

[Readback comparison](../work/waffle/gpu/forensic-audit/E64-comparison.json),
[submit comparison](../work/waffle/gpu/forensic-audit/E66-comparison.json).

## November 2: CPU, flashlight and allocation pressure

Four and seven XNU CPUs passed isolated startup and concurrency checks. The
resident USB loader retains one physical core. GPU UI runs now request seven
CPUs by default. This does not establish full eight-core handoff.

The Waffle SPMI v7 flashlight path passed a bounded 100 mA/channel pulse and
Control Center on/off was confirmed on the phone. Shutdown readbacks confirm
the module is dark. Alert Slider modes and the displaced volume HUD remain
unresolved.

Mesa now has an opt-in, single retry after purging unused BO caches. An earlier
version deadlocked by holding the table lock while destructors took that lock;
that candidate was rejected. Cache reclamation alone could not accommodate
128 MiB of live BOs. The physical budget is now 192 MiB with the same 8,192
descriptor slots, 256 MiB VA range and 8 MiB per-BO limit. E77 completed its
240-second GPU phase with 61,993 completions and 10,462 lifetime BOs, no logged
allocation refusal or SIGSEGV, and a full context close. Its strict fence
collector still reports missing/discontinuous events; original failures remain
recorded. This is a bounded observation, not indefinite stability or an FPS
claim.

The bundled iOS 16 collection is exposed on the 375×812@2x canvas. Automatic
selection is under hardware test; gallery availability alone does not prove
the requested wallpaper is applied.

E78 subsequently exhausted the full 192 MiB during interactive UI and backboardd
crashed after 9,787 completions. Seven online CPUs and actual parallel execution
were observed in this same run. The user reported GPU-phase stripes; the saved
app-switcher capture also shows horizontal discontinuities. Their cause remains
unproven. Further heap increases are stopped pending a live-BO ownership and
presentation review. [Failure report](../work/waffle/gpu/forensic-audit/E78-result.json),
[architecture review](../work/waffle/gpu/forensic-audit/E78-architecture-review.md).

E79 confirmed seven online CPUs alongside GPU composition (3.7 CPU-time/wall-time
ratio in the short concurrency probe), 1,140 GPU completions and full context
close. The requested iOS16 wallpaper is visible in native captures. Its automatic
configuration creation succeeded, but selection returned NSCocoaErrorDomain -1.
The wallpaper was already visible before that attempt, so automatic default
selection remains unverified. Original runner exit1 is retained.
[Report](../work/waffle/gpu/forensic-audit/E79-result.json).

## Alert Slider

The MXM1120 Hall pair now drives native iOS modes: top enables Do Not Disturb
with its system moon banner, middle mutes the ringer and enables vibrate-in-silent,
and bottom restores ring mode. Leaving the top releases only the assertion
created by this driver. The Focus Off banner is suppressed so it cannot cover
Silent Mode; pending old banners are cancelled on physical changes. Native
Silent Mode On/Off labels and all three modes were confirmed on the phone.

The driver uses stock calibration, native RPMh power resources, verified
volatile gain/measurement settings, debounced samples and a power lock shared
with touch. Focus uses the HID client allowed by the original SpringBoard
entitlements. Physical vibration and speaker output remain unsupported.

[E95 report](../work/waffle/gpu/forensic-audit/E95-result.json),
[state and banner journal](../work/waffle/gpu/forensic-audit/E95-slider-components.log).
Android recovery was independently confirmed. Original GPU runner exit1 is
retained; these peripheral checks do not establish overall GPU stability.

## Current allocation and presentation investigation — November 2

- A fully offscreen layer could enter filtering with an empty clipped interval
  and read outside memory. The actual layer/row code reproduces the fault under
  ASan; the clipping guard passes 40 independent pixel/canary cases.
- Native Mesa requests of 10 and 12 MiB were rejected by the old 8 MiB object
  limit while aggregate residency still had room. The object bound now follows
  the existing 192 MiB heap; physical residency, 256 MiB VA, 8,192 slots and
  160 translation tables are unchanged. Host tests cover every PTE of a single
  192 MiB object, full-budget refusal, revocation and reuse.
- E100 completed 20,251 GPU commands and full context cleanup. Its original
  strict runner failure remains recorded because the rolling-log collector
  lacked complete Dynamic BO proof. This is not an end-to-end UI pass.
- A display IOSurface usage lease is implemented as a candidate, disabled by
  default. Hardware VSync/page flipping, animation correctness and an FPS gain
  remain unqualified. The optional native application-launch probe is also
  experimental; its first system launch request was declined.

Desktop wallpaper improvement does not establish that wallpaper previews or
app-opening animations are fixed. Raw loader screenshots read live scanout,
so a capture during movement can itself combine multiple frames. Completed
rolling logs can be packed with `tools/archive-waffle-run-logs.py`; every archive
member is hash-verified before loose snapshots are removed. Final logs and
results are retained.
