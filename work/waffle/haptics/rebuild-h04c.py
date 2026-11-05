from pathlib import Path
import json,hashlib,os,shutil,subprocess
r=Path('/home/qarzis/ios-macan');base=r/'work/waffle/diagnostic-haptic-pulse-h04b';out=r/'work/waffle/diagnostic-haptic-pulse-h04c';mu=r/'work/waffle/mu-hakios'
assert not out.exists()
m=json.loads((base/'manifest.json').read_text())
assert hashlib.sha256((base/'kernel').read_bytes()).hexdigest()==m['kernel_sha256']
for name in ['kernel/files/bsd/dev/macan_torch.c','kernel/files/bsd/sys/waffle_haptic_readonly.h','kernel/files/bsd/sys/waffle_haptic_pulse.h','loader/loader.c','loader/platform.h','loader/build.sh','loader/identity.h']:
 assert (r/name).read_bytes()==(base/'source'/name).read_bytes(),name
shutil.copytree(base,out)
header=out/'waffle-kernel.h';header.write_text(header.read_text()+'#define WAFFLE_HAPTIC_PULSE_TEST 1\n')
with (out/'haptic-loader-build.log').open('w') as log:
 subprocess.run(['bash','loader/build.sh'],cwd=r,env=os.environ|{'XNU_PLATFORM':'waffle','WAFFLE_KERNEL_HEADER':str(header)},stdout=log,stderr=subprocess.STDOUT,check=True)
 shutil.copyfile(r/'loader/loader-waffle.efi',out/'loader-waffle.efi')
 shutil.copyfile(out/'loader-waffle.efi',mu/'Platforms/OnePlus/wafflePkg/Applications/XnuRamLoader/loader-waffle.efi')
 subprocess.run(['python3','build_uefi.py','-d','waffle','-r','DEBUG'],cwd=mu,stdout=log,stderr=subprocess.STDOUT,check=True)
image=out/'HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img';shutil.copyfile(mu/'Mu-waffle.img',image);shutil.copyfile(image,out/'HakiOS-waffle-PJD110-AUTO-RAM.img')
names=['kernel/files/bsd/dev/macan_torch.c','kernel/files/bsd/sys/waffle_haptic_readonly.h','kernel/files/bsd/sys/waffle_haptic_pulse.h','loader/waffle.h']
for name in ['loader/waffle.h','tools/build-waffle-diagnostic.py','tools/run-waffle-auto.py','tools/tests/waffle-haptic-policy-host.c','tools/tests/waffle-haptic-binding-host.py']:
 target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r/name,target)
m.update(hardware_tested=False,kernel_reused_from=str(base),kernel_reuse_reason='Only loader policy changed after not-started refusal; compiled XNU kernel and relevant sources byte-identical',haptic_pulse_loader=True,boot_image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),haptic_pulse_source_sha256={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names})
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(out/(image.name+'.sha256')).write_text(m['boot_image_sha256']+'  '+image.name+'\n')
subprocess.run([str(r/'work/validate-venv/bin/python'),'tools/validate-waffle-diagnostic.py',str(out)],cwd=r,check=True)
print('H04C loader-only rebuild validated; kernel reused unchanged; NOT hardware result')
