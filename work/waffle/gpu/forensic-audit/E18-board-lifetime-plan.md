# Remaining board lifetime after E17 (plan, not an implementation result)

The SMMU and clock journals can return live, but the diagnostic still owns
CX and CFG_AHB in `waffle_adreno.c:probe_cx` and `probe_gpu_body` locals.
`probe_aop_channel` owns stack QMP/IPCC callback storage and a shared mutex;
`waffle_aop_qmp_transaction_run` always sends ACD off after its GPU callback.
Returning from that callback with live GPU work would therefore drop ACD.

Next minimal experiment: an explicit board parent for saved CFG enable/gating,
CX collapse ownership, GCC/GPUCC mapping references and the existing clock
child. Begin returns with the child live; separate exercise and end must
complete GMU/SMMU/PLL/clock stop before CX/CFG restoration. Preserve both CX
branches: do not collapse a domain that was already powered by another owner;
restore only the acquired collapse bit and CFG control bits. Test partial
mapping/power/clock construction failure and exact reverse cleanup. Use the
same 93 control and three-IB94 sequence; no new PM4 or power constants.

AOP is a separate unresolved boundary, not a keep flag. The existing
`macan_aop_mailbox_lock` is also used by macan Wi-Fi and ADSP. Their mailbox
send functions lock only around transport, and Wi-Fi accepts an already-open
channel. A persistent waffle path must own QMP/IPCC callback storage and ACD
state while allowing bounded per-message lock ownership. Shared-channel close
policy and unknown on/off receipts must be explicit; an empty message length
proves transport receipt only. Do not infer ACD applied or power held from it.
The pinned vendor `adreno_gen7_gmu.c:gen7_gmu_aop_send_acd_state` uses existing
mbox_send_message and the exact padded ACD payload already implemented here.
No new Qualcomm/XNU API is needed or asserted by this plan.

`macan_input.c:redwood_input_init` currently selects waffle initialization and
returns before donor Wi-Fi/ADSP initialization. This explains current bounded
isolation, but does not establish a usable long-lived shared mailbox service.

After all board parents are owned, a persistent iOS backend still needs dynamic
BO mapping/publication, submit/completion, client lifetime and failure recovery.
Current module-static native clock state is serialized by one active clock
owner; no concurrent userspace or same-boot session reopen is qualified.
Do not publish readiness, switch Mesa from softpipe, or claim rendering based
on ownership-only tests. A shader/offscreen image needs separate GPU evidence.
