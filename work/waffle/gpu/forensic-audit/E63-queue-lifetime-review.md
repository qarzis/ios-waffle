# Queue lifetime audit before another driver change

Current E60 kernel is unchanged while E62 runs. This audit records a separate
persistent-session gap, not the cause of any observed UI respring.

- Actual `waffle_gpu_drm.c` increments `drm_next_queue` to 32. CLOSE clears the
  live bit but never makes the issued ID available again.
- `waffle-queue-issued-limit-host.py` reproduces 32 NEW/CLOSE cycles with zero
  live queues and ENOSPC on NEW 33. No BO or GPU work is involved.
- E61 raw snapshots contain queue IDs 1, 2, 3 only. There is no evidence that
  E61 reached the queue limit. E62 remains the active hardware observation.

Selected design: retain the 32-live-queue bound and default queue 0, but encode
per-slot generations in the existing uint32 ID. Reuse only closed slots. Compare
exact generations on SUBMIT, WAIT, QUERY and CLOSE. Quarantine a slot before
uint32 wrap. All queues still share the existing synchronous submission path;
this does not add hardware scheduling, priorities or parallel contexts.

Temporary actual-cdev source prototype passes 100000 cycles, the 32-live bound,
queue33 submit/wait/query, stale queue1 refusal before GPU work, default0, and
all-slot generation exhaustion. Runtime has NOT been edited for this design.

After E62 and independent Android recovery: minimally wire the proven design,
run actual-source regression/full build, and make one focused RAM test where a
reused queue submits the already qualified guarded CP_MEM_WRITE packet. Require
its matching GPU completion, CPU reference values, refusal of the stale queue,
normal Mesa triangle and full parent cleanup. Do not infer hardware queue
semantics or success from compilation/the host fake.
