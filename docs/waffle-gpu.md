# OnePlus 12 GPU port

This is an unfinished hardware port of the macan graphics stack to SM8650.
The current build boots GMU firmware and initializes HFI, **not GPU acceleration**.
The working CPU-rendered iOS, touchscreen, buttons and serial package is preserved.

The latest completed control is NATIVE93 (2026-10-31): verified UEFI NPA
clients held CX/MX256, GMU booted using PLL1 at1250MHz /2 (625MHz), then changed
toPLL1 520MHz /2 (260MHz) before GPU preparation. The post-prepare HFI query
passed; GMU slumber, GX collapse, CM3 reset, root detachment, PLL scalar restore
and clock rollback passed. Android boot completion was independently verified.
No CP RAW command was submitted in93. Isolated PLL92 had already passed both
rates and restoration. Full CP_INIT94 was hardware tested and failed with
USB/900e and no saved CP ACK. Standard diagnostic collection/reset completed
and Android recovery was confirmed. All 88 saved kernel logs stop at RAW
checkpoints 0–3; the missing next marker does not prove publication never ran.

The current workflow is forensic audit, with production source changes and
further RAW probes paused. See `GPU_DEBUG_LOG.md` and
`work/waffle/gpu/forensic-audit/AUDIT.md` for evidence, architecture gaps,
rejected explanations and the proposed first discriminating no-RAW experiment.

SEC_STALL91 previously failed with USB/900e and no CP ACK or captured SMMU
fault atGMU200MHz. Native captures established the625->260 sequence now
validated by93; this does not yet establish CP execution or acceleration.
See `work/waffle/gpu/RESUME.md` for the current test and recovery record.

Earlier control TG81 passed GPU preparation, HFI query,
full collapse and return to Android passed with the native TCR `0xb5193519`.
Live Android CB0 capture exposed a port bug: copying the lower TCR half left
TG1=0, while 4KB TTBR1 tables require TG1=2. The native allocator selects a
different granule code for TTBR1; the port and its previous host test both
missed that step. The corrected test fails against the old port code and
passes after the fix. THREAD82, the isolated thread-control test with corrected TG1, still failed
with USB/900e and no CP ACK; the correction alone does not resolve the failure.
The phone returned to Android after the standard diagnostic collection/reset.
See `work/waffle/gpu/RESUME.md` for the current hardware and recovery record.

## Hardware and source evidence

The recorded PJD110 live FDT identifies Adreno750v2 as chip ID `0x43051401`,
compatible `qcom,adreno-gpu-gen7-9-1`. The two stock base trees also contain
revision 0 (`0x43051400`, Gen7.9.0). These IDs are Qualcomm's vendor identifiers,
not a hex encoding of the marketing number 750.

The macan donor targets Adreno829 / Gen8 with `gen80900` firmware. Its
register constants, firmware and initialization sequence cannot be reused as-is.
The existing Mesa26.3 Freedreno device table recognizes `0x43051401` as FD750;
this establishes user-space device recognition, not a working XNU hardware driver.

| Block | Address | Size |
| --- | --- | --- |
| GCC | `0x00100000` | `0x1f4200` |
| GPUCC | `0x03d90000` | `0x9800` |
| GPU | `0x03d00000` | `0x40000` |
| GMU | `0x03d68000` | `0x37000` |
| RSCC | `0x03d50000` | `0x10000` |
| CX_MISC | `0x03d9e000` | `0x2000` |
| GPU SMMU | `0x03da0000` | `0x40000` |

The GMU node's **name** ends in `3d69000`, but its actual `reg` starts at
`0x03d68000`. Gen7 register definitions are DWORD indices relative to the GPU
base. The Gen8 offsets in macan differ: for example Gen7 CX counter is
`0x1f880`, not `0x1f840`, and the power-clock status is `0x1f8d0`, not `0x1f7e8`.
SM8650 CX GDSCR/HW_CTRL are GPUCC `0x9108/0x9168`, whereas macan uses
`0x9080/0x9094`. Keep these differences explicit.

Source snapshots and checksums are in `work/waffle/gpu/vendor/`:

- OnePlus modules/device-tree commit `c951f93ec63fbee49d468ee2f9d93ac0e807da67`:
  `adreno-gpulist.h`, `adreno_gen7*`, `gen7_reg.h`, `pineapple*-gpu*.dtsi`.
- OnePlus kernel `drivers/clk/qcom/{gcc,gpucc}-pineapple.c`; exact revision in
  `oneplus-kernel-tree-revision.txt`.
- Linux v6.12 `gcc-sm8650.c`, `gpucc-sm8650.c`, `a6xx_gpu.c`, `a6xx_gmu.c`;
  URLs and hashes in `linux-provenance.json`.

`tools/check-waffle-gpu.py` checks the chip, compatibles and mapped register
ranges against all three DTBs. `kernel/files/bsd/sys/waffle_gpu.h` contains the
initial board profile. No memory reservations are borrowed from macan.

## Current diagnostic stages

`waffle_adreno_init()` runs only with `waffle=1 waffle_gpu=N` and returns to
the loader before starting touch and iOS. Without this explicit boot argument,
the board continues to use the existing software graphics path.

1. Read the GCC GPU configuration-bus and memory-bus clock status. No writes.
2. Force the configuration-bus branch on with hardware gating disabled, wait
   at most 10ms, and inspect GPUCC clock/power status. Restore both enable/gating bits
   before returning. If the bus stays halted, do not access GPUCC.
3. Repeat stage 2, deassert CX collapse, wait up to 50ms for power-on and
   restore the collapse request. If CX is already powered, leave its power
   control unchanged. Do not touch GX, GMU clocks, resets or SMMU mappings.
4. With CX powered, vote the existing GPLL0 parent and configure the hub at
   200MHz and GMU at the XO reference. Enable the required CX clock branches,
   check readiness, then read GMU reset/firmware status and sample its AO
   counter. Restore branches, clock sources and votes before collapsing CX.
   A failed clock handshake prevents GMU register reads.
5. Enable the GPU memory/AXI and SMMU clock branches, inspect SMMU ID/layout,
   the first six stream entries and two context banks. Refuse context reads
   when the reported layout exceeds the DT range. No SMMU writes.
6. Add the vendor SNOC clock vote and read the GPU QTB500 state at `0x03de8000`.
7. Borrow disabled context1 and an unused stream entry only after checking
   ownership. Allocate and flush three table pages plus a target page. Run
   the vendor ECATS protocol for SID5/IOVA `0x60010000`, compare its physical
   result to the target allocation, then restore context, stream and QTB
   controls and invalidate the test ASID before freeing pages. Refuse a busy
   QTB, an enabled/faulted context or a conflicting stream route. No firmware
   or GPU execution is started. A TLB-sync failure retains allocated pages
   and requires an Android reboot before another test.
8. Parse the phone's uncompressed GMU firmware, allocate its external memory
   regions and populate a general three-level page table. Verify the first
   and last page of each region through ECATS, then write and read back the
   TCM payloads with CM3 still in reset. Back up all touched TCM words first,
   restore them afterwards and verify restoration before freeing the backup.
9. Add the vendor 17-queue HFI table and log buffers, configure Gen7 boot
   registers and release CM3 reset. Poll readiness for at most 2 seconds;
   then assert reset, drain GBIF/QTB, restore all 32KB TCM and release the
   mappings. A stop failure retains memory and requires an Android reboot.

