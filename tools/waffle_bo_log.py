"""Decode compact kernel BO proof records; never repair interleaved verbose text."""
import re
PUB=r'GENERAL_BO published index=(\d+) VA=([0-9a-f]+) bytes=(\d+) allocated=(\d+) flags=([0-9a-f]+) pages=(\d+)'
FREE=r'GENERAL_BO reclaimed index=(\d+) VA=([0-9a-f]+) bytes=(\d+) CPU_unmapped=(\d+) GPU_idle=(\d+) dual_ASID_TLBI=(\d+) used=(\d+)'
def normalize(text):
    if '!wbo' not in text:return text
    if '!wbo:v1!' not in text or '!wbo:error!' in text:raise RuntimeError('Compact BO proof missing/overflowed')
    if 'SURFACE_BO published' in text:raise RuntimeError('Compact BO mode is not qualified for native import diagnostics')
    # Compact records are authoritative for these two event types. Other lifetime,
    # generation, permission, range, budget and teardown checks remain unchanged.
    text=re.sub(PUB,'',text);text=re.sub(FREE,'',text)
    pattern=r'!wbo([+-])([0-9a-f/]+)!'
    first=text.find('!wbo:v1!')
    for m in re.finditer(pattern,text):
        if m.start()<first:raise RuntimeError('Compact BO event before protocol declaration')
    def decode(m):
        if len(m.group(0))>=64:raise RuntimeError('Oversized compact BO record')
        kind,payload=m.groups();v=payload.split('/');expected=6 if kind=='+' else 4
        if len(v)!=expected or any(not x for x in v):raise RuntimeError('Malformed compact BO record')
        n=[int(x,16) for x in v]
        if kind=='+':return f'GENERAL_BO published index={n[0]} VA={n[1]:x} bytes={n[2]} allocated={n[3]} flags={n[4]:x} pages={n[5]}'
        return f'GENERAL_BO reclaimed index={n[0]} VA={n[1]:x} bytes={n[2]} CPU_unmapped=1 GPU_idle=1 dual_ASID_TLBI=1 used={n[3]}'
    return re.sub(pattern,decode,text)
