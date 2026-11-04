# D06 source consumer lease experiment

D05 establishes a data-ownership defect: sampled source pixels sometimes change across the actual CPU draw interval, including when the published seed is unchanged. It does not establish the only cause of panel tearing.

## Isolated change

In explicit `waffle_display_present=1` mode on Waffle, enqueue uses the existing `MiniIOSurfaceCopyForDisplay`, and after `show()` returns the presenter uses matching `MiniIOSurfaceDropForDisplay`. Ordinary framebuffer modes retain their prior behavior. Source observation stays enabled. No changes to source locking, SwapWait, queue size/retirement, frame copy, cache attributes, MMIO or wait thresholds.

The lease publishes shared useCount to pools that consult native IOSurfaceIsInUse. It does not stop a producer that ignores that count, and begins at enqueue rather than at producer allocation. Therefore absence of improvement rejects this specific lease as sufficient protection; it does not reject the observed race.

## Baseline and decision

D05: initial B copies 31.6–35.9 ms, A copies 2.3–2.8 ms. At logged 595 source reads there were 14 changed observations, 11 with sampled pixel changes. One more seed change was logged later. Measurements are sparse and workload-dependent, not universal rates.

Use the same 240-second GPU root/workload, Mesa749/E113, seven cores, buffered mode and hardware callbacks. Record first source useCount holds, final source counters, commit progress, allocation failure, GPU close, restoration evidence and Android return. Compare rates only at comparable source-read counts and workload stages. A reduced change rate supports pool-reuse involvement. A zero sampled rate alone does not establish correctness. Physical scrolling feedback remains necessary to qualify tearing.

## Native ABI evidence

iOS16.5 local framework export SwapWait 0x1af1c00f8 branches through object+1872. IOKit backend binding selects 0x1af1c0648. It calls selector6 with three scalar inputs, zero-extended w1, zero-extended w2, and zero. Timeout backend 0x1af1c4990 sends the same first two arguments and a converted double timeout. Argument meanings, flags and timeout units remain unproven. Another backend at0x1af1c42f0 returns success directly. No speculative wait implementation is included in D06.

Raw bounded disassembly: D06-swap-wait-disassembly.txt, D06-swap-backend-bindings.txt, D06-swap-backends.txt. These are derived from the local native cache; no web or undocumented invented API was used.
