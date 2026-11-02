# OnePlus 12 audio bring-up

The OnePlus 12 PJD110 now passes a bounded ADSP firmware boot, GPR state query,
and shutdown test in XNU. **iOS audio playback is not implemented yet.**

## Verified on hardware

Test A09, 2026-11-02 13:56:00 UTC, authenticated the phone's original ADSP DTB
and firmware, received fresh SMP2P ready/handover state, opened GLINK/QRTR/GPR,
queried the audio framework's SPF state, and shut down both PAS instances.
XNU returned normally and Android boot completion was independently checked.

The literal result included:

```text
adsp: PAS 36 authenticated and running (adsp_dtb)
adsp: PAS 1 authenticated and running (adsp)
adsp: SMP2P ready seen state=0x2
adsp: SMP2P handover seen state=0x6
adsp: STAGE1 OK PAS=36,1 SMP2P=ready+handover GLINK=up QRTR node=5 services=13 GPR SPF=1 mode=6
adsp: PAS 1 shutdown=OK
adsp: PAS 36 shutdown=OK
adsp: WAFFLE DSP_BOOT result=1 stop_clean=1; GPR SPF state only, no PCM or amplifier startup
```

This is one qualified diagnostic lifecycle, not a playback or endurance test.
The observed QRTR node and service count are results, not fixed device constants.

## Changes

- Native firmware reservations and the IPCC base replace donor assumptions.
- The power plan resolves native ARC indices and eight BCM resources from the
  live command database, including SH1/SN3 and VCD commit boundaries.
- Bounded RPMh transactions check idle state, completion and register restoration.
  Diagnostic votes remain raised until Android takes ownership; shared votes are
  not cleared by the donor release sequence.
- Removable MMIO mappings use the matching XNU map/unmap interface.
- SCM continuations preserve the Qualcomm A6 context and use a two-second bound
  on Waffle instead of aborting after 100 interruptions. A09 needed 273
  interruptions for PAS shutdown. An unresolved continuation blocks dependent
  calls; unsupported WAITQ handling is refused rather than blindly resumed.

Host sanitizer checks exercise the actual firmware validator, command database
parser, native BCM encoding comparison, RPMh transaction, power wrapper, and SCM
continuation loop. Hardware results are recorded separately from build results.

## Remaining components

| Component | State |
|---|---|
| Signed firmware lifecycle | Verified in A09 |
| SMP2P, GLINK, QRTR and GPR control transport | Verified in A09 |
| AudioReach/APM PCM graph | Prototype; graph send blocked in GLINK |
| DSP PCM buffer mapping and period completion | Missing |
| Native speaker route and TFA amplifier initialization | Not ported |
| Connection to the iOS PCM sink | Missing |

The local HakiOS reference targets POCO X5 Pro/redwood and uses legacy APR,
ASM/ADM/AFE. Its playback commands and hardware addresses cannot be used directly
with Waffle's GPR firmware. Native OnePlus driver references are pinned to
`OnePlusOSS/android_kernel_oneplus_sm8650` revision
`e39bf7032e38c547d588372a11a5dd55eb714860` and the modules/device-tree repository
revision `38d50357db2728300a61b6f757f2d3a09651c155`.

Firmware and amplifier containers are obtained from the connected phone and are
not included in the repository.

## Graph prototype: A10/A11

The prototype connects WR_SHMEM to RD_SHMEM without a hardware endpoint or DMA.
Its 344-byte GRAPH_OPEN and 64-byte GRAPH_CLOSE packets compare byte-for-byte
with the actual Linux v6.12 AudioReach builders at revision
`adc218676eef25575469234709c2d87185ca223a`. GPR parser sanitizer tests cover
token/opcode correlation, malformed/stale replies and the existing SPF query.

In A10, DSP boot and SPF state succeeded, but `glink_send` failed before the graph
packet was published. No APM graph reply was received. The exact transport error
was not yet logged, so the graph format has not been blamed or changed. PAS
shutdown and return to Android succeeded; the graph test remains failed.

A11 adds intent-table overflow, remote-intent/request state, FIFO-room and send
error logging. Its XNU compilation passed; UEFI packaging was stopped by the user
and A11 has not been tested on the phone. This is diagnostic work in progress,
not PCM playback support. The next test should establish the transport failure
before changing allocation or packet format.

Native audio DMA uses Apps SMMU streams `0x1001/0x1061`; the redwood `0x1801`
mapping is inapplicable. Buffer mapping and completion events remain unimplemented.
