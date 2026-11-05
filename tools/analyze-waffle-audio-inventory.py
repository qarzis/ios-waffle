#!/usr/bin/env python3
"""Verify complete read-only SMMU inventory; never infer context ownership."""
import argparse,json,re
from pathlib import Path

def analyze(text,require_global=False):
 headers=re.findall(r'AUDIO_SMMU ids=(0x[0-9a-f]+)/(0x[0-9a-f]+)/(0x[0-9a-f]+) groups=(\d+) banks=(\d+) page_shift=(\d+) cb_base=(0x[0-9a-f]+) exids=([01]) complete=1',text)
 if not headers or len(set(headers))!=1:raise ValueError('Missing/conflicting SMMU geometry')
 fields=headers[0];id1=int(fields[1],16);exids=int(fields[7]);groups=int(fields[3]);banks=int(fields[4]);s2=(id1>>16)&255
 summaries=re.findall(r'AUDIO_INVENTORY v=1 groups=(\d+) banks=(\d+) stage2=(\d+) candidates=(\d+) ownership=0',text)
 if not summaries or len(set(summaries))!=1:raise ValueError('Missing/conflicting complete inventory')
 ng,nb,ns,nc=map(int,summaries[0])
 if (ng,nb,ns)!=(groups,banks,s2) or not 0<=s2<=banks<=255 or not 1<=groups<=255:raise ValueError('Inventory geometry mismatch')
 def rows(pattern):
  out={}
  records=re.findall(pattern,text)
  marker=pattern.split(' ')[0]+' '
  if text.count(marker)!=len(records):raise ValueError('Malformed inventory record')
  for record in records:
   key=int(record[0]);v=tuple(int(x,0) for x in record[1:])
   if key in out and out[key]!=v:raise ValueError('Conflicting replay')
   out[key]=v
  return out
 routes=rows(r'AUDIO_ROUTE i=(\d+) smr=(0x[0-9a-f]+|0) s2cr=(0x[0-9a-f]+|0)')
 contexts=rows(r'AUDIO_BANK cb=(\d+) referenced=([01]) sctlr=(0x[0-9a-f]+|0) candidate=([01])')
 if sorted(routes)!=list(range(groups)) or sorted(contexts)!=list(range(banks)):raise ValueError('Missing routes or banks')
 referenced=set()
 for smr,s2cr in routes.values():
  if not (s2cr&(1<<10) if exids else smr&(1<<31)):continue
  kind=(s2cr>>16)&3
  if kind==3:raise ValueError('Reserved route')
  if kind==0:
   cb=s2cr&255
   if cb>=banks:raise ValueError('Out-of-range translated bank')
   referenced.add(cb)
 candidates=[]
 for cb,(ref,sctlr,candidate) in contexts.items():
  expected=cb>=s2 and cb not in referenced and not(sctlr&1)
  if bool(ref)!=(cb in referenced) or bool(candidate)!=expected:raise ValueError('Bank classification mismatch')
  if candidate:candidates.append(cb)
 if len(candidates)!=nc or 'WAFFLE AUDIO_IOMMU OK' not in text or 'AUDIO_INVENTORY FAIL' in text:raise ValueError('Incomplete inventory completion')
 global_rows=re.findall(r'AUDIO_GLOBAL v=1 cr0=(0x[0-9a-f]+|0) acr=(0x[0-9a-f]+|0) clientpd=([01]) usfcfg=([01])',text)
 if (require_global or 'AUDIO_GLOBAL' in text) and (not global_rows or len(set(global_rows))!=1):raise ValueError('Missing/conflicting global SMMU state')
 global_state=None
 if global_rows:
  cr0,acr,pd,usf=(int(x,0) for x in global_rows[0])
  if pd!=bool(cr0&1) or usf!=bool(cr0&(1<<10)):raise ValueError('Global bit decode mismatch')
  global_state=dict(cr0=cr0,acr=acr,client_power_down=bool(pd),unmatched_stream_fault=bool(usf),ownership_qualified=False)
 return dict(global_state=global_state,read_only_inventory_valid=True,groups=groups,banks=banks,stage2_banks=s2,referenced_banks=sorted(referenced),disabled_unreferenced_candidates=candidates,ownership_qualified=False,dma_tested=False,pcm_tested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);p.add_argument('--require-global',action='store_true');a=p.parse_args();print(json.dumps(analyze(a.log.read_text(errors='replace'),a.require_global),indent=2))
