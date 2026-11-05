# H08: first source-backed capability blocker

H05 actual motor/PCM bridge works. H07B CHHapticEngine.capabilitiesForHardware.supportsHaptics=0; public player can return success with no HAL Actuator output.

Pinned local iOS16.5 shared-cache metadata: CHDefaultHapticDeviceCapability initPrivate at1af4f1c90 calls AVHapticPlayer supportsHaptics; AVHapticPlayer cached query at1af52b924 ultimately calls1af509bb0, which passes CFString at1d8906a48 to MGGetBoolAnswer (resolved target19c527bdc in libMobileGestalt). String gqDnklGQnpv5ilgh5uHckw exactly equals unpaddedBase64(MD5("MGCopyAnswerDeviceSupportsClosedLoopHaptics")). This is a hardware identity query, not a GPU/motor amplitude check.

loader/identity.h already contains actual generated product/haptics properties closed-loop=1/supports-3rd-party-haptics=1. Waffle loader emitted product identity then ended product without emitting haptics. Pinned Corvette loader explicitly emits this node and documents Actuator-vs-legacy-IOKit selection; pre-existing upstream notes independently agree.

Minimal H08 change emits existing identity_haptics inside product ONLY for valid dedicated haptic_test2 service requests; default/read-only/one-shot boots do not acquire the claim. No Apple framework method hook or forced capability return. The PCM service has qualified tap approximation, not continuous waveform fidelity. Runtime verification still needed: capability becomes1 AND actual Actuator PCM reaches motor; identity alone is not success.

Actual product-block host fixture verifies nested node/two little-endian values, dedicatedbuildonly/validservicepolicy and exclusions. Loader policy fixture passesbase/user/pulse variants. No device test during user's15-minute phone absence. Next build loader/root and pairvalidate, then wait for renewed phone availability; do not auto-contact USB merely because timeout elapsed.
