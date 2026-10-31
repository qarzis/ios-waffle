# OnePlus 12 GPU milestones

Status: October 31, 2026, OnePlus 12 PJD110 / SM8650 / Adreno 750.
The current verified implementation is the E15 source snapshot. These are
bounded kernel diagnostics, with Android reset and boot confirmation between
cold sessions. They do not establish GPU rendering of the iOS interface.

| Stage | Hardware result | Evidence |
| --- | --- | --- |
| E06-r2: physical clocks | GFX3D 231,000,200 Hz and GMU 260,001,136 Hz; measurement fields restored and full shutdown passed | [Result](../work/waffle/gpu/forensic-audit/E06-r2-result.json) |
| E07: LPAC mapping control | SID1/CB1, GMU SID5/CB3, 42 SQE-page data/instruction translations and GMU lifecycle passed; no CP RAW | [Result and runner classification limitation](../work/waffle/gpu/forensic-audit/E07-result.json) |
| E08: full CP_INIT | First native CP_INIT ACK under XNU: sequence 42, value 0, valid 1; successful unchanged reproduction after Android reset | [First result](../work/waffle/gpu/forensic-audit/E08-result.json), [repeat](../work/waffle/gpu/forensic-audit/E08-repeat-result.json) |
| E09: signed ZAP | PAS13 initialization, memory setup and signature authentication succeeded; native secure-mode switch ACK and TRUST=0 | [Result](../work/waffle/gpu/forensic-audit/E09-result.json) |
| E10: GPU memory write | GPU wrote four expected words; CPU checked all 4,096 buffer words with no unexpected changes | [Result](../work/waffle/gpu/forensic-audit/E10-result.json) |
| E11: indirect-buffer fetch, first attempt | Failed with an exact SMMU permission fault at the IB address; Android recovered. This attempt is retained as a failure | [Failure](../work/waffle/gpu/forensic-audit/E11-result.json) |
| E11-r2: scoped IB permission fix | AP_UNPRIV added only for the dedicated writable command BO. GPU fetched eight PM4 words and produced the correct memory result; all 4,096 words checked | [Result](../work/waffle/gpu/forensic-audit/E11-r2-result.json) |
| E12: owned submission session | Heap-owned session retained OOB/BO across initialization return; three IBs with distinct completion tokens and results passed | [Result](../work/waffle/gpu/forensic-audit/E12-result.json) |
| E13: GMU begin/finish owner | GMU register snapshots, live state and shutdown evidence survived begin return; default control and three-IB session passed | [Session](../work/waffle/gpu/forensic-audit/E13-result.json), [control](../work/waffle/gpu/forensic-audit/E13-control-result.json) |
| E14: GMU/TCM component | Live component returned to its SMMU parent; three IBs passed, then GMU stopped and the complete 32 KiB TCM snapshot was restored before owner release | [Session](../work/waffle/gpu/forensic-audit/E14-result.json), [control](../work/waffle/gpu/forensic-audit/E14-control-result.json) |
| E15: SMMU parent owner | Parent-owned tables, firmware plan, context snapshots and callback storage survived constructor return. Three distinct GPU results passed; child stopped before context detach and parent release | [Session](../work/waffle/gpu/forensic-audit/E15-result.json), [27 access checks / 42 LPAC checks control](../work/waffle/gpu/forensic-audit/E15-control-result.json) |

E15's complete kernel log is [preserved here](../work/waffle/runs/20261031T111210Z/kernel-final.log).
The [hardware runner report](../work/waffle/diagnostic-gpu-smmu-owner-e15/hardware-result-94.json)
records exit 0 and confirmed Android boot. The
[automatic-cycle report](../work/waffle/auto-runs/20261031T111146Z/result.json)
records automatic loader entry, no physical Boot iOS selection and no flash
operations. [Source hashes](../work/waffle/diagnostic-gpu-smmu-owner-e15/source-binding-audit.json)
and [container validation](../work/waffle/diagnostic-gpu-smmu-owner-e15/validation.json)
identify the tested artifacts. Build images, captured firmware and iOS assets
are not distributed with these reports.

## What changed

The earlier CP_INIT failures were passed after adding the missing LPAC mapping
and aperture, native GMU bank placement and invalidation for both ASIDs. That
prerequisite set resolved the failing CP_INIT test; the individual contributions
were not isolated and the historical reset reason was not decoded.

The new IB test exposed a separate, directly observed defect: its writable BO
was privileged-only, while the actual command fetch was unprivileged. The
scoped AP_UNPRIV fix removed that exact permission fault. Firmware and other
writable mappings were not broadly relaxed.

GMU/TCM and SMMU ownership was then separated from constructor stack locals.
The parent now retains tables, saved contexts and callback storage until the
child finishes. Failed or uncertain completion/teardown retains resources
instead of freeing pages still potentially used by hardware.

## Remaining boundary

- Board-clock, CX and AOP ownership still encloses the diagnostic session. The
  current AOP transaction holds a mutex around the callback and sends ACD off
  on exit; keeping the GPU alive by setting a flag would not provide a valid
  production lifetime.
- Dynamic userspace BO mappings, submission/fences and IRQ recovery are not
  implemented as a persistent waffle backend. Kernel-test completion tokens
  are not an advertised userspace fence API.
- Shader execution, a verified offscreen frame and GPU-backed iOS composition
  remain untested. The desktop continues to use Mesa softpipe. Metal is absent.
- Reopening the GPU after shutdown in the same boot is unverified. The verified
  lifecycle uses Android reset between cold sessions.

The existing RedwoodGPU IOUserClient, Darwin DRM shim, FD750 Mesa device
profile and IOSurface transport provide integration points; they do not by
themselves establish working hardware rendering on waffle. See the
[integration inventory](../work/waffle/gpu/forensic-audit/IOS-GPU-INTEGRATION.md)
and [chronological debug log](../GPU_DEBUG_LOG.md).
