from pathlib import Path
import json,hashlib,shutil,subprocess,os
r=Path('/home/qarzis/ios-macan');base=r/'work/waffle/diagnostic-haptic-worker-h09';out=r/'work/waffle/diagnostic-haptic-gpu-ui-h10';mu=r/'work/waffle/mu-hakios'
assert not out.exists();shutil.copytree(base,out)
source=json.loads((base/'manifest.json').read_text());old=json.loads((r/'work/waffle/diagnostic-quiet-ui-d22/manifest.json').read_text())
for n in ['kernel/files/bsd/dev/macan_torch.c','kernel/files/bsd/sys/waffle_haptic_readonly.h','kernel/files/bsd/sys/waffle_haptic_pulse.h','kernel/files/bsd/sys/waffle_haptic_events.h']:
 assert (r/n).read_bytes()==(base/'source'/n).read_bytes(),n
header=out/'waffle-kernel.h'
with (out/'haptic-loader-build.log').open('w') as log:
 subprocess.run(['bash','loader/build.sh'],cwd=r,env=os.environ|{'XNU_PLATFORM':'waffle','WAFFLE_KERNEL_HEADER':str(header)},stdout=log,stderr=subprocess.STDOUT,check=True)
 for dest in [out/'loader-waffle.efi',mu/'Platforms/OnePlus/wafflePkg/Applications/XnuRamLoader/loader-waffle.efi']:shutil.copyfile(r/'loader/loader-waffle.efi',dest)
 subprocess.run(['python3','build_uefi.py','-d','waffle','-r','DEBUG'],cwd=mu,stdout=log,stderr=subprocess.STDOUT,check=True)
image=out/'HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img';shutil.copyfile(mu/'Mu-waffle.img',image);shutil.copyfile(image,out/'HakiOS-waffle-PJD110-AUTO-RAM.img')
shutil.copytree(r/'work/waffle/haptics/h10-ui-root',out/'gl-probe',dirs_exist_ok=True)
ui=json.loads((out/'gl-probe/manifest.json').read_text())
preserved=['target','kernel_sha256','kernel_crc32','kernel_build_target','source_revision','source_diff','haptic_pulse_loader']
m=old|{k:source[k] for k in preserved};m.update(hardware_tested=False,haptic_ui_test=True,haptic_pulse_test=True,gl_probe_root_sha256=ui['root_sha256'],ui_stop_seconds=60,boot_image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),kernel_reused_from=str(base),kernel_reuse_reason='H09 threaded haptic kernel; H10 only loader policy and GPU userland root changed',experiment='H10 first joint guarded GPU UI, PCM haptic service and torch; CPU1 only',render_timing=False)
names=['kernel/files/bsd/dev/macan_torch.c','kernel/files/bsd/sys/waffle_haptic_readonly.h','kernel/files/bsd/sys/waffle_haptic_pulse.h','kernel/files/bsd/sys/waffle_haptic_events.h','loader/waffle.h','loader/loader.c']
for n in ['loader/waffle.h','loader/loader.c','tools/run-waffle-auto.py','scripts/run_waffle_ios.py','work/waffle/gpu/run-publish-test.py','tools/build-waffle-ui-probe.py']:
 target=out/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r/n,target)
m['haptic_pulse_source_sha256']={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(out/(image.name+'.sha256')).write_text(m['boot_image_sha256']+'  '+image.name+'\n')
subprocess.run([str(r/'work/validate-venv/bin/python'),'tools/validate-waffle-diagnostic.py',str(out)],cwd=r,check=True)
print('H10 packaged/paired validated; no hardware test yet')
