#!/usr/bin/env python3
"""RAM boot the automatic waffle loader and run a bounded GPU diagnostic.

Never flashes. Optional standard Sahara collection uses the existing pinned
collector, which resets after collecting offered crash segments.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--audio-preflight', action='store_true', help='Isolated60-second native ADSP firmware validation, without DSP startup')
    parser.add_argument('--audio-power', action='store_true', help='With --audio-preflight: qualify native RPMh upvotes, retain until Android reset')
    parser.add_argument('--audio-survey', action='store_true', help='With --audio-preflight: read-only SMEM/SMP2P/GLINK state survey')
    parser.add_argument('--audio-iommu', action='store_true', help='Read-only native Apps SMMU/audio stream survey; no DSP or DMA writes')
    parser.add_argument('--audio-boot', action='store_true', help='With --audio-preflight: bounded ADSP firmware boot/GPR query/shutdown, no PCM')
    parser.add_argument('--audio-graph', action='store_true', help='With --audio-boot: open/close shared-memory endpoint graph; no DMA/PCM')
    parser.add_argument('--hardware-vsync',action='store_true',help='Opt-in hardware panel TE timestamps for iOS callbacks')
    parser.add_argument('--display-survey',action='store_true',help='Read-only inherited DPU/TE survey during GPU UI')
    parser.add_argument('--cpu-ui-test', action='store_true', help='Bounded softpipe iOS boot testing PSCI cores, without GPU startup')
    parser.add_argument('--cpus', type=int, choices=range(1,8), help='XNU cores for an explicit UI test (GPU UI default: 7); resident loader owns the eighth core')
    parser.add_argument('--cpu-seconds', type=int, choices=(60,90,180,240), default=60, help='Bounded CPU/UI observation window')
    parser.add_argument('--torch-readonly', action='store_true', help='Separate Waffle flash module identification without PMIC writes')
    parser.add_argument('--torch-pulse',action='store_true',help='Single two-second flash-module pulse in the GPU UI workload')
    parser.add_argument('--torch-service',action='store_true',help='Expose the qualified Waffle flashlight driver in the GPU UI')
    parser.add_argument('--prepare-gpu', action='store_true', help='Run existing probe93; no RAW')
    parser.add_argument('--access-matrix', action='store_true', help='Add existing E03 checks to probe93')
    parser.add_argument('--measure-clocks', action='store_true', help='Measure clocks on prepare-only probe93')
    parser.add_argument('--lpac-cp-init',action='store_true',help='E08 only: CP_INIT94 with validated LPAC mapping; may enter900e')
    parser.add_argument('--gl-context',action='store_true',help='E36 actual Darwin OSMesa GL renderer')
    parser.add_argument('--mapped',action='store_true',help='E33 direct mapped BOs; requires --msm --mesa-transport')
    parser.add_argument('--mesa-transport',action='store_true',help='E32 actual Mesa DRM shim; requires --msm')
    parser.add_argument('--msm',action='store_true',help='E31 two BOs and user command submission')
    parser.add_argument('--user-va',action='store_true',help='E30 GLSL data at64bitlowerGPUVA; requires dispatch')
    parser.add_argument('--glsl',action='store_true',help='E29 GLSL compiled shader; prepare or dispatch')
    parser.add_argument('--data-bo',action='store_true',help='E28 separate GPU data allocation; requires dispatch')
    parser.add_argument('--user-copy',action='store_true',help='E27 real Darwin user-process ioctl boundary; requires dispatch')
    parser.add_argument('--worker',action='store_true',help='E26 serialized top-level context with kernel worker; requires dispatch')
    parser.add_argument('--copy-jobs',action='store_true',help='E25 three caller-input compute jobs; requires dispatch')
    parser.add_argument('--image-present',action='store_true',help='E24 CPU-present verified GPU pixels then restore; requires dispatch')
    parser.add_argument('--image-copy',action='store_true',help='E23 uploaded image read/copy; requires --compute')
    parser.add_argument('--image',action='store_true',help='E22 compute-generated16x16 pixels; requires --compute')
    parser.add_argument('--compute',choices=('prepare','dispatch'),help='E21 bounded shader state/control or dispatch; requires --dynamic-bo')
    parser.add_argument('--dynamic-bo',action='store_true',help='E20: post-bootstrap test BO; requires --session')
    parser.add_argument('--session',action='store_true',help='E12 bounded owned session: requires --ib and entire verified chain')
    parser.add_argument('--ib',action='store_true',help='E11: GPU indirect command-buffer fetch; requires --writeback')
    parser.add_argument('--writeback',action='store_true',help='E10: dedicated GPU memory write after verified ZAP; requires --zap')
    parser.add_argument('--zap',action='store_true',help='E09: PAS13 authenticated load and native secure switch after CP_INIT')
    parser.add_argument('--lpac-map',action='store_true',help='Validate LPAC mappings on probe93, or controlled94 with --lpac-cp-init')
    parser.add_argument('--fastboot', default=str(ROOT.parent / 'platform-tools/fastboot'))
    parser.add_argument('--adb', default=str(ROOT.parent / 'platform-tools/adb'))
    parser.add_argument('--ui-workload',action='store_true',help='E46 isolated actual backboardd GPU workload; requires controlled GL root')
    parser.add_argument('--ui-long-test',action='store_true',help='Four-minute bounded UI with300-second kernel return; requires matching240-second UI root')
    parser.add_argument('--ui-soak-test',action='store_true',help='Ten-minute UI with660-second return; requires matching600-second root and generation handles')
    args = parser.parse_args()
    if args.audio_power and not args.audio_preflight:parser.error('--audio-power requires --audio-preflight')
    if args.audio_survey and (not args.audio_preflight or args.audio_power):parser.error('--audio-survey requires isolated --audio-preflight and excludes --audio-power')
    if args.audio_boot and (not args.audio_preflight or args.audio_power or args.audio_survey):parser.error('--audio-boot requires isolated --audio-preflight')
    if args.audio_graph and not args.audio_boot:parser.error('--audio-graph requires --audio-boot')
    if args.audio_iommu and (not args.audio_preflight or args.audio_power or args.audio_survey or args.audio_boot or args.audio_graph):parser.error('--audio-iommu requires isolated --audio-preflight')
    if args.audio_preflight and any(getattr(args, name) for name in (
            'cpu_ui_test','cpus','torch_readonly','torch_pulse','torch_service','prepare_gpu','access_matrix',
            'measure_clocks','lpac_cp_init','gl_context','mapped','mesa_transport','msm','user_va','glsl',
            'data_bo','user_copy','worker','copy_jobs','image_present','image_copy','image','compute',
            'dynamic_bo','session','ib','writeback','zap','lpac_map','ui_workload','ui_long_test','ui_soak_test')):
        parser.error('--audio-preflight must run separately from other diagnostics')
    if args.torch_readonly and not (args.cpu_ui_test or args.ui_workload):parser.error('--torch-readonly requires a CPU or GPU UI workload')
    if args.torch_pulse and (args.torch_readonly or not args.gl_context):parser.error('--torch-pulse requires the controlled GPU GL workload and excludes read-only mode')
    if args.torch_service and (args.torch_pulse or args.torch_readonly or not args.ui_workload):parser.error('--torch-service requires GPU UI and excludes probe modes')
    if args.cpus is not None and not (args.cpu_ui_test or args.ui_workload):parser.error('--cpus requires a UI workload')
    if args.ui_workload and args.cpus is None:
        args.cpus=7
    if args.cpu_ui_test and any((args.prepare_gpu,args.lpac_cp_init,args.gl_context,args.ui_workload,args.compute,args.session,args.lpac_map,args.access_matrix,args.measure_clocks,args.image,args.image_copy,args.image_present,args.copy_jobs,args.worker,args.user_copy,args.data_bo,args.glsl,args.user_va,args.msm,args.mesa_transport,args.mapped,args.dynamic_bo,args.ib,args.writeback,args.zap,args.ui_long_test,args.ui_soak_test)):
        parser.error('--cpu-ui-test must run separately from GPU experiments')
    if args.ui_workload and not args.gl_context:parser.error('--ui-workload requires --gl-context')
    if args.ui_long_test and not args.ui_workload:parser.error('--ui-long-test requires --ui-workload')
    if args.ui_soak_test and not args.ui_workload:parser.error('--ui-soak-test requires --ui-workload')
    if args.ui_soak_test and args.ui_long_test:parser.error('Select exactly one UI duration')
    if sum((args.gl_context,args.msm,args.user_va,args.glsl,args.data_bo,args.user_copy,args.worker,args.copy_jobs,args.image_present,args.image_copy,args.image))>1:parser.error('Choose image ramp or uploaded image copy')
    if (args.image_present or args.copy_jobs or args.worker or args.user_copy or args.data_bo or args.user_va or args.msm or args.gl_context) and args.compute!='dispatch':parser.error('--image-present requires --compute dispatch')
    args.image=args.gl_context or args.msm or args.image or args.image_copy or args.image_present or args.copy_jobs or args.worker or args.user_copy or args.data_bo or args.glsl or args.user_va
    if args.mesa_transport and not args.msm:parser.error('--mesa-transport requires --msm')
    if args.mapped and not (args.msm and args.mesa_transport):parser.error('--mapped requires MSM Mesa transport')
    artifact = args.artifact.resolve()
    image = artifact / 'HakiOS-waffle-PJD110-AUTO-RAM.img'
    if args.access_matrix and not args.prepare_gpu:
        parser.error('--access-matrix requires --prepare-gpu')
    if args.measure_clocks and not args.prepare_gpu:
        parser.error('--measure-clocks requires --prepare-gpu')
    if args.lpac_cp_init and (not args.lpac_map or args.prepare_gpu):
        parser.error('--lpac-cp-init requires --lpac-map and excludes --prepare-gpu')
    if args.lpac_map and not (args.prepare_gpu or args.lpac_cp_init):
        parser.error('--lpac-map requires --prepare-gpu or controlled --lpac-cp-init')
    if args.zap and not args.lpac_cp_init:
        parser.error('--zap requires controlled --lpac-cp-init --lpac-map')
    if args.writeback and not args.zap:
        parser.error('--writeback requires --zap')
    if args.ib and not args.writeback:
        parser.error('--ib requires --writeback')
    if args.image and not args.compute:
        parser.error('--image requires --compute')
    if args.compute and not args.dynamic_bo:
        parser.error('--compute requires --dynamic-bo')
    if args.dynamic_bo and not args.session:
        parser.error('--dynamic-bo requires --session')
    if args.session and not args.ib:
        parser.error('--session requires --ib')
    manifest = json.loads((artifact / 'manifest.json').read_text())
    if args.audio_preflight:
        if args.audio_boot:
            for name in ('A06-result.json','A07-result.json'):
                proof=json.loads((ROOT/'work/waffle/audio'/name).read_text())
                if not proof.get('passed') or not proof['auto_runner'].get('android_confirmed'):parser.error('Missing qualified audio prerequisite: '+name)
        audio_root=artifact/'audio-probe/root.packfs'
        audio_system=artifact/'audio-probe/system.packfs'
        audio_manifest=json.loads((artifact/'audio-probe/manifest.json').read_text())
        for path, key in ((audio_root,'root_sha256'),(audio_system,'system_sha256')):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=audio_manifest[key]:parser.error('Audio image hash mismatch')
        for name,digest in audio_manifest['source_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:parser.error('Audio source binding mismatch: '+name)
        if hashlib.sha256((artifact/'kernel').read_bytes()).hexdigest()!=manifest['kernel_sha256']:parser.error('Audio kernel hash mismatch')
        bound_source=artifact/'source/kernel/files/bsd/dev/macan_adsp.c'
        if not bound_source.is_file() or hashlib.sha256(bound_source.read_bytes()).hexdigest()!=audio_manifest['source_sha256']['kernel/files/bsd/dev/macan_adsp.c']:
            parser.error('Audio kernel source binding missing or stale')
    if args.hardware_vsync and (args.display_survey or not args.ui_workload or not args.gl_context or args.audio_preflight or not manifest.get('hardware_vsync_candidate') or not manifest.get('native_vbl_requested')):
        parser.error('--hardware-vsync requires a qualified GPU UI artifact and excludes diagnostics/audio')
    if args.display_survey and (not args.ui_workload or not args.gl_context or args.audio_preflight or not manifest.get('display_survey_readonly')):
        parser.error('--display-survey requires a qualified GPU UI artifact and excludes audio')
    if args.cpus is not None and args.cpus>1 and not manifest.get('multicore_loader'):
        parser.error('Artifact lacks the opt-in multicore loader policy')
    if args.torch_readonly and not manifest.get('torch_readonly_loader'):parser.error('Artifact lacks the torch read-only policy')
    if args.torch_pulse and not manifest.get('torch_pulse_loader'):parser.error('Artifact lacks the bounded torch pulse policy')
    if args.torch_service and not manifest.get('torch_service_loader'):parser.error('Artifact lacks the iOS torch-service policy')
    if args.cpu_ui_test:
        if not manifest.get('multicore_loader'):
            parser.error('Artifact lacks the opt-in multicore loader policy')
        cpu_root=artifact/'cpu-ui/root.packfs'
        if hashlib.sha256(cpu_root.read_bytes()).hexdigest()!=manifest.get('cpu_ui_root_sha256'):
            parser.error('CPU UI root hash mismatch')
    if args.ui_workload and not manifest.get('ui_workload'):parser.error('Artifact lacks isolated UI workload manifest')
    if args.ui_long_test and manifest.get('ui_stop_seconds')!=240:parser.error('Long UI test requires a bound240-second root')
    if args.ui_soak_test and (manifest.get('ui_stop_seconds')!=600 or not manifest.get('generation_handles') or not manifest.get('ui_soak_loader')):parser.error('Soak UI requires a bound600-second root, generation handles and a matching soak loader')
    if args.gl_context:
        if not manifest.get('gl_context'):parser.error('Artifact lacks controlled GL probe')
        glroot=artifact/'gl-probe/root.packfs'
        if hashlib.sha256(glroot.read_bytes()).hexdigest()!=manifest.get('gl_probe_root_sha256'):parser.error('GL root hash mismatch')
        system=ROOT/'work/waffle/images/system.packfs'
        digest=hashlib.sha256()
        with system.open('rb') as stream:
            for block in iter(lambda:stream.read(16*1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=manifest.get('gl_system_sha256'):parser.error('GL system image hash mismatch')
    if args.mapped and not manifest.get('mapped_bo'):parser.error('Artifact lacks mapped BO probe')
    if args.mesa_transport and not manifest.get('mesa_drm_shim'):parser.error('Artifact is not the Mesa transport probe')
    if not manifest.get('automatic_usb_loader'):
        parser.error('Artifact does not declare automatic loader entry')
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest['boot_image_sha256']:
        parser.error('Boot image does not match manifest')
    if args.msm or args.user_copy or args.data_bo or args.user_va or (args.glsl and args.compute=="dispatch"):
        root_image=artifact/('mapped-probe/user-probe.packfs' if args.mapped else 'msm-probe/user-probe.packfs' if args.msm else 'user-probe/user-probe.packfs')
        if not root_image.is_file() or hashlib.sha256(root_image.read_bytes()).hexdigest()!=manifest.get('mapped_probe_root_sha256' if args.mapped else 'msm_probe_root_sha256' if args.msm else 'user_probe_root_sha256'):
            parser.error('User probe root does not match manifest')
    for name in ('adb', 'fastboot'):
        if not Path(getattr(args, name)).is_file():
            parser.error(f'Missing {name}')
    if args.prepare_gpu or args.lpac_cp_init:
        # The existing session runner pins these transport paths.
        if Path(args.adb).resolve() != (ROOT.parent / 'platform-tools/adb').resolve() or \
                Path(args.fastboot).resolve() != (ROOT.parent / 'platform-tools/fastboot').resolve():
            parser.error('Prepare runner requires the standard workspace platform-tools')
        if hashlib.sha256((artifact / 'kernel').read_bytes()).hexdigest() != manifest['kernel_sha256']:
            parser.error('Kernel does not match manifest')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'work/waffle/auto-runs' / stamp
    output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': stamp, 'flash_operations': False, 'gpu_raw': args.lpac_cp_init,
              'prepare_gpu': args.prepare_gpu, 'access_matrix': args.access_matrix,
              'measure_clocks': args.measure_clocks, 'lpac_map':args.lpac_map, 'lpac_cp_init':args.lpac_cp_init, 'zap':args.zap, 'writeback':args.writeback, 'ib':args.ib, 'session':args.session, 'dynamic_bo':args.dynamic_bo, 'compute':args.compute, 'image':args.image, 'image_copy':args.image_copy,'image_present':args.image_present,'copy_jobs':args.copy_jobs,'worker':args.worker,'user_copy':args.user_copy,'data_bo':args.data_bo,'glsl':args.glsl,'user_va':args.user_va,'msm':args.msm,'mesa_transport':args.mesa_transport,'mapped':args.mapped,'gl_context':args.gl_context,
              'physical_boot_selection': False, 'android_confirmed': False}

    def command(items, timeout=10):
        result = subprocess.run(items, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        with (output / 'host.log').open('a') as log:
            log.write(' '.join(map(str, items)) + '\n' + result.stdout + result.stderr + '\n')
        return result

    def wait_for(check, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if check():
                return True
            time.sleep(1)
        return False

    def android_ready():
        p = command([args.adb, '-s', '1c62e9aa', 'shell', 'getprop', 'sys.boot_completed'])
        return p.returncode == 0 and p.stdout.strip() == '1'

    def fastboot_has(serial):
        p = command([args.fastboot, 'devices'])
        return any(line.split()[:1] == [serial] for line in p.stdout.splitlines())

    collector = None
    recovery_log = None
    try:
        if android_ready():
            p = command([args.adb, '-s', '1c62e9aa', 'reboot', 'bootloader'])
            if p.returncode:
                raise RuntimeError('Android refused reboot to bootloader')
        if not wait_for(lambda: fastboot_has('1c62e9aa'), 60):
            raise RuntimeError('Expected PJD110 Android fastboot; no RAM boot sent')
        p = command([args.fastboot, '-s', '1c62e9aa', 'boot', str(image)], timeout=30)
        if p.returncode:
            raise RuntimeError('RAM boot rejected')
        if not wait_for(lambda: fastboot_has('xnuloader'), 60):
            raise RuntimeError('Automatic loader did not enumerate')
        p = command([args.fastboot, '-s', 'xnuloader', 'getvar', 'platform'])
        if p.returncode or 'platform: waffle' not in p.stdout + p.stderr:
            raise RuntimeError('Automatic loader platform mismatch')
        report['automatic_loader_verified'] = True
        if args.audio_preflight:
            if args.audio_boot or args.audio_iommu:
                recovery_log=(output/'recovery.log').open('w')
                collector=subprocess.Popen([sys.executable,'tools/capture-waffle-crash.py','--collect','--wait-seconds','180'],cwd=ROOT,stdout=recovery_log,stderr=subprocess.STDOUT)
            items=[sys.executable,'scripts/run_waffle_ios.py','--seconds','60','--audio-preflight',
                '--kernel',str(artifact/'kernel'),'--root',str(audio_system),'--system',str(audio_root),
                '--fastboot',args.fastboot]
            if args.audio_power:items.append('--audio-power')
            if args.audio_survey:items.append('--audio-survey')
            if args.audio_iommu:items.append('--audio-iommu')
            if args.audio_boot:items.append('--audio-boot')
            if args.audio_graph:items.append('--audio-graph')
            result=command(items,timeout=240)
            report['audio_preflight']=True
            report['audio_power']=args.audio_power
            report['audio_survey']=args.audio_survey
            report['audio_iommu']=args.audio_iommu
            report['audio_boot']=args.audio_boot
            report['audio_graph']=args.audio_graph
            report['runner_exit']=result.returncode
            if result.returncode:raise RuntimeError('Audio firmware preflight failed; inspect preserved logs')
            p=command([args.fastboot,'-s','xnuloader','reboot'])
            if p.returncode:raise RuntimeError('Loader refused Android reboot after audio preflight')
        elif args.cpu_ui_test:
            recovery_log=(output/'recovery.log').open('w')
            collector=subprocess.Popen([sys.executable,'tools/capture-waffle-crash.py','--collect','--wait-seconds','60'],cwd=ROOT,stdout=recovery_log,stderr=subprocess.STDOUT)
            requests=output/'capture-requests'
            requests.mkdir()
            items=[sys.executable,'scripts/run_waffle_ios.py','--seconds',str(args.cpu_seconds),'--cpus',str(args.cpus or 2),'--kernel',str(artifact/'kernel'),'--root',str(cpu_root),'--fastboot',args.fastboot,'--capture-requests',str(requests)]
            if args.torch_readonly:items.append('--torch-readonly')
            if args.torch_pulse:items.append('--torch-pulse')
            result=command(items,timeout=args.cpu_seconds+240)
            report['cpu_ui_test']=True
            report['requested_cpus']=args.cpus or 2
            report['runner_exit']=result.returncode
            if result.returncode:
                raise RuntimeError('CPU boot/proof failed; preserve logs before another experiment')
            p=command([args.fastboot,'-s','xnuloader','reboot'])
            if p.returncode:
                raise RuntimeError('Loader refused Android reboot after CPU test')
        elif args.prepare_gpu or args.lpac_cp_init:
            recovery_log = (output / 'recovery.log').open('w')
            collector = subprocess.Popen([sys.executable, 'tools/capture-waffle-crash.py',
                '--collect', '--wait-seconds', '60'], cwd=ROOT,
                stdout=recovery_log, stderr=subprocess.STDOUT)
            items = [sys.executable, 'work/waffle/gpu/run-publish-test.py', '94' if args.lpac_cp_init else '93', str(artifact)]
            if args.torch_readonly:items.append('--torch-readonly')
            if args.torch_pulse:items.append('--torch-pulse')
            if args.hardware_vsync:items.append('--hardware-vsync')
            if args.display_survey:items.append('--display-survey')
            if args.torch_service:items.append('--torch-service')
            if args.cpus is not None:items.append(f'--cpus={args.cpus}')
            if args.access_matrix:
                items.append('--access-matrix')
            if args.measure_clocks:
                items.append('--measure-clocks')
            if args.lpac_map:
                items.append('--lpac-map')
            if args.zap:
                items.append('--zap')
            if args.writeback:
                items.append('--writeback')
            if args.ib:
                items.append('--ib')
            if args.session:
                items.append('--session')
            if args.dynamic_bo:
                items.append('--dynamic-bo')
            if args.compute:
                items.append('--compute-'+args.compute)
            if args.image:
                items.append('--gl-context' if args.gl_context else '--msm' if args.msm else '--user-va' if args.user_va else '--glsl' if args.glsl else '--data-bo' if args.data_bo else '--user-copy' if args.user_copy else '--worker' if args.worker else '--copy-jobs' if args.copy_jobs else '--image-present' if args.image_present else '--image-copy' if args.image_copy else '--image')
            if args.mesa_transport:items.append('--mesa-transport')
            if args.mapped:items.append('--mapped')
            if args.ui_workload:items.append('--ui-workload')
            if args.ui_long_test:items.append('--ui-long-test')
            if args.ui_soak_test:items.append('--ui-soak-test')
            result = command(items, timeout=1140 if args.ui_soak_test else 780 if args.ui_long_test else 420 if args.gl_context else 240)
            report['runner_exit'] = result.returncode
            if result.returncode:
                raise RuntimeError('GPU test failed; preserve original result and inspect recovery log')
        else:
            p = command([args.fastboot, '-s', 'xnuloader', 'reboot'])
            if p.returncode:
                raise RuntimeError('Loader refused Android reboot')
        if not wait_for(android_ready, 90):
            raise RuntimeError('Android recovery not confirmed; stop before another experiment')
        report['android_confirmed'] = True
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        report['success'] = False
        # Try normal loader reboot without hiding the failed experiment.
        try:
            if fastboot_has('xnuloader'):
                command([args.fastboot, '-s', 'xnuloader', 'reboot'])
            report['android_confirmed'] = wait_for(android_ready, 60)
        except Exception as recovery_error:
            report['recovery_error'] = str(recovery_error)
    finally:
        if collector:
            if collector.poll() is None and report['android_confirmed']:
                collector.terminate()
            try:
                collector.wait(timeout=65)
            except subprocess.TimeoutExpired:
                collector.terminate()
                report['collector_timeout'] = True
        if recovery_log:
            recovery_log.close()
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(output), **report}, indent=2))
    return 0 if report.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
