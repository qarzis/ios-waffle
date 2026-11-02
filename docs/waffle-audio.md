# OnePlus 12 audio bring-up

The OnePlus 12 PJD110 passes bounded ADSP boot, GPR state query, APM graph
open/close and shutdown tests in XNU. **iOS audio playback is not implemented yet.**

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
| AudioReach/APM control graph | WR_SHMEM → RD_SHMEM open/close verified in A13; no PCM transfer |
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

## Graph transport and firmware ABI: A10–A13

The prototype connects WR_SHMEM to RD_SHMEM without a hardware endpoint or DMA.
The 344-byte GRAPH_OPEN and 64-byte GRAPH_CLOSE use the actual Linux v6.12
serializers at revision `adc218676eef25575469234709c2d87185ca223a` as a reference.
GPR parser sanitizer tests cover token/opcode correlation, malformed/stale
replies and the existing SPF query.

In A10/A11, the graph was not delivered: 64 small unused remote intents filled
the local cache, which discarded larger advertised intents. A11 measured
`ENOBUFS`, despite a granted request and adequate FIFO space. A12 retained larger
unused credits without increasing the table or replacing in-flight entries.
The graph then reached the DSP, which returned status `1`.

A13 changed exactly one 32-bit field: legacy PP capability `1` became the modern
generic-container type `0x0B001001`. The pinned AudioReach parser and container
factory establish this distinction; the actual firmware confirmed it. On
2026-11-02 at 20:33:37 UTC, OPEN/token2 and CLOSE/token3 both returned status `0`.
PAS1/PAS36 shutdown, normal XNU return and independent Android recovery passed.
No DMA, PCM, hardware endpoint or amplifier startup occurred.

Host tests compare the legacy and modern packets for exactly one changed word,
then compare modern serialization byte-for-byte. The container-factory test
uses `AudioReach/audioreach-engine` tree
`b38cb85a1a2543aa28aa1b27f4c380cafa5024bb`.

Native audio DMA uses Apps SMMU streams `0x1001/0x1061`; the redwood `0x1801`
mapping is inapplicable. Buffer mapping and completion events remain unimplemented.
