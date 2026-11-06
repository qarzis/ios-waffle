# UniXNU GPU integration U01

User requested integration into current Waffle iOS16.5 port. Pinned upstream repositories checked out under /home/qarzis/unixnu-reference (gitlinks/provenance). Do not replace qualified Adreno750 hardware startup with A740/SM8550 power/firmware code.

Current concrete implementation: unmodified MIT upstream NativeAdrenoABI.h vendored with revision/hash/license. New rootPID1 privatecdev ingress WAFFLE_UNIXNU_CALL carries ABI2methodQuery into currentA750owner. Reports verified backendlimits39VA/36PA/actualmaxBO, flags0 (no unsupportedhostimport/coherencypromise). Allothermethods refusedbeforehardware. This isNOTIOKitservice/Metalpublication. Actualcdev+upstreamheaderhostfixturespass; ordinaryGEM/submit/cacheownershipregressionspreserved. DedicatedDarwin16.5probe compiled toqueryandtestunsupportedsubmitrefusal,thenexistingGLpixeltest. Fresh U01 kernel built and paired validation passed. Hardware run 20261106T095030Z passed: ABI2 query, unsupported submit refused, FD750 GL triangle checked=256 wrong=0 GL_error=0. Android return confirmed. See gpu/U01-result.json. No Metal or performance claim.

Remaining substantial integration: IOKitNativeAdrenoABIservicewithper-taskowner; translateBOalloc/map/free/CPUmap/queues/fence/history/submit/lifetime; noheader-castbetweenMSM/NativeAdreno. Currentbackendusesglobalserializedowner whileupstreamexpectsmultipleclients/queues andclientchosenIOVA. Needexplicitunsupported/refusalratherthaninventAPI. DeviceInfochip43051401/A7503MiBfromqualifiedboardevidence; UBWC/highestbank/swizzlestillmustbindmatchingcatalog,notA740values. ImportedIOSurfaceownershipneedsCPUread/writevsGPUwriteexclusionbeforeproductionnativewritabletargets.

Metalfrontend upstreambuildrequiresDarwinTurniplibvulkan_freedreno+metal2vulkan andiOS17default/27option, macOSxcrun/codesigntoolchain. OuravailableSDK16.5/clangiOSbuildsrequireportingthosebuildstepsandcheckingactualiOS16.5MetalABI. ExistingMesaOSMesa isOpenGL,notTurnipreplacement. NoreadyTurnip/metal2vulkanbundlecurrentlyverifiedlocal. KeepordinaryMesa/rootbootuntilisolatednativequery,BO,fence,pixelproofandMetalABIstartupqualified. NeverclaimU01queryaloneacceleratesMetal/SpringBoard.


## U02 — owned allocation/free candidate

Methods 2 and 4 translate the pinned fixed-size UniXNU records into shared existing GEM allocation/reclamation helpers under the same context lock and PID1 gate. Allocation accepts positive 4KiB multiples up to the existing backend limit, alignment exponents 12..14, noncontiguous backing only. Larger valid alignment or contiguous requests return ENOTSUP before allocation. Invalid sizes, versions and output/input shapes return EINVAL. Free validates the full 64-bit handle before narrowing; generations prevent stale/double free; failed backend reclamation retains the live object for retry. Allocation currently also establishes the backend-chosen VA internally; this is NOT implementation of client-selected BoMap and gives users no address or mapping token.

Host ASan/UBSan actual-cdev test passed: normal 13-BO Mesa submission regression; foreign PID, contiguous/alignment/size refusals, allocation/free, generation reuse, stale/double/64-bit-truncated handle refusals, reclamation failure retained then retried. Exact upstream alloc layout checked. Darwin16.5 probe built; fresh full kernel build and paired validation passed. Hardware run20261106T100106Z passed two alloc/free cycles, stale refusals and distinct generation handles, plus FD750256pixels/wrong0; runner0/Android confirmed. Boot iOS selected manually after automatic menu timeout.

| Upstream method | Current adaptation | Next gate |
| --- | --- | --- |
| Query 1 | U01 hardware qualified, flags 0 | Keep conservative capabilities |
| BoAlloc/BoFree 2/4 | U02 hardware qualified for PID1, shared backend lifecycle | Two hardware allocations/frees and stale refusals plus GL pixels |
| BoMap 3 | Refused | Client-selected IOVA, collisions, VA reservation and revocation |
| Submit/Wait 5/6 | Refused | Bound BO ranges, queues, dependencies and real completion |
| CpuMap/Unmap 13/14 | Refused | IOKit per-task memory tokens, mapping lifetime |
| DeviceInfo 15 | Refused | Complete verified A750 UBWC catalog facts |
| Import 16 | Refused | Task-owned wiring and CPU/GPU exclusion |
| Other methods | Refused | Translate only after individual contract evidence |

IOKit client creation and Turnip/Metal publication remain absent; the cdev is an isolated adapter qualification transport, not a replacement for upstream IOKit discovery.
