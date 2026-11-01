"""Summarize actual Mesa no-op frontend requests; explicitly no GPU evidence."""
from pathlib import Path
import argparse,json,collections,struct,hashlib,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
rows=[json.loads(l) for l in args.trace.read_text().splitlines()]
alloc=[r for r in rows if r.get('nr')==0x42 and r['ret']==0];subs=[r for r in rows if r.get('nr')==0x46]
assert subs and all(s['nr_bos']>=1 for s in subs)
xml=ET.parse(root/'xnu-deps/build/mesa/mesa-26.3.0-rc1/src/freedreno/registers/adreno/adreno_pm4.xml')
names={int(v.get('value'),0):v.get('name') for v in xml.iter() if v.tag.endswith('value') and v.get('value','').startswith('0x') and v.get('name','').startswith('CP_')}
commands=[]
for path in sorted(args.trace.parent.glob(args.trace.name+'-submit-*-cmd-*.bin')):
 b=path.read_bytes();assert len(b)%4==0;words=struct.unpack('<%dI'%(len(b)//4),b);at=0;packets=[];ops=collections.Counter();nested=[]
 while at<len(words):
  h=words[at];typ=h>>28
  if typ==7:
   n=h&0x3fff;op=h>>16&0x7f;name=names.get(op,hex(op));ops[name]+=1
   if op==0x3f:
    assert n>=3;nested.append({'gpu_va':hex(words[at+1]|words[at+2]<<32),'words':words[at+3]})
  elif typ==4:n=h&127;name='type4_reg_'+hex(h>>8&0x3ffff)
  else:raise RuntimeError('Unknown PM4 packet at '+str(at))
  assert at+1+n<=len(words);packets.append({'word':at,'type':typ,'name':name,'payload_words':n});at+=1+n
 commands.append({'path':str(path),'bytes':len(b),'words':len(words),'packets':packets,'type7_opcodes':dict(ops),'nested_IBs':nested,'sha256':hashlib.sha256(b).hexdigest()})
result={'experiment':'E34 actual Mesa FD750 GL frontend architecture gap audit','host_only':True,'gpu_execution':False,'pixel_correctness_tested':False,'frontend':'actual EGL/GLES3 Gallium FD750 triangle16x16','adapter':'stock freedreno_noop_drm_shim; SUBMIT is no-op','allocation_events':len(alloc),'requested_BO_sizes':dict(collections.Counter(str(r['size']) for r in alloc)),'requested_BO_flags':dict(collections.Counter(hex(r['flags']) for r in alloc)),'submits':subs,'commands':commands,'first_required_unsupported_interface':'MSM GET_PARAM GPU_ID/GMEM_SIZE/CHIP_ID, not implemented in current diagnostic cdev; preceding cached-coherent probe may be refused as unsupported','first_real_memory_gap':'actual GL submission references13 BOs; current diagnostic exposes two fixed16KiB handles. GL startup requests4KiB/8KiB/4MiB BOs and WC/readonly/cached-coherent flags','command_gap':'actual root IB310words with5 nested IBs and draw-state packets; current kernel only accepts exact191word compute package','implementation_order':['real context parameter queries from board-verified values','general owned BO registry with pagewise mappings, sizes and flags; retain lifetime until GPU idle/stop','general ordered command submission and GPU fence wrapper; audited graphics PM4','actual GL triangle GPU pixel test before IOSurface integration'],'evidence_sha256':hashlib.sha256(args.trace.read_bytes()).hexdigest()}
args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['host_only','gpu_execution','allocation_events','requested_BO_sizes','first_real_memory_gap','command_gap']},indent=2))
