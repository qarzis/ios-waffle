#!/usr/bin/env python3
"""Run the loader's UEFI power audit or baseline hold, then return Android.

Requires the user to have selected Boot iOS in the RAM-booted firmware image.
Default is read-only. --hold creates two dedicated NPA clients at the current
verified NOM256 baseline, kept until reset. Neither mode stages/launches XNU,
changes clock frequency or enables a clock.
"""
from pathlib import Path
import argparse,datetime,json,re,subprocess,time

ROOT=Path(__file__).resolve().parents[1]
FB='/home/qarzis/platform-tools/fastboot'
ADB='/home/qarzis/platform-tools/adb'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--hold',action='store_true',help='Request the observed NOM256 baseline via dedicated clients until reset')
    args=parser.parse_args()
    artifact=args.artifact.resolve()
    if not (artifact/'source/loader/waffle-power.h').is_file():
        raise SystemExit('Artifact has no saved firmware audit source')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'work/waffle/gpu'/('firmware-power-'+stamp)
    out.mkdir()
    report={'started_at':stamp,'output':str(out.relative_to(ROOT)),
            'flash_operations':False,'kernel_launched':False,'power_requests_issued':False,
            'hardware_tested':False,'android_confirmed':False}
    report['hold_mode']=args.hold
    def command(*items,timeout=15):
        result=subprocess.run([FB,'-s','xnuloader',*map(str,items)],capture_output=True,text=True,timeout=timeout)
        with (out/'host.log').open('a') as log:
            log.write(' '.join(map(str,items))+'\n'+result.stdout+result.stderr+'\n')
        return result
    try:
        identity=command('getvar','platform')
        if identity.returncode or 'platform: waffle' not in identity.stdout+identity.stderr:
            raise RuntimeError('Expected the waffle loader after Boot iOS')
        report['hardware_tested']=True
        report['power_requests_issued']=None if args.hold else False
        result=command('oem','waffle-power-hold' if args.hold else 'waffle-power')
        report['audit_exit']=result.returncode
        report['audit_reply']=result.stdout+result.stderr
    except (RuntimeError,OSError,subprocess.SubprocessError) as e:
        report['error']=str(e)
    finally:
        if report['hardware_tested']:
            try:
                command('oem','log')
                result=command('get_staged',out/'loader.log')
                report['log_exit']=result.returncode
            except (OSError,subprocess.SubprocessError) as e:report['log_error']=str(e)
            try:
                result=command('reboot')
                report['android_reboot_sent']=result.returncode==0
            except (OSError,subprocess.SubprocessError) as e:report['reboot_error']=str(e)
        for attempt in range(60):
            try:
                result=subprocess.run([ADB,'-s','1c62e9aa','shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=3)
                if result.returncode==0 and result.stdout.strip()=='1':
                    report['android_confirmed']=True;break
            except (OSError,subprocess.SubprocessError):pass
            time.sleep(1)
        text=(out/'loader.log').read_text(errors='replace') if (out/'loader.log').is_file() else ''
        if args.hold and text:
            report['power_requests_issued']='FW_HOLD request resource=' in text
        report['read_only_complete']='FW_POWER read-only audit complete=1 npa_core_queries=6 clock_core_queries=2; no requests issued' in text
        report['hold_verified']='FW_HOLD verified CX=100 MX=100; dedicated clients retained until reset; no clock writes' in text
        report['hold_rows']=[line for line in text.splitlines() if 'FW_HOLD ' in line]
        report['resource_rows']=[line for line in text.splitlines() if 'FW_POWER NPA resource=' in line]
        report['clock_rows']=[line for line in text.splitlines() if 'FW_POWER CLOCK name=' in line]
        report['passed']=bool(report.get('audit_exit')==0 and report.get('log_exit')==0 and (report['hold_verified'] if args.hold else report['read_only_complete']) and report['android_confirmed'])
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        (artifact/'firmware-power-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__':main()