10. After firmware readiness, initialize HFI through CTRL_INIT and poll STATUS
    bit0 for at most100ms. No START, DCVS or GPU draw command. Hardware pass
    `20261024T130240Z`: STATUS1, clean reset/drain/TCM restore and normal return.
11. Send read-only GET_VALUE property122 (GMU_AB_VOTE), require matching ACK
    sequence/header. Shared cmd/message queues use a WC alias of the first16KB
    HFI page, with ordered index publication and bounded packet validation.
    Host ring boundary/overflow/malformed-index tests pass. Hardware passes
    `20261024T130936Z` and repeat `20261024T131023Z`: matching ACK/value1,
    normal return and full shutdown.

12. Submit a52-word GPU_PERF table generated from live Android frequencies,
    matching stockDT voltage levels and captured cmd-db ARC levels. HFI2.6.1
    reported; TABLE ACK0 in `20261024T131451Z`, full cleanup. No START/DCVS.
13. Submit a160-word BW_VOTE_TBL: DDR/CNOC levels from liveDT, BCM addresses
    and units from captured cmd-db; native Gen7.9.1 ACV policy. Hardware ACK0 in `20261024T131902Z`, clean shutdown.

The first stage11 run `20261024T130457Z` timed out and panicked on alias unmap.
Use `ml_io_map_unmappable(...,VM_WIMG_WCOMB)` for removable aliases;
`ml_io_map_wcomb` creates permanent mappings. Stage11+ SMMU MAIR0 is normalNC44,
matching vendor GMU mappings without IOMMU_CACHE. With these fixes the queue
is consumed and the ACK arrives. Preserve the failed log as failure evidence.

Stage9 passed `20261024T084055Z`: FW_INIT100, full shutdown verified.
Stages 1/2 do not power CX/GX. Stage 3 temporarily requests CX power only.
Stages 1 through 6 do not change SMMU translation registers. Stage 7 temporarily
configures an unused context and stream route for a translation test.
Stages8 onward load firmware; stages9 onward execute GMU firmware. None submits
GPU draw commands, calls TrustZone, accesses flash or registers a functioning
`RedwoodGPU` service.
Stage 1 returned normally on hardware (`20261024T072847Z`): both GCC branches
read `0x80000003`. The first stage-2 version (`20261024T073034Z`) timed out
with those same values and returned normally without accessing GPUCC. The next
version temporarily clears the CBCR hardware gating bit before polling; that
change passed on hardware in `20261024T073356Z`: GPUCC registers were read and
CFG_AHB controls restored to 3; returned14963 0. CX GDSCR=`0022f801`,
HW_CTRL=`2800010a`, GX GDSCR=`00888801` (domains off).
Stage 3 passed in `20261024T073930Z`: CX power ON (`GDSCR=f822f800`,
`HW_CTRL=80000202`), collapse restored and power status OFF, then CFG_AHB
controls restored; returned15315 0.
Stage 4 passed in `20261024T074443Z`: clock branches ready,
CM3_SYSRESET=1, FW_INIT_RESULT=0, AO counter delta21692 in a requested1000us
interval. All clock controls restored, CX power OFF, CFG_AHB controls3;
returned16134 0. The GMU processor remains in reset.
Stage 5 passed in `20261024T074935Z`, returned20694 0. SMMU IDR0=`4c017e18`,
IDR1=`40000016`, IDR2=`5511`: 4KB register pages, 32 global pages, 22 context
banks, 24 stream entries. First six SMRs invalid, S2CR fault, CB0/CB1 disabled,
no fault status. The disabled banks' other registers contain uninitialized
values; do not interpret them as valid existing page tables.
IDR0.ATOSNS is set, so standard ATS1PR is unavailable. Use the vendor QTB500
ECATS mechanism, not standard ATOS.
Stage 6 passed in `20261024T080312Z`: SWID=`003567e0`, QTB idle.
The first stage-7 test translated correctly but panicked during cleanup:
writing reset CBAR type0 back requests unsupported stage2 (IDR0.S2TS=0).
The corrected code leaves that disabled/unassigned bank in supported stage1
mode and excludes reserved FSR bits from fault checks. Full stage-7 tests
passed twice (`20261024T080758Z`, `20261024T080817Z`), including TLB sync,
QTB/clock cleanup and CX power OFF.
Stage 8 passed in `20261024T082321Z`: all six external regions translated
correctly, all three TCM payloads matched and restoration passed.
Stage 9 passed in `20261024T084055Z`: FW_INIT=`100`, ready=1, IRQ status0,
GX stayed off. CM3 reset, bus draining, full TCM restoration, TLB/page cleanup
and CX power OFF all completed. HFI control/command exchange and 3D rendering
have not been implemented or tested yet.
A hardware abort
can interrupt restoration; reboot Android before retrying after an abort.

The loader accepts stages 1 through 9 only in a userland-enabled diagnostic image.
Legacy `macan_gpu=`, generic `gpu=1`, and stage 10 onward remain refused.

## Next hardware work

First capture Android metadata and firmware with the phone connected and root
read access available:

```bash
python3 tools/capture-waffle-gpu.py --output work/waffle/gpu/android-capture
```

This reads files only. It does not mount debugfs, change clock/power settings,
reboot or flash. Unavailable diagnostic files are recorded in the manifest.
The vendor firmware names are `gmu_gen70900.bin`, `gen70900_sqe.fw`,
`gen70900_aqe.fw`, and `gen70900_zap.mbn` (or its split MDT form). Take these
from this phone; do not use donor firmware.

After RAM-booting the matching diagnostic image and selecting Boot iOS:

```bash
python3 scripts/run_waffle_ios.py \
  --kernel work/waffle/diagnostic-gpu/kernel \
  --root work/waffle/posterboard/client-gl-images/root.packfs \
  --seconds 30 --gpu-probe 1
```

Start with stage 1, inspect the saved log and normal loader return, then run
stage 2 with `--reuse-system` in the same EFI session. No unattended boot is queued.

For early probes a minimal system avoids uploading all of iOS. The probe runs
after root/devfs mount and returns before userspace. An image containing only
directories `dev`, `tmp`, `private/var` was hardware tested in `20261024T073914Z`:

```bash
mkdir -p work/waffle/gpu/probe-system/{dev,tmp,private/var}
python3 tools/mkpackfs.py work/waffle/gpu/probe-system \
  -b 4096 -o work/waffle/gpu/probe-system.packfs
```

Pass that 12KB file as **both** `--root` and `--system`, together with an
explicit `--gpu-probe`. It cannot boot iOS. Do not reuse it as the system
image for an ordinary iOS session.

The next implementation steps depend on those results: RPMh power votes using
captured resources/levels; CX and clock startup; GMU firmware allocation and
SMMU mapping; Gen7 HFI boot; authenticated zap loading; SQE/AQE initialization;
a bounded fence write; then a rendered image. Each needs a reverse shutdown path
before repeating runs. Only then connect the existing `MacanGPU.cpp`/msm-shaped
allocation and submission interface to this backend, and enable Freedreno in
CoreAnimation. Metal translation is a separate layer and cannot replace that
hardware bring-up.

## Latest paused checkpoint (2026-10-24)

