# D01: qualify the inherited display DMA path before a second scanout buffer

Confirmed source: running Android-captured DT splash reservation is d5100000+02b00000. Waffle UEFI MemoryMapLib marks the identical range reserved and SimpleFbDxe uses its physical base as GOP FrameBufferBase. V01/V02 actual DPU SSPP0/1 share d5100000, stride5760,720x3168 per split. This equality does not by itself prove the rest of the reservation is mapped for DMA.

DT nonsecure display master uses AppsSMMU phandle52 SID1c00/ignore-mask2, therefore candidate hardware streams1c00 and1c02; secure SID1c01 is a separate master and must not be changed. Android IOVA pools exclude the splash interval and earlymap is enabled. The Android configuration does not prove the inherited UEFI routing state.

At5760*3168=18247680bytes, a second64KiB-aligned frame could fit atd6270000; this is address arithmetic only, not mapping or ownership qualification. No second-buffer writes, DPU flush/start/IRQ ack, SMMU attach or display modeset performed.

Maximum three mapping hypotheses: (1) display streams bypass SMMU; (2) display streams use an existing identity mapping covering the splash reservation; (3) only the current frame is mapped. The first experiment should only read AppsSMMU global control, native-validated stream matches and referenced context configuration. Absent/ambiguous/secure/disabled unknown state is unqualified. If translated, validate native table format before any bounded page-table reads; never substitute a guessed physical address for a DPU address.

Once DMA range ownership and shadow-latch/flush/start/retire order are proven, compose into the inactive buffer and switch both split SSPPs as one qualified display commit. The current CPU writes directly to active scanout; TE callbacks alone cannot make that atomic. User observes scrolling stripes disappear when stopped, consistent with transient frame incoherence.
