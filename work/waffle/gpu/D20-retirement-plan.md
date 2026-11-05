# Next display retirement experiment (not implemented)

D19C proves three fresh masked PP0_DONE reassertions after a verified clear, with new source addresses and MDP delta1. The old two-frame guard is unchanged. Full GPU workload and teardown passed; overall runner remains failed because separate multicore records were absent.

1. Most supported hypothesis: an additional unconditional frame wait costs latency after actual transfer completion. Qualification still requires proving the fresh PP0 event covers both visible halves and that the previous source is no longer consumed. Native route, latch and transfer semantics must agree before changing retirement.
2. Alternative: the recurring PP0 event is real but not a sufficient source-reuse boundary. Falsifier for early release: continued references to the old source or either half after the event, or uncertainty about the selected output path. Retain the old guard in that case.
3. Separate throughput limit: full-frame output readback and CPU copy remain necessary. Even a qualified earlier retirement need not increase active-scroll FPS; compare measured GPU/readback/copy/wait stages under the same scrolling workload.

First next action is source-contract review against pinned native command-mode PP_DONE handler and pingpong routing. Then a bounded opt-in experiment with unchanged fallback and automatic restore, never a global early-release switch. Required measurements: both-half correctness, original front restored, strict BO lifetime proof, active-scroll frame intervals, user-visible tearing. Sparse idle measurements cannot establish 80–100 FPS. No identical failed hardware reruns merely to recollect logs.