Stages14..20 added powerfirmware start, RSC/PDC setup, native slumber,
SCM secure-register initialization, loweststockfrequency request, realGXon/off,
GPUcontext0/SID0 translation, and SQE/AQEbase write/read/restore withCPdisabled.
Last fully verified artifact `work/waffle/diagnostic-gpu-ucode2`, run140858Z.
Stage21 attempted minimallegacyCP ring initialization butFAILED: USBlost,
Qualcomm900e/black screen, nofinalkernel log. User force-restarted and confirmed
Androidboot. CPexecution/rendering/FPSgain remainUNPROVEN. Explicitlypaused
atuserrequest. See work/waffle/gpu/RESUME.md before any resumedwork.

## 2026-10-24 20:05 UTC — stage22 PASS

Explicit user resume; Android boot_completed confirmed over ADB. No old pstore.
Built/validated diagnostic-gpu-cp-setup; all ASan/UBSan host tests passed.
RAM-only run20261024T200519Z returned40140 0. All14APRIV/ring/SQE/AQE
setup/readback/restore verified with CP0, noSQEcontrol/WPTRwrites. Native
RSCsleepcomplete1, GXoff, context0restoredTLBdone/faults0, RAMrelease passed.
This narrows prior21fatal to after setup (enable/submit/poll/halt not separated).
Stage23 candidate diagnostic-gpu-cp-enable now isolates SQEenable1 withWPTR0,
100usdelay, readback thenhalt3 whilevalidbuffersremainmappeduntilGXoff.
No command packets submitted; not yet hardwaretested. MandatoryAndroidreset
between nativeASLEEP tests. Originalworking20/failing21/working22 preserved.

## 2026-10-24 20:07 UTC — stage23 FAILED, Android recovery confirmed

RAM run20261024T200719Z (diagnostic-gpu-cp-enable) ACKedrun0 thenUSBread
No suchdevice; oemlogtimedout15s, nofinalkernel log. Deviceenumerated
05c6:900eQUSB_BULK. Userforcedrestart, Androidsys.boot_completed=1confirmed
viaADB; ro.boot.bootreason/sys.boot.reason=bootloader, pstoreempty. Saved
recovery/dmesg/debugfslisting inrunfolder. NO successfulCPenable evidence.
Stage23neverwritesWPTR: failure narrowed toenable/readback/halt path,
notCP_ME_INITsubmission. No exactfaultinstructionknown.

NativeGen7.9.1 selectsgen7_9_0_hwsched_gpudev, notlegacyringstart; native
CPinitialization usesHFI_ISSUE_CMD_RAW afterHWSCHEDSTART allocation/feature
handshake. Newcandidate24 diagnostic-gpu-hwsched-features enablesHWSCHED1,
KPROF16beforeCORE_FW_START, disablesPREEMPTION2/LPAC24/DMS27,enablesAQE29.
AllCPUCP-control/WPTRwrites are bypassed at24; onlyverifiedstage20base
transaction underOOBGPU. Seq6..12features/core,13minvote,14slumber.
Candidatebuilding, untested. Originalartifact20/21/22/23 preserved.
CapturedAndroidglobals atgpu/android-hwsched-globals.txt show5GMURBringbuffers,
SMMUinfo,14.6MBprivnonsecure+secureCSW, AQE16KB; addressesmaskedbykernel.
Debugfsmountedonlyforreadandunmountedaftereachcapture. NoAndroidsettingschanged.


# Current checkpoint — 2026-10-24 20:14 UTC (resumed, not paused)

User explicitly resumed. No build/test queued after the following completed
checks. No flash/erase. Stable userland/touch/buttons/serial packages untouched.
No GPUdraw/Metal/FPS improvement achieved yet; do not claim CP initialized.

## Completed hardware results this turn

- Stage22 PASS run20261024T200519Z, returned40140 0,
  diagnostic-gpu-cp-setup:14APRIV/ring/ucode registers setup/readback/reverse
  restore, CP0, noSQEcontrol/WPTRwrites, fullGXcollapse/nativeRSCsleep,
  context0TLBdone/faults0. This is the safe isolatedsetup baseline.
- Stage23 FAILED run20261024T200719Z, diagnostic-gpu-cp-enable:
  onlySQEenable1,100us,registerreadback,halt3; WPTRneverwritten. USBdisappeared,
  oemlogtimeout15s,05c6:900e, no kernel log. Narrows failure to enable/read/halt,
  NOT command submission. Userforcedrestart; Androidboot_completed1 confirmed.
  Recoverypstoreempty; bootreasonbootloader; dmesg/debugfslists savedinrun.
  Never rerun21/23 unchanged. Exact failing instruction remains unknown.
- Stage24 PASS run20261024T201155Z, returned42118 0,
  diagnostic-gpu-hwsched-features: nativeHWSCHED1/KPROF16ON beforeCORE_FW_START;
  PREEMPTION2/LPAC24/DMS27OFF,AQE29ON. AllACK0seq6..12; minvote13,
  stage20base-onlytransaction withCPdisabled, slumber14/nativeRSCsleep,
  GXoff/context0fault0/fullcleanup. StillNOHWSCHEDSTARTallocationhere.
- Stage25 PASS run20261024T201430Z, returned40685 0,
  diagnostic-gpu-hwsched-request: features as24, then START10seq13. Captured
  first F2H_MEM_ALLOC:11words hdr00c00b14 version1, flags0000033f,
  kind2(SCRATCH),hosthandle0,gmu_handle2,gpu/gmuVA0,size4096,alignment0.
  NOreply sent, noMINIMUM_DCVS/OOB/GX/CPenable. CM3reset,GBIF/QTBdrain,
  GXstatus3/GDSCR888801, RSC/PDCconfigurationrestored(awake,notnativeASLEEP),
  TCMrestored,context0TLBdonefault0, fullRAMrelease verified. ReturnAndroid
  requested after completion (see session final/recovery file for confirmation).

## Current code

Policy/runner/kernel stages1..25. Stages21..23 ONLY uselegacyCPprobe;
24 usesbase-onlytransaction;25 skipsGPUvote/OOB/slumber entirely and resets
CM3 whilewaitingforfirstallocationreply. RestoresawakeRSC/PDCconfiguration.
New waffle_hfi_mem_request_decode in sys/waffle_hfi.h validatesexact10/11word
v0/v1 packets, ID/type/length, flags/kind/size/alignmentbounds. It parsesonly,
allocatesnothing. New actualsourcehosttest tools/tests/waffle-hwsched-host.py
covers truncated/version/align/size/kind/flags, timeout, corruptqueue and
NOallocationreply/CPaccess. Includedinbuilder/artifactsources. AllASan/UBSan
hosttests andfullkernel/EFI/containerstructuralvalidation passed for25.



# Current GPU port checkpoint — 24 October 2026, 20:20 UTC

The user explicitly resumed work. This is a saved progress point, not a user-requested pause.
No build, boot or test is queued. Phone returned to Android; ADB serial `1c62e9aa`
reports `sys.boot_completed=1`. No flash or erase. Stable iOS userland packages remain intact.
Hardware GPU rendering, Metal acceleration and an FPS gain have NOT been achieved.

## Latest result: HWSCHED memory handshake, incomplete

Artifact: `work/waffle/diagnostic-gpu-hwsched-alloc/`, stage26.
Run: `20261024T202012Z`; kernel returned `51678 0`, runner correctly FAILED the
probe because START never completed. This was a controlled refusal, not a crash.
Seven allocation replies were accepted before the firmware requested protected RAM:

