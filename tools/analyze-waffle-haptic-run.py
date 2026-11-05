#!/usr/bin/env python3
"""Summarize retained haptic trace without treating request ACKs as physical output."""
import argparse,json,re,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('trace',type=Path);a=p.parse_args();raw=a.trace.read_bytes()
lines=raw.decode(errors='replace').splitlines()
# The loader channel and later timestamped printf dump can contain the same
# event twice. Preserve raw bytes, count only the direct loader records.
text='\n'.join(x for x in lines if not re.match(r'^\[\s*\d+\.\d+\]:',x))
starts=text.count('haptic-waffle-pulse: passed=1 admitted=1 start=1')
stops=text.count('haptic-waffle-pulse: stopped=1 restored=1 emergency=0 writes=7')
failed=bool(re.search(r'haptic-waffle-pulse: passed=0|haptic-waffle-service:.*failed=1',text))
hal=re.findall(r'(?:redwood|hakios): audio: the actuator plays: (\d+) frames, peak (\d+) of 32768([^\n]*)',text)
result={'source':str(a.trace),'source_sha256':hashlib.sha256(raw).hexdigest(),'capabilities':[int(x) for x in re.findall(r'CoreHaptics_supports=(\d+)',text)],'player_returns':re.findall(r'CoreHaptics_play=(\d+) error=(-?\d+)',text),'completed_pulses':starts,'confirmed_stop_restore':stops,'active_us':[int(x) for x in re.findall(r'haptic-waffle-pulse: active_us=(\d+)',text)],'direct_client_results':re.findall(r'direct_taps=(\d+) errors=(\d+)',text),'HAL_actuator_samples':[{'frames':int(f),'peak':int(peak),'sink_available':'not felt' not in tail} for f,peak,tail in hal],'fault_or_quarantine':failed,'system_route_claim':'Requires capability plus actual HAL samples with available sink; player success alone insufficient','trace_component_consistent':starts==stops and not failed}
print(json.dumps(result,indent=2))
