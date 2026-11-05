"""Decode complete compact display records; no truncated-field inference."""
import re
def normalize(text):
    if '!dph:error!' in text:raise ValueError('Display packet formatter overflow')
    heads=re.findall(r'!dph:v1/([0-9a-f]+)/([0-9a-f]+)/([0-9a-f]+)/1!',text)
    if not heads or len(set(heads))!=1:raise ValueError('Missing/conflicting compact display header')
    count,hz,writes=(int(v,16) for v in heads[0])
    if not 1<=count<=128 or hz<=0 or not 0<=writes<=8:raise ValueError('Invalid compact display bounds')
    parts={};probe={};sizes={'a':7,'b':6,'c':5,'d':6,'p':7}
    for m in re.finditer(r'!dp([abcdp]):([0-9a-f/]+)!',text):
        if len(m[0])>=64:raise ValueError('Oversized compact display record')
        kind,payload=m.groups();v=payload.split('/')
        if len(v)!=sizes[kind] or any(not x for x in v):raise ValueError('Malformed display packet')
        n=tuple(int(x,16) for x in v);index=n[0]
        if not 0<=index<count:raise ValueError('Display packet outside record bound')
        target=probe if kind=='p' else parts;key=index if kind=='p' else (index,kind)
        if key in target and target[key]!=n:raise ValueError('Conflicting display packet replay')
        target[key]=n
    if set(parts)!={(i,k) for i in range(count) for k in 'abcd'}:raise ValueError('Missing compact display packet')
    out=[f'waffle-display-completion: records={count} no_extra_writes={int(not writes)} guard_frames=2 cntfrq={hz}',f'waffle-display-irq-probe: enabled=1 writes={writes} clear_offset=1018 clear_mask=100 guard_frames=2 mode_change=0 irq_enable_writes=0']
    for i in range(count):
        _,seq,stage,ticks,f0,f1,valid=parts[i,'a'];_,flush,scheduler,auto,write,read=parts[i,'b'];_,a,b,top,enable=parts[i,'c'];_,ctl,ctl_en,tear,tear_en,active=parts[i,'d']
        if valid not in (0,1):raise ValueError('Invalid display validity bit')
        out.append(f'waffle-display-completion: row={i} seq={seq} stage={stage} ticks={ticks} valid={valid} frame0={f0} frame1={f1} flush={flush:x} scheduler={scheduler:x} auto_status={auto:x} write_line={write} read_line={read} address0={a:x} address1={b:x}')
        out.append(f'waffle-display-irq: row={i} top_status={top:x} top_enable={enable:x} ctl_status={ctl:x} ctl_enable={ctl_en:x} tear_status={tear:x} tear_enable={tear_en:x} active={active:x}')
        if i in probe:
            _,pseq,action,wrote,after,mux,version=probe[i]
            out.append(f'waffle-display-irq-probe: row={i} seq={pseq} action={action} wrote={wrote} status_after={after:x} mux={mux:x} version={version:x}')
    return '\n'.join(out)+'\n'