| Kind | Handle | Flags | Requested bytes |
| --- | --- | --- | --- |
| Scratch (2) | 2 | 0x33f | 4096 |
| Kernel profiling (14) | 14 | 0x33f | 4096 |
| User profiling (15) | 15 | 0x339 | 4096 |
| Command buffer (16) | 16 | 0x178 | 32768 |
| Ringbuffer (1) | 26 | 0x37b | 32768 |
| SMMU info (3) | 3 | 0x17f | 24 |
| Nonsecure context save (4) | 4 | 0x37f | 3657728 |
| **Secure context save (5), refused** | 5 | **0x1007** | **3657728** |

A 32 MiB normal-NC arena at VA `0x61000000` was allocated, zeroed, cache-cleaned
and mapped before starting CM3. Seven replies used 3,739,648 bytes including page
rounding. Duplicate handles are checked, records capped at32, alignment/overflow
are bounded. Secure, cacheable and MMIO requests are refused rather than assigned
ordinary RAM. Buffer flags are preserved in replies. For this bring-up probe the
GPU and GMU share a privileged RW page-table root; separate permissions/isolation
remain work for the production backend.

On refusal CM3 was reset, GX stayed off, GBIF/QTB drained, awake RSC/PDC registers
and TCM were restored, GPU context0 TLB synchronization completed with faults0,
and memory was released. No CP enable or graphics commands in stages25/26.
Do not classify26 as a completed START or GPU initialization.

Captured requests are a regression fixture:
`tools/tests/fixtures/waffle-hfi-start-allocations.json`.
`waffle-hwsched-host.py` replays all8: accepts first7 and refuses the secure request.
The fixture/replay test was added after the artifact build and run manually;
compiled kernel C is unchanged. Builder includes it for future artifacts.



## 2026-10-24 — active secure-memory port, stage27 PASS

User explicitly requested continued driver work; do not stop after reporting a milestone.
Stage27 artifact `diagnostic-gpu-secure-page`, run `20261024T203147Z`, returned30610 0.
SCM MP_ASSIGN availability0/1, whole16KiB page HLOS->CP_PIXEL status0/result0,
CP_PIXEL->HLOS status0/result0, subsequentCPUwrite/read succeeded, context0TLBdone/faults0.
No GMU boot/GXon/CPcommands in this stage. It proves real ownership roundtrip,
not just a software ABI check. The page is excluded from GPU/GMU mappings.

New `sys/waffle_scm.h`: bounded native MP_ASSIGN encoder, at most256 whole16KiB
physical pages; segment/source/destination/extended arrays isolated in one16KiB
HLOS-owned metadata page. SCM64 extended args start at argument3; arginfo1117;
sourceHLOS3/destinationCP_PIXEL10 RW6, reverse HLOS RWX7. `scm_raw` now supports
x2..x5 and existing bounded interrupt/x6 resume. Unknown ownership retains buffers
and returns REBOOT REQUIRED; no CPU read or free before confirmed reclaim.
Actual-source hosttest uses mprotect(PROT_NONE) during CP ownership and tests
assign/reclaim failures, allocation failures and metadata bounds under ASan/UBSan.

Pinned additional primary sources include secure_buffer.c/.h, qcom-io-pgtable-arm.c,
qcom-io-pgtable-alloc.c/.h and io-pgtable.h, with provenance JSON in gpu/vendor.
Important: native secure page tables are SHARED HLOS(RW)+CP_PIXEL(R), unlike
exclusive CP_PIXEL data. Reclaim source list must include BOTH VMIDs. New stage28
candidate `diagnostic-gpu-secure-table-page` tests this table-sharing roundtrip,
including CPU write while shared. Building/Android reset underway; hardware untested.
No GPU rendering or FPS increase. Policy/runner currently supports1..28.



## Active continuation — 2026-10-24, stage29 PASS, stage30 candidate

User asked to keep implementing the driver rather than stopping after milestones.
No user pause. Still no GPU rendering, Metal acceleration or FPS increase.

- Stage27 `diagnostic-gpu-secure-page`, run203147Z returned30610 0: real whole16KiB
  HLOS->CP_PIXEL data ownership and reclaim both status0/result0; CPU write after
  reclaim verified, full cleanup. Preserved artifact.
- Stage28 `diagnostic-gpu-secure-table-page`, run203607Z returned30553 0: table
  shared HLOS RW+CP_PIXEL R, CPU write while shared, reclaim source BOTH VMIDs
  back to HLOS RWX; all SCM calls0/0, full cleanup. Preserved artifact.
- Stage29 `diagnostic-gpu-secure-context`, run204339Z returned25281 0: private
  three-table root shared with CP_PIXEL, protected16KiB data page exclusively
  assigned CP_PIXEL, CB2/SMR2/SID2 ASID3, first/last ECATS translations match PA,
  context2 disable/TLBdone faults0, data/tables reclaimed0/0, resources freed.
  No GMU/GX boot or commands. This is real protected translation, not rendering.

SCM runtime now exports waffle_scm_assign_pages; only pre-submission errors
returnfalse; unknown ownership stops with REBOOT REQUIRED and retains pages.
Native secure_buffer caps batches at32segments (2MiB size threshold); use32
16KiB pages per call. Encoder metadata permits256 but runtime caps32. Stage29
artifact was built before this cap change, but its calls only used3/1segments.
Generic GPU context helper supports private bank/slot/SID and checks overlapping
routes; TLBIASID now uses current TTBR0 ASID rather than hardcoded1.

Stage30 candidate `diagnostic-gpu-hwsched-protected` building/awaiting validation:
prepares4MiB protected arena at GPU VAa0000000, private SID2 root; data is assigned
in8 native32-page batches. HWSCHED normal arena32MiB remains at61000000 in the
shared SID0/SID5 root; protected pages are NEVER mapped there. Protected descriptors
kind5/flags1007 now receive real GPU VA (GMU VA0) from the protected allocator.
All protected ownership/context state remains until CM3 stopped, GXoff and bus
traffic drained, then CB2TLBsync -> reverse data batches -> tables reclaim -> free.
Partial allocation/assignment rollback and TLB/reclaim failures are hosttested.
No CP enable or GPU commands in stage30. Full START ACK not hardwareverified yet.

New actualsource tests: waffle-scm-host.py (mprotect page while CPowns it),
waffle-secure-context-host.py (guards and detach-before-reclaim),
waffle-protected-pool-host.py (scattered4MiB pages/nativebatches/partialrollback,
PROT_NONE during ownership/failure retention). All ASan/UBSan checks pass so far.
Current kernel/loader/runner support1..30; stage30 hardware check pending.
Phone reset to Android after29; wait for boot_completed before RAMbooting30.



# PAUSED by the user — 25 October 2026, after GPU stage30 and PosterBoard diagnosis

The user explicitly asked «сохраняй прогресс лимиты кончаются». SAVE AND STOP.
Do not build, boot, test or continue implementation until the user resumes.
No further work is queued. PosterBoard UI test completed. USB was absent at recovery
check; no reboot command was sent and Android boot is NOT confirmed. Recovery result is in `work/waffle/posterboard/paused-recovery.json`.

## Authorized objectives on resume

1. Fix PosterBoard first (the blank Add New Wallpaper gallery).
2. Continue the GPU driver alongside software work; hardware tests use the phone sequentially.
The user initially said SpringBoard, then explicitly corrected it to PosterBoard.
They will provide a list of other redwood fixes AFTER PosterBoard; do not request it now.
No subagents were used. No flash/erase; all hardware images RAM-booted. Stable Downloads packages preserved.

