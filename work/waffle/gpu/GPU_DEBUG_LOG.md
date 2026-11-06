
## 2026-11-06 — U01 UniXNU ABI bootstrap PASS

Hypothesis: the pinned UniXNU ABI2 query can use the existing A750 context without changing hardware startup or breaking OpenGL. Vendored exact MIT header, added private PID1-only cdev query, refuse all unsupported operations. Full kernel and Darwin16.5 probe builds, ABI/layout/negative host tests and actual cdev regression passed. Hardware run 20261106T095030Z: ABI2 VA39 PA36 flags0, submit refused; FD750 GL checked256 wrong0 GL_error0; runner0 and Android confirmed. Hypothesis confirmed only for this protocol bootstrap. No Metal device, IOKit service, new FPS result or production UniXNU submission claimed.

Next experiment U02: isolate BO allocation/free against current context with generation handles and strict unsupported alignment/contiguous policies; prove no leaked or cross-owner handles before adding client-chosen IOVA. Upstream BoMap chooses IOVA; current backend assigns GPU VA. Do not pretend returning the existing VA implements that contract. Before normal clients: per-client state, real queue/fence lifetimes and IOKit memory tokens. Keep unsupported operations refused. No hardware retry of U01 without new changes.
