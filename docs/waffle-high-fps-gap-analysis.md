# Waffle: reaching 80–100 visible frames per second

Target: sustained active scrolling at 80–100 genuinely presented frames/s, without tearing or resprings. Callback frequency and GL submission count are not presentation FPS. Latest evidence is D16, 2026-11-04; the bounded test does not qualify sustained stability.

## Current measurements and hard limits

D16 active five-second intervals were 34,39,42,43,34fps. The user's desktop loaded but lag still felt present. Display-driver time fell from roughly19–22ms to7.7–9.4ms after private composition overlapped the previous pending flip. The final GPU context summary averaged19.2ms per GL frame,6.6ms of which was readback. The median of1,121 unique GPU-phase frame timing records was18.1ms. These partly overlapping stages cannot be added as an end-to-end latency. D16 closed10,340 commands/2,112 BOs, restored the original buffer after1,260 completed flips and returned Android. Its original strict collector exit1 is preserved.

Two separate existing limits prevent claiming80–100fps even if rendering becomes faster:

* `MiniIOMobileFramebuffer.cpp::refreshHz()` defaults Waffle to60Hz (`kFBRefreshHz`). The120Hz donor override requires `macan`, which is not the Waffle boot mode. This controls advertised mode timings and callback pacing. `waffle_vsync_phase.h::waffle_vsync_divider` divides the measured approximately120.8Hz TE source accordingly.
* `waffle_display_present_pending_wait()` requires at least two forward MDP frames before it permits the next A/B scanout copy/flip. With the observed approximately120.8Hz source this serial flip protocol has a ceiling near60.4fps. D16 overlaps CPU composition, but does not remove that cap.

The80–100fps target means10–12.5ms between visible frames. Raising callbacks alone would not overcome either the pending-flip guard or current GL costs. The target is not reached.

## Surface exchange audit

The existing Darwin Mesa code already defines an IOSurface import route. No new private iOS API needs to be invented:

1. `gl_osmesa.c::redwood_gl_surface_texture` passes the IOSurface ID to the locally patched `glEGLImageTargetTexture2DOES`.
2. `src/gallium/frontends/osmesa/osmesa.c::osmesa_st_get_egl_image` calls `osmesa_surface_resource` in the Darwin winsys. It requests surface metadata through `redwood_drm_surface`, then calls `resource_from_handle`.
3. `drm_shim.c::redwood_drm_surface` and `drmPrimeFDToHandle` use existing selector0x7e and the40-byte `redwood_drm_surface` ABI.
4. At D16 the Waffle cdev transport did not encode0x7e and its ioctl handler had no surface case. S01 now provides the opt-in metadata-only case, qualified against iOS values and a fullsize pixel control; importing remains explicitly unsupported. The donor `MacanGPU.cpp::surfaceBuffer` implements its own IOKit path; it is not called by the Waffle cdev.
5. Current `WaffleGPUMemory.cpp` owns newly allocated write-combined IOBufferMemoryDescriptors. Its destroy, page lookup and user mapping assume that ownership and cache mode. The imported IOSurface path would need a retained surface/backing descriptor, correct offset after its shared header, matching CPU cache policy, validated GPU pages and detach-before-release. Treating an existing cached IOSurface as a new WC BO would be incorrect.
6. GPU completion/source stability must remain explicit. `MiniIOSurface::drawn` currently integrates the donor fence path; imported Waffle surfaces need their own qualified completion/coherency boundary. Source D09 retirement fixed observed tearing and must not be bypassed.

D14 observed two750×1624 stride classes (3008 and3072 bytes), each using one GL read, with medians5.66/5.80ms. It found no multi-row fallback. Freedreno imported-resource layout additionally checks the exact supplied pitch. The later explicit-layout audit confirms64-byte pitch alignment for linear four-byte BGRA imports: both3008 and3072 meet that pitch rule. This does not yet qualify GPU mapping or cache coherency.

## Native display completion audit

Pinned OnePlus SM8650 source revision38d50357db2728300a61b6f757f2d3a09651c155 distinguishes events that must not be conflated:

* `sde_hw_intf.c` has INTF_MDP_FRAME_COUNT at0x0a4, regular frame count at0x0ac, autorefresh configuration at0x2b4 and raw autorefresh status at0x2c0, relative to the interface. Its frame-counter helper selects MDP count when autorefresh is enabled and the hardware supports it.
* `sde_encoder_phys_cmd.c` signals frame completion on PP transmission-done/CTL-done and tracks autorefresh-done separately. TE read-pointer and write-pointer callbacks also have separate meanings.
* `sde_hw_intf_poll_timeout_wr_ptr` observes the beginning of transfer; it is not a transmission-done contract.
* A latched, never-cleared interrupt status bit cannot by itself establish a new frame's completion. No interrupt-enable/clear/TE/START writes are authorized by this source inspection alone.

A safe faster flip contract must establish when the old physical scanout buffer is no longer read. The current two-frame guard is conservative evidence, not proof that a one-frame substitute is safe. Native completion/retirement and callback mode are the next architecture work; do not remove the guard merely to reach a counter target.

## Next independently verifiable steps

1. Preserve D16 as a bounded candidate and D13/D09 as previous working checkpoints; keep the rejected D15 image out of retries. Further iterations on logger overhead/large readback scratch are unsupported by the latest measurements.
2. Establish a display completion contract using the exact native event/status definitions and actual before/after observations, with no buffer-reuse guard change in that observation test. Do not accept stale status bits as fresh completion.
3. Qualify the higher-rate iOS mode separately once presentation can safely exceed60fps. Measure delivered frames, tears, frame-time tails and close/recovery, rather than only notification count.
4. Implement IOSurface exchange incrementally: metadata-only ABI first, then one retained surface and GPU mapping, controlled render/readback/coherency pixel proof, then normal compositor integration. Keep fallback for unsupported pitch/plane/client-memory types. This is larger than enabling selector0x7e or increasing the heap.
5. Judge80–100fps using an active scrolling interval and independent presentation evidence, with stutter and long-run stability still reported. No deadline or guaranteed final FPS follows from this audit.