## GPU: latest fully verified milestone = stage30

Artifact `work/waffle/diagnostic-gpu-hwsched-protected/`.
Run `20261024T204950Z`, returned58372 0: native HWSCHED START ACK status0,
10 allocations, total7405568 bytes, including the previously unsupported protected
context-save buffer. Normal32MiB arena61000000 is in the bring-up SID0/SID5 root;
protected4MiB arena a0000000 is in a separate CB2/SID2 root. Protected data pages
are exclusively CP_PIXEL-owned, tables shared HLOS(RW)+CP_PIXEL(R), using native
SCM MP_ASSIGN in at most32 segments per call. Before release: CM3 reset, GXoff,
GBIF/QTB drained, context2 disabled/TLBdone/faults0, reverse ownership transitions,
all data/tables returned HLOS, then freed. Full TCM/awake RSC cleanup verified.
NO CP command execution, GPU draw, hardware Metal or FPS gain yet.

Preceding isolated passes, all preserved:
- Stage27 `diagnostic-gpu-secure-page`, run203147Z returned30610 0: exclusive
  CP_PIXEL page ownership + confirmed reclaim + restored CPU access.
- Stage28 `diagnostic-gpu-secure-table-page`, run203607Z returned30553 0:
  HLOS/CP_PIXEL shared table ownership + CPU write + confirmed reclaim.
- Stage29 `diagnostic-gpu-secure-context`, run204339Z returned25281 0:
  private3-table root, protected16KiB data page, first/last SID2 translations match,
  context2 ASID3, fault-free cleanup and ownership return.

Current loader/kernel/runner support1..30. New actual-source ASan/UBSan tests cover
SCM ABI, protected CPU-inaccessible pages, private SID2 routes, scattered4MiB pages,
32-segment batches, partial rollback and retention on TLB/reclaim failures. Raw
SCM failures after submission stop with REBOOT REQUIRED and preserve pages.
Latest GPU artifact kernel/EFI/container built and validated, then hardware passed.

Next GPU work, NOT implemented yet: native Gen7.9.1 `gen7_start` setup (GBIF/UCHE,
protected-register spans, SECVID, clock-gating), then CP_ME_INIT through
HFI_ISSUE_CMD_RAW131. Do not repeat known-failing direct SQE-enable21/23.
Primary pinned `vendor/adreno_gen7.c`, `adreno-gpulist.h`, `gen7_reg.h`.
Live DT: LPDDR5type8, MAL32, UBWC4; highestbank16; GMEM3MiB aligned16MiB;
UCHE clientPF1. Native secure aperture startsf0000000 but our protected VAa0000000
needs matching programmed SECVID bounds. Native cpu_gpu_lock is16bytes, not24.
No native-start register generator/stage31 was written in this session.

## PosterBoard: strong next lead, no functional fix claimed

UI run `20261024T205940Z`, execsession10279 COMPLETED returned1441823 0,
300seconds, fbscale2, kernel from GPUstage30 but NO gpu-probe flag, full iOS system.
Root `posterboard/layers-diagnostic/images/root.packfs`39174144bytes,
SHA256609bef6845d07a2c80770801734a6dd9e7b89146b31cd6d01825b6d3fc651920.
User confirmed white Add New Wallpaper screen. Screenshot `screen-30.png` shows
correct title/close button, empty content. Layer graph shows active visible
PBFPosterGalleryPreviewViewController / _PBFGalleryCollectionViewController with
empty UICollectionView: no cells. Therefore the remote window IS displayed;
prior upstream invisible-hosted-switcher note is not sufficient to explain this.
PosterBoard240 also hit scene-create watchdog10s (CPU0.037s, total11.720s),
then restarted as336. Do not blindly disable watchdog; likely waiting on a service.

**Most useful discovery, not tested/fixed yet:** `userland/mkjobs.py` DENY includes
`duetexpertd` (line13). Stock `com.apple.duetexpertd.plist` provides the exact
`com.apple.proactive.FaceSuggestions.xpc` Mach service used for wallpaper gallery
layout. Logs show DataStoreProactive push timeout. PosterBoard has loaded Gradient
(and other) descriptors but no gallery sections. This is a plausible root cause,
NOT yet proven. The existing mkjobs ALLOW environment removes selected DENY terms.
Next test should enable ONLY `duetexpertd` on demand in an isolated root using
`ALLOW=duetexpertd`, preserving all other exclusions; do not edit global DENY.
Read-only source check already confirmed program `/usr/libexec/duetexpertd`, mobile
user, MachServices include FaceSuggestions.xpc. No enabling change made yet.
FileProvider `Cannot query for providers` permission257 is a different subsystem;
do not bypass unrelated access checks based on that message.

Diagnostic code already built and tested in this UI run:
- `userland/src/inject_sb.c`: includes hidden PosterBoard windows; alpha, controller
  chain, existing layer/context graphs. Replaced13 unsafe diagnostic snprintf appends
  with bounded append_more so a long layer description cannot overrun the buffer.
- `userland/src/poster_diag.c --layers`: bounded notifications at30/90/180seconds,
  exits240seconds, no thread sampling in this mode.
- `tools/build-waffle-poster-layers.py`: isolated builder based on client-gl-kit;
  replaces libredwood-sb, adds diagnostic executable/job; injection config unchanged.
  Packed init, SB/app libraries, helper and manifest verified. Scale2 retained.
Existing CPU snapshot nil-Metal-queue fix in inject_poster.m loaded successfully.

Next diagnostic improvement if needed: notify ONLY PosterBoard/Preferences rather
than SpringBoard's entire icon graph, to avoid filling the ~1.44MiB kernel log cap.
Current helper posts global com.redwood.layers. Do not mistake missing late log
lines for an absent process. Some log files contain NUL: use rg -a or sanitized text.

Offline read-only cache tools/results in `posterboard/`:
- cache_reader.py, new objc_cache.py. Encoded pointers mask0xfffffffff; direct
  relative selector base18229614b was derived/validated against _imageForView:.
- gallery-classes.txt and gallery-provider-classes.txt: exact IMPs, selectors, ivars.
- retrieve-gallery.asm / fetch-gallery.asm / apply-gallery-snapshot.asm.
`PBFModalRootViewController` owns _galleryDataProvider (offset936) and _dataStore968;
store has _stateLock_suggestedLayout104 and _stateLock_configuration96;
`PBFGalleryConfiguration` depends on ATXFaceGalleryConfiguration suggested layout.
These are analysis facts; no arbitrary ivar patch or fake gallery was implemented.

Checkpoint `gpu/checkpoint-20261025-paused-gpu30-posterboard.tar.gz` (+sha256)
saves current source, new GPU artifacts27..30, new source provenance, PosterBoard
root/diagnostics, relevant logs and this resume. Supplements earlier stage26/full21
archives. The 2.2GiB iOS system image is intentionally not duplicated.

--- Older notes follow; the PAUSED state above takes precedence. ---


## 25 October: resumed, PosterBoard provider dependency isolated

User preference: return Android after every completed hardware test/task and verify
ADB sys.boot_completed=1. RAM-only; no flash/erase.

