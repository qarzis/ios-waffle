# V01 — inherited hardware timing survey

User deferred brightness and explicitly prioritizes VSync. Current software thread-call notifications and direct writes into inherited scanout do not synchronize with actual panel TE. SwapWait currently returns immediately; queue slot retirement also precedes CPU composition.

Hypotheses (max three):
1. The native INTF tear/frame counters progress under inherited UEFI configuration and can supply a measurable hardware phase. Test only reads configuration, counts and timestamps. Expected one or more active interfaces with coherent counter progression. Refute usable-counter hypothesis if all disabled/static; do not enable unknown blocks just to obtain a number.
2. DPU is scanning a buffer while CPU composition writes into it. Hardware phase alone may be insufficient when a full copy does not fit the blanking interval. Need actual active SSPP/CTL and DPU device address before qualifying a second buffer mapping/atomic flip.
3. Correct completion and queue lifetime ordering is missing independently of TE. First establish timing and drawing completion; do not claim changing callback frequency fixes presentation.

Chosen experiment H1 has native live-DT register provenance and no new hardware writes. Pure callback snapshot reads MDSS version,4INTF,6CTL,10SSPP; INTF-only32samples separated by IOSleep(2) include mach_absolute_time bounds. Reads do not acknowledge IRQs, enable timestamp counters or change refresh. Timestamp low/high read is a raw non-atomic observation, not a qualified timestamp until rollover/stability is checked. Counter progress is not proof of TE GPIO IRQ delivery. SSPP address is DPU device address, not assumed physical address.

DPU baseae00000/84000 from native live DT; version and offsets from OnePlus modules38d50357db2728300a61b6f757f2d3a09651c155 sde_hw_intf/ctl/sspp/catalog. src_blk base remains zero in zero-initialized native catalog. No inferred clocks/resets/DSI commands/IRQ masks are changed. Read inherited powered display only.

Host ASanUBSan actual callback header validates every read failure, native offset decoding, region bounds and INTF-only progression captures; loader policies reject duplicated flag/audio mixture/nonuserland. Full XNU/pairedUEFI build passed after local include path correction. Runtime flag defaultOFF. Fresh image/source snapshots/UI hashes verified, artifact validated. UI E113 hook unchanged; no visual synchronization modification. Android independently1 beforelaunch. Original collector failures must remain preserved.
