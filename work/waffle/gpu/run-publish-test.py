"""Session runner; return Android after each RAM GPU probe where USB survives."""
import subprocess,json,time,datetime,sys
from pathlib import Path
fb='/home/qarzis/platform-tools/fastboot';adb='/home/qarzis/platform-tools/adb'
probe=int(sys.argv[1]);assert probe in (33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94)
artifact=Path(sys.argv[2] if len(sys.argv)>2 else 'work/waffle/diagnostic-gpu-raw-publish36')
access_matrix=len(sys.argv)>3 and sys.argv[3]=='--access-matrix'
assert len(sys.argv)<=4 and (len(sys.argv)<4 or access_matrix)
assert not access_matrix or probe==93
before=set(Path('work/waffle/runs').iterdir())
report={'probe':probe,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
if access_matrix:report['variant']='E03-access-matrix-no-RAW'
try:
 with (artifact/f'hardware-host-{probe}.log').open('w') as log:
  result=subprocess.run(['python3','scripts/run_waffle_ios.py','--kernel',str(artifact/'kernel'),'--root','work/waffle/gpu/probe-firmware-system.packfs','--system','work/waffle/gpu/probe-firmware-system.packfs','--seconds','90' if probe>=77 else '30','--gpu-probe',str(probe),*(['--gpu-access-matrix'] if access_matrix else [])],stdout=log,stderr=subprocess.STDOUT,timeout=180)
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