Run20261025T064451Z: root duet-diagnostic SHA256
d9055d2880af9690b69b411177d9af50605a4fbc992dcbd5f741126914e865d9,
300s scale2, returned1441823 0; user confirmed white gallery. Scoped ALLOW=duetexpertd
actually starts the FaceSuggestions provider, but it repeatedly SIGTRAPs after
MobileAssetError32 (cannot confirm data vault exists), missing mobileassetd.v2.
Read-only disassembly confirms ATXEnableMobileAssetDataVault1bf1c854c explicitly
brk1 at1bf1c8718 when the vault request produces an error; matching error string
1bf4017fd. No bypass or native patch applied.
Loader reboot sent, Android sys.boot_completed=1 verified; recovery JSON saved.

Next root assets-diagnostic (duetexpertd +mobileassetd on-demand, all other DENY
terms preserved), SHA256fc63b3a2d1f3a95d580d568ba0ff6410553c691206ac9702baa15ccc9dbf4ba8.
Packed jobs/helper/libraries validated; second RAM image booted, waiting BootiOS.
Poster-only layer notification now avoids SpringBoard icon graph.

GPU offline: build-waffle-gpu-start-tables.py extracts pinned Gen7.9.1 GBIF,
GMU AO HWCG,48 protection spans,58 IFPC+17 preemption restore pairs (616bytes
including16byte native lock). Compiled native-table comparison ASan/UBSan passed.
Output gpu/gen7-start-tables.json. No runtime integration or new GPU hardware test.

## 25 October GPU31: native disabled configuration, first hardware result

Kernel/loader/runner now support31 (32+denied). New generated
waffle_gen7_tables.h contains92 native gen7_start operations,48 protection
spans and75 restore pairs. waffle_gen7_config.h performs reversible
configuration/readback, native16byte lock+616byte restore list assembly,
CP/RB-disabled gates and domain bounds. Clock-gating deferred, CP commands
not submitted. Actual pinned native gen7_start comparison passed (all92ops),
ASan/UBSan all92 induced readback failures rollback, restore-failure path.
Stage31 runs full protected HWSCHED START, DCVSseq32, OOBpower, config,
PREPARE_SLUMBERseq33; every resource retained until quiescence/reclaim.

Artifact diagnostic-gpu-gen7-configuration built/validated. Hardware
run20261025T072043Z returned60966 0 but FAILED config readback index50b
RBBM_PERFCTR_GPU_BUSY_MASKED. Everything through minimum vote/OOB passed.
Rollback, slumber/RSCsleep, TCMrestore, fault-free context2/0 and all protected
page ownership returns passed. Android reboot sent and boot_completed=1 verified.
No draw/CPcommand. Do NOT claim GPU31passed yet.

New diagnostic artifact diagnostic-gpu-gen7-config-readback built+validated,
adds only specific50b read/write trace to determine why readback mismatches.
Still strict comparison; NOT yet tested. Android rebootbootloader requested
for next test, waiting fastboot session37479. No image booted yet.
Use its own matchingEFI/kernel. User explicitly prioritizesGPU next.

# ACTIVE — GPU31 PASS, 25 October2026

Latest steering: GPU priority. Next GPU work is native HWCG handshake, then CP
init via HFI RAW131. No stage32 code yet. User asks return Android after EVERY
completed test; keep this preference.

Stage31 PASSED run20261025T073230Z returned61885 0. Artifact
work/waffle/diagnostic-gpu-gen7-config-page/. Full protected HWSCHED START,
DCVSseq32, OOBpower,92 native setup operations/readback+rollback,616byte
restore list (58IFPC+17preemption pairs), PREPARE_SLUMBERseq33, RSCsleep,
TCMrestore, CB2/CB0 fault-free TLBinvalidate, all protected pages reclaimed.
CP stays DISABLED. Clock-gating deferred. NO GPU commands/draw/FPS gain.
Android reboot sent; verification session11071 (check before nextboot).

Readback masks discovered safely with native writes preserved:
-50b busy mask: ffffffff writes/read002f7fff/restores0; compare002f7fff.
-e0d UCHE_GMEM_RANGE_MAX_LO:012fffff writes/read012ff000; comparefffff000.
Prior fail runs072043,072503,072927 all rolled back and returned resources,
and each Android return verified. Source primary gen7_start compilation matches
all92 writes, ASan/UBSan injects all92 failures+restoreretention tests.

New sources: waffle_gen7_config.h (bounded reversible transaction),
waffle_gen7_tables.h (generated), build-waffle-gpu-start-tables.py,
waffle-gen7-config-host.py, waffle-gen7-transaction.c,
waffle-gpu-start-tables-host.py, waffle-cp-init-host.py; all integratedbuilder.
Unused HFI CP init encoder is independently verified against native12,285cases.
Kernel/loader/runner currently1..31; preserve tested artifacts.

PosterBoard: gallery displayed8sections; user confirmed Color editor opens AND
adds wallpaper (run070249). Fixed plain root built/packedvalidated in
posterboard/fixed/images/root.packfs, NOT hardwaretested without observers.
Some previews incomplete; early-opening startup race NOT excluded. Do not claim
all PosterBoard issues solved. No stable Downloads package overwritten.

--- Earlier session details below ---


# ACTIVE — corrected GPU32 ready, phone USB absent

Stage31 fully passed (see below/archived). First32 run20261025T074423Z
returned61904 0, FAILED BEFORE HWCG was enabled: our extra preflight read of
RBBM_CGC_GLOBAL_LOAD_CMD returneddeafbead. Native driver ONLY WRITES this
command and waits P2S_STATUS/TXDONE, so the extra readable-state guard was wrong.
Rollback, slumber33/RSCsleep, CB0/CB2/TLB and secure-page reclaim all passed.
Android reboot was SENT/acknowledged but boot_completed NOT yet confirmed:
USB absent at0748check. Async question pending asking current phone screen/USB.
DO NOT falsely claim Android has returned after32; last confirmed Android before32.

Corrected artifact diagnostic-gpu-gen7-hwcg-command BUILT + validated, NOT BOOTED
or hardware tested yet. Native HWCG helper now never reads LOAD_CMD, uses
TXDONE only. Host test models command reads asdeafbead and asserts zero reads,
compares exact native on/off trace,1/3us ACK/3us timeout, AO/global failedrestore
retention, CP/global preflight gates. All host+kernel/EFI/container checks pass.
Kernel/loader/runner support1..32. No CPstart/commands/draw/FPS gain yet.

Use matching hwcg-command EFI/kernel for next32 test, tiny probe-firmware-system
as both root/system, --gpu-probe32 --seconds30. After EVERY test send Android
reboot and verify boot_completed1 per user's explicit preference.

Additional native flow checked offline: gen7_hwsched_gpu_boot calls gen7_start
(containsHWCG) BEFORE init_ucode_regs, which programsSQE/AQEbases only; HWSCHED
path does not directly writeSQE_CNTL1 like legacy ringbuffer path. RAW131 firmware
handles CP startup. gen7_hfi_send_cmd_async DOES waitACK; native failure is
ACKword2==ffffffff, otherwise accept then pollAO_GPU_CX_BUSY_STATUSbit23 clear
200ms. Use hfi_exchange(...zero_ack=false), not forcedzero ACK, for futureRAW.
Warmboot scratch helper is a NOOP when warmboot feature disabled, so no need
to fabricate scratch protocol for firstcoldboot. ZAPload follows nativeCPinit.

