# Native audio DMA domain audit after A14

A14 establishes only no valid SMR match for audio1001/1081/1061. It does not establish all71 context banks free, writable or owned by XNU. Do not choose bank0 from absent audio matches.

Pinned OnePlus kernel e39bf7032e38c547d588372a11a5dd55eb714860, drivers/iommu/arm/arm-smmu/arm-smmu.c:
- arm_smmu_attach_dev at2045 initializes the domain then adds only this device master.
- __arm_smmu_alloc_cb at390 reuses a pinned bank only when its device stream entry is pinned; otherwise reserves from tracked bitmap. A14 has no such audio entry.
- Stage1 domain at1380 uses CBAR S1_TRANS_S2_BYPASS and allocation start num_s2_context_banks, not a fixed arbitrary CB number.
- arm_smmu_init_context_bank/arm_smmu_write_context_bank configure page tables, TCR/MAIR/TTBR and SCTLR before stream attachment.
- arm_smmu_domain_add_master at1880 binds its stream indexes to the allocated bank, default privilege, translation type; no audio-specific bank constant.
- arm_smmu_write_s2cr at1663 has implementation override; copying generic register literals before selecting the native implementation is unqualified.
- Initial driver reset and SMR-mask selftest are global operations and cannot be copied into a live UEFI display environment.

Live audio DT: coherent DMA; pool10000000+10000000, native SID maskf, stream1001/ignore-mask80 and1061/mask0. Buffer IOVA plus tagged lowSIDbits<<32 is DSP protocol address; raw physical address is not a replacement.

Next minimal experiment must remain read-only: inventory all valid stream routes and referenced CBs, NUMS2CB, and SCTLR of potential unreferenced banks; preserve global/stream configuration. Decode ambiguous/overlapping routes and enabled unreferenced banks as unavailable. This provides candidates, not proof of secure ownership; qualify native implementation/secure access before first writes. After ownership, use one bounded page table and unmapped guards, then DSP memory-map ACK, then period completion; no amp/iOS sink claims before actual PCM.

No new hardware run for audio during E109 GPU USB ownership. No DMA/CB/reset writes implemented by this audit.
