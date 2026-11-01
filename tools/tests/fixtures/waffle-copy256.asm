@localsize 256, 1, 1
@buf 512
@invocationid(r0.x)
mov.u32u32 r2.x, 256
(rpt5)nop
add.u r0.y, r0.x, r2.x
(rpt5)nop
ldib.b.untyped.1d.u32.1.imm r1.x, r0.y, 0
(sy)nop
(rpt5)nop
stib.b.untyped.1d.u32.1.imm r1.x, r0.x, 0
end
nop