For actualCP test, current reversible config helper requires CPdisabled and
restoresGXregs beforecollapse. Do not simply sendRAW inside32callback: CPmay
remainenabled, and restorewhileactive isunsafe. Implement proper CP lifecycle:
keepconfig/mappings through slumber/CM3reset/GXoff, thenrestoreonlyAO/GMU state
and reclaim. No33 runtime/flag implemented.

--- Previous checkpoints/history ---


# PAUSED by user — 25 October2026, GPU32 PASS

User explicitly said «лимиты приближаются, останавливайся». SAVE AND STOP.
No builds, boots, tests, implementation or queued work until explicit resume.
Follow-up «насколько мы продвинулись по сравнению со вчерашним днем» is a STATUS
question, not a resume instruction. No formal goal or agents active.

Phone: ANDROID CONFIRMED via ADB sys.boot_completed=1 at07:54:45UTC, serial
1c62e9aa. Android reboot sent immediately after the last completed test.
User explicitly requires Android return after EVERY completed test/task.
RAM-only; no flash/erase. Stable Downloads packages preserved.

## Latest verified GPU milestone:32

Artifact diagnostic-gpu-gen7-hwcg-command/, run20261025T075252Z,
returned62208 0. FULL PASS:
- Full HWSCHED START,10 allocations incl4MiB protected arena/privateSID2.
- DCVSseq32 and OOB_GPUack/GXon at lowest stock frequency.
-92 native Gen7.9.1 setup operations/readbacks.
-Native HWCG on/off hardware handshake: TXDONE=1, status3, originalGLOBAL0.
-Native616byte powerup register list:16byte lock +58IFPC/17preempt pairs.
-All config/AO/global controls restored with CP remaining disabled.
-PREPARE_SLUMBERseq33, RSCsleep, CM3reset/TCMrestore, GXoff/GBIFQTBdrain.
-CB2/CB0 TLBinvalidate faults0, all protected pages/table ownership reclaimed.
-Android reboot and boot_completed1 confirmed after the test.
NO CP command execution, GPU drawing, hardware Metal or GPU FPS gain yet.

Previous verified31: diagnostic-gpu-gen7-config-page/,
run20261025T073230Z returned61885 0. Same native config, without HWCG exercise.
31 checkpoint archive retained: checkpoint-20261025-stage31-posterboard.tar.gz
170205387bytes,176files,SHA2566126a5ee934884946a657ca6532d97f577bc567f3b74755b8372a45f87c5549c.

Readback discovery tests072043/072503/072927 all returned resources +Android:
50b busy-mask nativeffffffff reads002f7fff; e0d GMEMmax native012fffff
reads012ff000. Keep native writes; generated separate readback masks reflect
observed readable bits/page granularity.
First32 run074423 returned61904 0 FAILED our incorrect extra readableLOAD guard:
CGC_GLOBAL_LOAD_CMD returneddeafbead. No clock setup ran. Fixed by following
native code: ONLY WRITE LOAD/TRIG, poll P2S_STATUS/TXDONE3x1us. Never readLOAD
as a state latch. That corrected32 hardware passed.

## Source/build state

Kernel/loader/runner1..32,33+denied. waFFLE_GEN7 config header holds reversible
92-op transaction with optional HWCG exercise; unexpectedCP/fatalcallback retains
state/pages and stops. waffle_gen7_hwcg.h implements nativeAO3 ->GLOBAL1 LOAD1
TRIG1 ->TXDONE3us ->GLOBAL0, nativeoff and readableAO/global restoration.
Native code/order and fault/rollback/retention host tests ASan/UBSan passed,
kernel/EFI/container validated. Generator/header and tests all in builder snapshots.
Unused waffle_hfi_cp_init_packet in waffle_hfi.h matches actual native
gen7_cp_init_cmds +PM4/HFI macros in12,285 address/sequence cases.

## Next GPU work on explicit resume

Actual CP initialization via HFI RAW131, not the old directSQE-enable21/23 path.
Native gen7_hwsched_gpu_boot: gen7_start(includesHWCG), then SQE/AQEbaseprogram,
then RAW131 CP init. HWSCHED path itself does not writeSQE_CNTL1 like legacy RB.
gen7_hfi_send_cmd_async DOES waitACK; error isACKword2==ffffffff, otherwise
accept and then pollAO_GPU_CX_BUSY_STATUSbit23 clear200ms. Use zero_ack=false.
Warmboot scratch helper NOOP when warmboot disabled. ZAP/PAS13 load followsCPinit
and is not implemented yet; do not switch to nonsecure before verifiedauth.

IMPORTANT: current32 exercise returns with CPdisabled and restoresGXregs BEFORE
collapse. Do NOT insert RAW131 into this callback without proper lifecycle.
For33 preserve config/buffers through realCP use, slumber, CM3reset, GXoff and
GBIF/QTBdrain; restore only always-on/GMU controls after GXoff, then reclaim.
Do not access gatedGX MMIO or free protected pages while engines may run.
NO33 runtime code has been written; only offline source research/plan.

## PosterBoard result

Scope ALLOW=duetexpertd mobileassetd fixes missing FaceSuggestions provider and
fatal ATXEnableMobileAssetDataVault/ASEnsureDataVault error32.
UI run070249 displayed8gallery sections (screenshot screen-18.raw /
screen-current.png). User confirmed Color editor OPENS AND ADDS wallpaper.
Some previews incomplete; early-open startup race is not excluded (previous both
service run065248 stayed white; third run070249 was opened later).
Normal root WITHOUT observers/helper is built+packedvalidated at
posterboard/fixed/images/root.packfs, SHA256
c2cb1de85085ee4b7a8b16a2e324f6e16edfafa65eafa042aa226a4320ad1c1b,
NOT separately hardwaretested. Do not claim every PosterBoard issue is fixed.
No stable Downloads package overwritten. User will give otherredwood fixes later.

Upstream ios-macan fetched READ-ONLY at bf6106be492670acd05fac0ee7b7d037a48eafd9;
snapshot gpu/upstream-20261025/. No merge/reset; upstream still disables poster
switcher and excludes both services. No ready PosterBoard fix found.

## Resume commands (ONLY after explicit resume)

python3 tools/build-waffle-diagnostic.py --mu work/waffle/mu
 --dtb /home/qarzis/OnePlus12-port/vendor_boot.img-2.dtb
 --dtb /home/qarzis/OnePlus12-port/vendor_boot.img-3.dtb
 --live-dtb work/waffle/gpu/android-capture2/android-live.dtb
 --output work/waffle/diagnostic-gpu-NEXT --userland --jobs6

Validate with work/validate-venv/bin/python tools/validate-waffle-diagnostic.py.
Probe uses tiny gpu/probe-firmware-system.packfs as BOTHroot/system, seconds30.
Normal iOS uses full work/waffle/images/system.packfs2.2GiB, fbscale2.
Use matching EFI/kernel; wait for/select BootiOS if xnuloader is absent.
Aftertest fastboot -s xnuloader reboot, confirm ADBboot_completed1.
Never parallelize USB fastboot connections or privateMu builds.

Historical checkpoints retained; this PAUSED state takes precedence.


## 25 October2026 evening: offline CP lifecycle (user resumed without phone)

Prepared split persistent native config/HWCG lifecycle and RAW131 CP submission
helper, with cache publication ordering, native ACK policy, bounded BIT23 idle
poll and resource retention after uncertain submission. Post-collapse cleanup
never touches gated GX MMIO. Added sanitizer coverage for missing stop evidence,
timeouts, restore failures and no early rollback. Fixed error-path liveCP guard.

