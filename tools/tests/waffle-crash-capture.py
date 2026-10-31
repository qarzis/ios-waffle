#!/usr/bin/env python3
"""No-device checks: crash capture refuses Android/9008/foreign/ambiguous USB."""
from pathlib import Path
import importlib.util
import tempfile
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('capture', ROOT/'tools/capture-waffle-crash.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
def device(vid='05c6',pid='900e',serial='1C62E9AA',product='QUSB_BULK_CID:0448_SN:1C62E9AA'):
    return dict(vid=vid,pid=pid,serial=serial,product=product,path='mock')
assert capture.eligible([device()])
assert capture.eligible([device(serial='',product='QUSB_BULK_CID:0448_SN:1C62E9AA')])
for items in [[],[device(vid='22d9',pid='2769')],[device(pid='9008')],
              [device(serial='foreign',product='QUSB_BULK')],[device(serial='',product='QUSB_BULK')],
              [device(),device(serial='foreign')],[device(),device(pid='9008')]]:
    assert capture.eligible(items) is None
args=capture.command(device(),Path('/tmp/mock-only'))
assert args[1:3]==['ramdump','--backend'] and args[-1]==capture.SEGMENTS
assert '--serial' in args and '1C62E9AA' in args
assert capture.command(device(serial='6716d0bd'),Path('/tmp/mock-only'))==args
try:
    capture.command(device(product='QUSB_BULK'),Path('/tmp/mock-only'))
except ValueError:
    pass
else:
    raise AssertionError('Missing iProduct serial must refuse the USB operation')
assert all(word not in args for word in ['flash','erase','write','reset','--loader'])
assert not any(x in capture.SEGMENTS.lower() for x in ['ddr','dram','*','?'])
assert 'md_TZ_DIAG' in capture.SEGMENTS.split(',')
assert 'md_MSGRAM15' in capture.SEGMENTS.split(',')
assert not any(x in capture.SEGMENTS.lower() for x in ['aes_key','hmac','wrpd_keys','encr_iv'])
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);p=base/'3-4';p.mkdir()
    for key,value in [('idVendor','05c6'),('idProduct','900e'),('serial','1C62E9AA')]:
        (p/key).write_text(value+'\n')
    assert capture.eligible(capture.devices(base))
print('Crash-capture no-device guards, serial binding and fixed small-segment RAM-only command passed')
