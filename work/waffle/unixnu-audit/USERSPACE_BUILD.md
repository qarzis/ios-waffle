# UniXNU graphics userspace: ARM64 / iOS 16.5

Built on Linux on 2026-11-06 without using the phone. The actual linked bundle is `work/waffle/unixnu-build/NativeAdrenoMetal.bundle/`: 25,561,256-byte Metal executable plus 17,865,960-byte Turnip library. Both are Mach-O ARM64, platform iOS, minimum OS16.5. The Metal principal class and `native_bridge_metal_open`, and Turnip's `vk_icdGetInstanceProcAddr`, are defined. Exact hashes/dependencies/source identities are in USERSPACE_BUILD_RESULT.json.

This is a complete userspace link, not a hardware or SpringBoard result. It has not been installed or trusted on the phone.

## Reused sources

- UniXNU core e2fdae4312d0acc3d8a52bc457101e7918095e6a.
- AdrenoMetal 6416a76e0a287d85afbcddda21192388460e155c.
- Mesa 85fda3b36405bcaea8bffc64aa4f2651dc90770d, all17 patches from the pinned adreno-compiler-inputs.json. One patch needed explicit new-file mode metadata for forward git apply; the original upstream reverse-patch identity guard passed unchanged.
- metal2vulkan 624bab3918de5b978e1101517abca2b4fa426565, all30 patches from the upstream bridge builder. Source tree/cache runtime ID is recorded in the result.
- AdrenoPM4 and GopFramebuffer wire header at the core's exact gitlinks.

The complete Rust bridge built with Rust1.98.0 for aarch64-apple-ios, deployment16.5, release/fat-LTO. Toolchain installation stayed under the ignored build directory; no global Rust configuration changed. No third-party binaries or Apple SDKs are committed.

## iOS16 source compatibility

The actual frontend first failed compilation on MTLLanguageVersion3_1 and MTLBindingAccess, plus the diagnostic shared-event call's declaration. The SDK's maximum declared language is3.0; MTLBinding.access returns MTLArgumentAccess with values0/1/2. The private build selects default3.0 and aliases that existing SDK type. The wait selector is already implemented by UniXNU's own shared-event object; its test now calls it as id with an explicit declaration. No Apple method implementation or unknown type layout was invented. IOS16_FRONTEND.patch holds the two source edits; the build recipe emits the declaration header.

## Build commands

Prepared pinned reference checkout: `/home/qarzis/unixnu-reference`. Mesa and translator caches are required, as are the local iPhoneOS16.5 SDK, existing Darwin compiler, upstream-generated smoke shaders, pinned Python requirements, and the private Rust toolchain. Build output is never installed automatically.

```
python3 tools/build-waffle-unixnu-userspace.py --stage turnip
python3 tools/build-waffle-unixnu-userspace.py --stage frontend
python3 tools/build-waffle-unixnu-userspace.py --stage bridge
python3 tools/build-waffle-unixnu-userspace.py --stage bundle
```

Actual final logs: unixnu-build/turnip-build-final.log, frontend/*-build.log, bridge-build-final.log, bundle-link.log. The bundle stage checks architecture, load commands, minimum OS and required exports and emits userspace-build-result.json.

## Runtime integration still required

Turnip's actual dw_open_connection opens IOAcceleratorES/type0x4147 (or NativeAdrenoGpuPublished/type0) through IOKit, queries ABI2 and DeviceInfo, and uses IOConnectMapMemory64 with native CPU tokens. The current port's U01–U04 implementation is a private PID1 cdev, not that service. Ordinary IOAcceleratorES in MiniIOMobileFramebuffer.cpp currently only publishes an IOService; it does not forward NativeAdreno methods.

Required next work: reuse/adapt the actual IOKit user-client lifetime and CPU-view implementation; bind verified A750 DeviceInfo/UBWC facts; support the 4KiB GPU VA allocation contract or adapt its granularity explicitly; remove diagnostic-only queue/fence-history limits for sustained operation. Unknown capability fields must stay refused. Do not replace these with successful stubs or publish the Metal plugin globally before a controlled device test.

The existing working A750 hardware initialization and ordinary Mesa path were not changed during this userspace build. No FPS claim or phone request is justified by a successful link alone.
