# Metal port: pinned source gap review

Read-only audit of hakios-metal commit
`642fe419ab703f89f341e9ce83e01a39ca0996ec` in the local checkout.
The 259 passing tests use its fake A6xx GPU and committed shader fixtures with
MESA compiler disabled. They do not establish A750 Metal support.

| Component | Pinned upstream | Current waffle | Required work |
| --- | --- | --- | --- |
| Device transport | `src/iokit_transport.cpp`: HakiosGPU IOKit service, struct-method selectors, IOConnectMapMemory64 | gated `/dev/waffle-gpu-drm`, encoded ioctl plus explicit MAP/UNMAP requests | Dedicated transport using the implemented ABI; preserve errno, owner lifetime and mappings |
| Pipe encoding | `gpu.hpp` kPipe3D=1, used for PARAM and SUBMIT | actual cdev requires pipe/flags 0x10 | Explicit conversion or target-specific constant, tested against actual endpoint; layouts matching is insufficient |
| Request layouts | legacy MSM BO, command, fence and queue structures | corresponding MSM structures already checked against pinned Mesa UAPI | Check offsets and sizes against both actual headers before adapter work |
| Surface import | custom selector0x7e HakiosSurface | absent in general waffle cdev | Initially offscreen owned BOs; surface sharing needs its own proven kernel memory path |
| GPU identity/compiler | fixed A6xx chip06030500 in a6xx.hpp and compiler.cpp | live target chip43051401, Mesa FD750 | A750 device selection AND generation-specific compiler/packet/layout audit |
| AIR frontend | compiler.cpp includes nir_air.h; compiler.mk needs libair.a and upstream AIR source | neither nir_air.h nor AIR source found in the current main Mesa source/compiler or tools/mesa tree | Obtain/verify actual upstream frontend and compatible source/build dependencies; no invented substitute |
| Draw/dispatch packets | A6xx register/descriptors and committed A635 machine code | qualified A750 Mesa/compute paths | Rebuild shaders for A750, derive register/program state from the matching primary Mesa source and actual qualified streams |
| Root command length | Gpu::submit emits one root of arbitrary recorded size | whole root must fit1536words, metadata bounded16KiB | Explicit bounded packet-preserving submission design or honest refusal; never truncate |
| Process ownership | Metal objects open upstream IOKit client | one current cdev context, exact owning PID; second open returns EBUSY | Qualify Metal in isolated process first; shared compositor/app GPU ownership needs an architectural solution |
| Fault reporting | Gpu::faults silently returns0 on PARAM9 failure | PARAM9 unsupported | Preserve unsupported/error semantics; do not pretend reset detection exists |

First port milestone after sustained UI baseline: an isolated target transport
and small CP fill/copy with actual buffer/fence/reference checks. Then one
A750-compiled compute shader, one pixel-reference draw, then actual Metal plugin
objects and IOSurface integration. Concurrent app/compositor operation is a
separate ownership/state task; compiling the Objective-C plugin alone will not
make it work.

No Metal source change or A750 Metal hardware test has been performed here.
