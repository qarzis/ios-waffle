#!/usr/bin/env python3
from pathlib import Path
import tempfile,sys,hashlib
r=Path(__file__).resolve().parents[2];sys.path.insert(0,str(r/'tools'));from waffle_log_stream import merge_run_logs
header=b'one payload identity\n'.ljust(256,b' ')
body=b''.join(hashlib.sha256(str(i).encode()).hexdigest().encode()+b'\n' for i in range(600))
with tempfile.TemporaryDirectory() as d:
 p=Path(d);first=header+body[:18000];second=header+body[:1024]+body[12000:26000];final=header+body[:1024]+body[20000:]
 (p/'kernel-1.log').write_bytes(first);(p/'kernel-2.log').write_bytes(second);(p/'kernel-final.log').write_bytes(final)
 result,proof=merge_run_logs(p);assert result==header+body and proof['bytes']==len(result)
 (p/'kernel-final.log').write_bytes(b'other'+final[5:])
 try:merge_run_logs(p)
 except ValueError:pass
 else:raise AssertionError('Another payload accepted')
 (p/'kernel-final.log').write_bytes(header+body[30000:])
 try:merge_run_logs(p)
 except ValueError:pass
 else:raise AssertionError('Gap accepted')
print('PASS strict log stream: byte-exact rolling snapshot recovery, different payload and missing overlap refused; synthetic only.')
