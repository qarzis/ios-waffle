# Verified OnePlus 12 GPU checkpoint: E21

The first compute shader executed on Adreno 750 under XNU. Eight local invocations wrote 0–7 to an SSBO, the GPU control fence reached 1, and all 4,096 buffer words matched. The prepare-only test used the same stream with CP_EXEC_CS replaced by NOP and correctly left the output poisoned. Both runs completed full shutdown and returned to Android.

- Default control: `20261031T212802Z`, 27 access checks and 42 LPAC translations.
- Compute preparation: `20261031T212939Z`, no shader dispatch.
- Shader execution: `20261031T213222Z`, eight correct results.
- Evidence: [E21 result](forensic-audit/E21-result.json), [prepare result](forensic-audit/E21-prepare-result.json).
- Shader source: [invocation test](../../../tools/tests/fixtures/waffle-invocation-8.asm).

E19 verified full GPU resource ownership with the AOP mailbox mutex released during GPU work. E20 verified GPU fetch/write through a BO allocated and mapped after bootstrap. Tests are bounded cold sessions; reopening without an Android reset is unqualified.

Next: a compute-generated offscreen pixel pattern, then presentation and the production userspace buffer/submission/fence backend. No image, iOS hardware composition, Metal or IRQ recovery is claimed by E21. The iOS interface still uses softpipe.
