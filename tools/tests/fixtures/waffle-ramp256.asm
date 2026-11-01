@localsize 256, 1, 1
@buf 256
@invocationid(r0.x)
mov.u32u32 r1.y, 0xff000000
(rpt5)nop
or.b r1.x, r0.x, r1.y
(rpt5)nop
stib.b.untyped.1d.u32.1.imm r1.x, r0.x, 0
end
nop