Full XNU/EFI build and container validation PASS at
work/waffle/diagnostic-gpu-cp-lifecycle-offline/. No USB/device commands performed.
RAW helper is NOT runtime-integrated; probe range remains1..32. No new hardware
CP execution/drawing/FPS result. Latest hardware milestone remains32 PASS.
Updated authoritative work/waffle/gpu/RESUME.md supersedes historical pause text.
Next: audit native host GPU IRQ handling and persist snapshots through the
existing OOB/slumber/reset/GXoff/GBIF-QTB sequence before introducing probe33.


## 25 October2026 evening: runtime CP integration and hardware isolation

Implemented persistent paired config/HWCG/ucode/CP lifecycle, native RAW131
publication/ACK/idle handling, actual stop-evidence collection and AO-only
post-collapse restoration before SMMU/protected reclaim. IRQs remain masked for
polled diagnostic; no final GPU interrupt handler/ZAP/unsecure/drawing.
Probe34 prepare-only FULL HARDWARE PASS run184339Z returned61757 0, including
native collapse, fault-free contexts and complete ownership reclaim; Android
boot_completed1 confirmed after automatic reboot. CP remains disabled in34.

Full RAW33 first failed run184007Z (black/lost USB, manually recovered Android).
Found native UCODE AP mismatch: read-only GPU firmware lacked AP_UNPRIVbit6.
Corrected only SQE/AQE permissions, actual mapper/native AP differential tests
ASan/UBSan pass. However RAW33 run184818Z STILL failed with USB05c6:900e.
Thus fix is native parity, NOT proof of crash cause; CP ACK/idle success unknown.
User instructed force restart; Android recovery pending in latest GPU/RESUME.md.
No further raw retries planned until better failure logging/new evidence.
Three full XNU/EFI builds/containers and composite99-failure tests passed.


Recovered latest900e crash: ADB boot_completed1 CONFIRMED; phone left Android.
Prepared pinned stock qdl and guarded read-only900e small-segment capture tool,
not yet used on device. qdl builds/Sahara archive test pass; unrelated VIP test
blocked by missing host zip. No HIL tests executed. Runner now saves pre-run
loader log to retain dynamic RAM allocation addresses. No further RAW retries
performed. Latest authoritative resume notes updated.


## 25 October2026 late: hardware Sahara capture, prefix35, fault monitor

Read actual PJD110 MEMORY_DEBUG64 table and27diagnosticBINfiles249068bytes using
pinned qdl, after user granted temporaryUSBACL. Fixed wrong iSerial binding
(qdl usesiProduct_SN) andmissing md_ filterprefix, nativefilter hosttests pass.
Capture gpu/crashdumps/20261025T190459Z; qdl reset Android verified. Diagnostic
bytes highentropy/opaque, likelyencrypted; no readable crashcause decoded.
Standalone firstCP_THREAD_CONTROL prefix35 also losesUSB(run191544Z), Android
restored manuallyandADBboot_completed1 verified. This is still NO confirmed
GPUcommandexecution/frames. Prefix-alone firmwareacceptance is unconfirmed.
Built newRAW faultmonitor: DEBUGqueue2+CTX_BAD+ERR+CM3IRQbit15 handling with
resource retention, message/logbounds, actualhelper ASan/UBSan tests pass.
Full XNU/EFI build+containervalidation PASS at diagnostic-gpu-cp-fault-monitor,
NOT hardwaretested. Latestsoftware supports1..35; latesthardwarePASS remains34.
CurrentphoneAndroid, no further device action queued. Completionestimate remains
rough30–40% fullaccelerateddriver; no measuredprogresspercentage.


## 25 October2026 PAUSED by user at7percent quota

Newprobe36 native SMMUstall(CFCFG1,HUPCF0,CFIEmasked) plus FSR/FAR sampler
hostsanitizers/builds passed buthardwarelostUSB. Run193512Z retained29logs through
prepublicationpause. Added8stepcheckpoints; run194036Z retained65logs, last
checkpoint5-index-published, never6-doorbell-sent. No SMMUfault captured.
Nextfix NOT IMPLEMENTED: remove diagnostic MMIO/logs AND nonnative350mspause
frombetween cmdqwriteindex publication and H2Gdoorbell; make nativeconsecutive
barrier/index/barrier/notify sequence. Diagnostic timing itself can cause failure,
so lastcheckpoint does not prove the exactcause. Currentcheckpoint source still
contains that experiment. Userpaused before edit. PhoneuserconfirmedAndroid;
ADBverification recordedgpu/pause-state.json. No more work until explicitresume.

26 October: consecutive HFI publication/notification host-tested and built as
`diagnostic-gpu-raw-publish36`. Hardware36 failedUSB (25samples); control34
PASSED returned59041/fullcollapse and AndroidADB1; fullinit33 also failedUSB.
ManualAndroidrecovery confirmed after33. NoCPACK/frame.
Next experimental nativeSCM CP-SMMU-aperture configuration isolated in37
(prepareonly),38(fullinit); actualC nativeABI/failure testsPASS, buildpending.

Native SCM aperture probe37 hardware PASS20261026T162202Z (returned59336 0).
SCM availability=1, CB0 configuration status=0, prepare/fullcollapse pass;
automaticAndroidADB1. This does not confirm CP execution. Probe38 pending.

26 October final hardware:37 nativeSCMaperture+preparePASS;38 fullCPinit
withSCMapertureFAIL USB/noACK, manualAndroid+ADBboot_completed1 confirmed.
SCMaperture implementation alone does not fix CP start. No frames/acceleration.

26 October native trace and splitVA:39 hardwarePASS20261026T164949Z,
highalias ECATS+prepare/collapse, automaticAndroid.40 CPinitFAIL20261026T165123Z,
manualAndroidconfirmed. Native matched-mode trace165442Z provesGMU DMSfeature
mustbeadvertisedON independentlyofCPdisableDMSbit; oldportexplicitlydisabled
it. New41/42 isolateDMSadvertisement/orderfix; hosttestPASS, buildpending.

Userrequestedstopaftercurrenttest26Oct. DMS41artifactfullhosts/XNU/EFI/container
PASS.41attempt20261026T165852Z NOTRUN: getvarplatform timeout, noloader,
no kernel/payload transferred. Do not call thisGPUfailure. Androidmanual
recoveryconfirmationpending. Nextresume:test41prepareonlythen42CPif41passes.

## 28 October 2026: BCL control and native ACD table

Probe43 changed only feature ID11 to the Android BCL value (enable1, data1).
Its preparation-only hardware run passed and Android booted. Probe44 carried
that change into full CP RAW, then lost USB and reached Qualcomm 900e. Sahara
reset returned Android; ADB confirmed `sys.boot_completed=1`. This change did
not establish CP execution or GPU drawing.

A new private Android Kprobe capture included HFI message ID7, which the
previous trace filtered out. Native ACD_TBL is 69 words / 276 bytes: version1,
enable_by_level0x1ffe, stride1, 12 level values and 52 trailing zero words.
The offline `waffle_hfi_acd_table_packet` encoder matches all captured words.
Native `gen7_gmu_acd_probe` also obtains an AOP mailbox, and first boot sends
ACD state to AOP before the HFI startup. The port does not yet perform that
mailbox step, so the ACD table encoder is not wired into hardware startup.
Full trace and current status are in `work/waffle/gpu/RESUME.md`.
