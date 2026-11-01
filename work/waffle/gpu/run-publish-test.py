"""Session runner; return Android after each RAM GPU probe where USB survives."""
import subprocess,json,time,datetime,sys
from pathlib import Path
fb='/home/qarzis/platform-tools/fastboot';adb='/home/qarzis/platform-tools/adb'
probe=int(sys.argv[1]);assert probe in (33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94)
artifact=Path(sys.argv[2] if len(sys.argv)>2 else 'work/waffle/diagnostic-gpu-raw-publish36')
options=set(sys.argv[3:]);assert len(options)==len(sys.argv[3:])
assert options<={'--ui-long-test','--ui-workload','--gl-context','--mapped','--mesa-transport','--msm','--user-va','--glsl','--data-bo','--user-copy','--worker','--copy-jobs','--image-present','--image-copy','--image','--compute-prepare','--compute-dispatch','--dynamic-bo','--access-matrix','--measure-clocks','--lpac-map','--zap','--writeback','--ib','--session'}
if '--ui-long-test' in options:assert {'--ui-workload','--gl-context'}<=options
access_matrix='--access-matrix' in options
measure_clocks='--measure-clocks' in options
lpac_map='--lpac-map' in options
zap='--zap' in options
writeback='--writeback' in options
ib='--ib' in options
session='--session' in options
dynamic_bo='--dynamic-bo' in options
compute=1 if '--compute-prepare' in options else 2 if '--compute-dispatch' in options else 0
assert not {'--compute-prepare','--compute-dispatch'}<=options
assert len(options & {'--gl-context','--image','--image-copy','--image-present','--copy-jobs','--worker','--user-copy','--data-bo','--glsl','--user-va','--msm'})<=1
image=13 if '--gl-context' in options else 12 if '--mapped' in options else 11 if '--msm' in options else 10 if '--user-va' in options else (9 if compute==1 else 8) if '--glsl' in options else 7 if '--data-bo' in options else 6 if '--user-copy' in options else 5 if '--worker' in options else 4 if '--copy-jobs' in options else 3 if '--image-present' in options else 2 if '--image-copy' in options else int('--image' in options)
assert '--mapped' not in options or {'--msm','--mesa-transport'}<=options
assert '--mesa-transport' not in options or image in (11,12)
assert not image or compute
assert image<3 or image==9 or compute==2
assert not compute or dynamic_bo
assert not dynamic_bo or (session and probe==94)
assert not options or (probe==93 and not zap and not writeback and not ib and not session) or (probe==94 and (options-{'--ui-long-test','--ui-workload','--gl-context','--mapped','--mesa-transport','--image','--image-copy','--image-present','--copy-jobs','--worker','--user-copy','--data-bo','--glsl','--user-va','--msm'}) in ({'--lpac-map'},{'--lpac-map','--zap'},{'--lpac-map','--zap','--writeback'},{'--lpac-map','--zap','--writeback','--ib'},{'--lpac-map','--zap','--writeback','--ib','--session'},{'--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo'},{'--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-prepare'},{'--lpac-map','--zap','--writeback','--ib','--session','--dynamic-bo','--compute-dispatch'}))
before=set(Path('work/waffle/runs').iterdir())
report={'probe':probe,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
if access_matrix:report['variant']='E03-access-matrix-no-RAW'
if measure_clocks:report['variant']='E06-clock-measure-no-RAW'
if lpac_map:report['variant']='E07-LPAC-map-no-RAW' if probe==93 else 'E08-LPAC-map-CP_INIT'
if zap:report['variant']='E09-ZAP-native-secure-transition'
if writeback:report['variant']='E10-guarded-GPU-memory-writeback'
if ib:report['variant']='E11-indirect-command-buffer-fetch'
if session:report['variant']='E12-owned-multisubmit-session'
if dynamic_bo:report['variant']='E20-post-bootstrap-dynamic-BO'
if compute:report['variant']=f'E21-compute-mode{compute}'
if image:report['variant']=f'E{31 if image==11 else 30 if image==10 else 29 if image>=8 else 28 if image==7 else 27 if (6<=image<=8 or image in (10,11,12)) else 26 if image==5 else 25 if image==4 else 24 if image==3 else 23 if image==2 else 22}-image-mode{compute}'
if '--mesa-transport' in options:report['variant']='E32-actual-Mesa-DRM-shim'
if '--mapped' in options:report['variant']='E33-mapped-GPU-BOs'
if '--ui-workload' in options:assert '--gl-context' in options
if '--gl-context' in options:report['variant']='E36-actual-Darwin-OSMesa-GL'
try:
 with (artifact/f'hardware-host-{probe}.log').open('w') as log:
  result=subprocess.run(['python3','scripts/run_waffle_ios.py','--kernel',str(artifact/'kernel'),'--root',str(artifact/'gl-probe/root.packfs') if image==13 else str(artifact/('mapped-probe/user-probe.packfs' if image==12 else 'msm-probe/user-probe.packfs' if image==11 else 'user-probe/user-probe.packfs')) if (6<=image<=8 or image in (10,11,12)) else 'work/waffle/gpu/probe-firmware-system.packfs','--system','work/waffle/images/system.packfs' if image==13 else str(artifact/('mapped-probe/user-probe.packfs' if image==12 else 'msm-probe/user-probe.packfs' if image==11 else 'user-probe/user-probe.packfs')) if (6<=image<=8 or image in (10,11,12)) else 'work/waffle/gpu/probe-firmware-system.packfs','--seconds','300' if '--ui-long-test' in options else '90' if probe>=77 else '30','--gpu-probe',str(probe),*(['--gpu-access-matrix'] if access_matrix else []),*(['--gpu-measure-clocks'] if measure_clocks else []),*(['--gpu-lpac-map'] if lpac_map else []),*(['--gpu-zap'] if zap else []),*(['--gpu-writeback'] if writeback else []),*(['--gpu-ib'] if ib else []),*(['--gpu-session'] if session else []),*(['--gpu-dynamic-bo'] if dynamic_bo else []),*(['--gpu-compute',str(compute)] if compute else []),*(['--gpu-ui'] if '--ui-workload' in options else []),*(['--gpu-mapped'] if '--mapped' in options else []),*(['--gpu-mesa-transport'] if '--mesa-transport' in options else []),*(['--gpu-gl-context' if image==13 else '--gpu-msm' if image in (11,12) else '--gpu-user-va' if image==10 else '--gpu-glsl' if image>=8 else '--gpu-data-bo' if image==7 else '--gpu-user-copy' if image==6 else '--gpu-worker' if image==5 else '--gpu-copy-jobs' if image==4 else '--gpu-image-present' if image==3 else '--gpu-image-copy' if image==2 else '--gpu-image'] if image else [])],stdout=log,stderr=subprocess.STDOUT,timeout=700 if '--ui-long-test' in options else 360 if image==13 else 180)
 report['runner_exit']=result.returncode
except Exception as e:report['exception']=str(e)
finally:
 report['runs']=[str(p) for p in sorted(set(Path('work/waffle/runs').iterdir())-before)]
 runs=[Path(p) for p in report['runs']]
 # An accepted loader run proves transfer and launch, not GPU execution.
 report['hardware_tested']=any('oem run 0\nOKAY' in (p/'host.log').read_text(errors='replace')
                               for p in runs if (p/'host.log').is_file())
 kernel_logs=[log for p in runs for log in p.glob('kernel-*.log')]
 report['kernel_probe_started']=(any('waffle-gpu:' in log.read_text(errors='replace') or
                                     'waffle-gmu:' in log.read_text(errors='replace') or
                                     'waffle-iommu:' in log.read_text(errors='replace')
                                     for log in kernel_logs) if kernel_logs else
                                 None if report['hardware_tested'] else False)
 try:
  devices=subprocess.run([fb,'devices'],capture_output=True,text=True,timeout=5).stdout
  report['fastboot_after']=devices
  if 'xnuloader' in devices:
   reboot=subprocess.run([fb,'-s','xnuloader','reboot'],capture_output=True,text=True,timeout=15)
   report['android_reboot_sent']=reboot.returncode==0
 except (OSError,subprocess.SubprocessError) as e:report['fastboot_after_error']=str(e)
 report['android_confirmed']=False
 for attempt in range(40):
  try:
   state=subprocess.run([adb,'-s','1c62e9aa','shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=5)
   if state.returncode==0 and state.stdout.strip()=='1':report['android_confirmed']=True;break
  except (OSError,subprocess.SubprocessError) as e:report['adb_error']=str(e)
  time.sleep(1)
 (artifact/f'hardware-result-{probe}.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 sys.exit(0 if report.get('runner_exit')==0 and report['android_confirmed'] else 1)
