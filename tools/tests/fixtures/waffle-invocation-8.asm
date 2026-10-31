@localsize 8, 1, 1
@buf 8
@invocationid(r0.x)
mov.u32u32 r1.x, r0.x
(rpt5)nop
stib.b.untyped.1d.u32.1.imm r1.x, r0.x, 0
end
nop
