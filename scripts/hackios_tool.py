#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / 'artifacts' / 'ace6t'
KIT = ROOT / 'work' / 'kit'
IMAGES = ROOT / 'work' / 'images'
RELEASE = 'https://github.com/hxfuxyy/ios-macan/releases/latest/download/hackios-kit.zip'
HW = A / 'hw-android'
WINDOWS = os.name == 'nt'
LOG = ROOT / 'work' / 'logs' / 'hackios.log'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'
if WINDOWS:
    os.system('')
BOLD, GREEN, RED, RESET = ('\033[1;36m', '\033[1;32m', '\033[1;31m', '\033[0m') if sys.stdout.isatty() else ('',) * 4


def say(text):
    print(f'{BOLD}hackios:{RESET} {text}', flush=True)


def die(text):
    print(f'{RED}hackios:{RESET} {text}', file=sys.stderr, flush=True)
    sys.exit(1)


def step(number, total, text):
    print(f'\n{BOLD}[{number}/{total}] {text}{RESET}', flush=True)


def megabytes(count):
    return f'{count / 1048576:,.0f} MB'


def show_progress(label, done, total, start):
    elapsed = max(time.time() - start, 0.001)
    speed = done / elapsed
    if total:
        fraction = min(done / total, 1)
        filled = int(fraction * 30)
        left = (total - done) / speed if speed > 0 else 0
        line = (f'  {label} [{"#" * filled}{"." * (30 - filled)}] {fraction * 100:5.1f}%  '
                f'{megabytes(done)} of {megabytes(total)}  {speed / 1048576:4.1f} MB/s  {int(left // 60)}:{int(left % 60):02d} left ')
    else:
        line = f'  {label} {megabytes(done)}  {speed / 1048576:4.1f} MB/s '
    print('\r' + line, end='', flush=True)


def download(url, path, label):
    import urllib.error
    import urllib.request
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(path, 'wb') as out:
            total = int(response.headers.get('Content-Length') or 0)
            done, start, shown = 0, time.time(), 0
            while True:
                block = response.read(1 << 20)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if time.time() - shown >= 0.3:
                    shown = time.time()
                    show_progress(label, done, total, start)
            show_progress(label, done, total, start)
            print(flush=True)
    except (urllib.error.URLError, OSError) as error:
        print(flush=True)
        path.unlink(missing_ok=True)
        die(f'download failed ({getattr(error, "reason", error)}): check the Internet connection and run this again')
    if total and done != total:
        path.unlink(missing_ok=True)
        die(f'the download stopped at {megabytes(done)} of {megabytes(total)}: run this again')


def run_python(script, what):
    code = subprocess.call([sys.executable, str(ROOT / script)])
    if code:
        die(f'{what} failed (the reason is in the lines above). Fix it and run the same command again: '
            'finished parts are kept.')


PLATFORM_TOOLS = ROOT / 'work' / 'platform-tools'
ZADIG = 'https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe'
USB_ID = 'VID_18D1&PID_D00D'


def get_platform_tools():
    import zipfile
    system = 'windows' if WINDOWS else 'darwin' if sys.platform == 'darwin' else 'linux'
    archive = ROOT / 'work' / 'platform-tools.zip'
    say("downloading Google's platform-tools (adb, fastboot) into work/platform-tools")
    download(f'https://dl.google.com/android/repository/platform-tools-latest-{system}.zip', archive, 'platform-tools.zip')
    shutil.rmtree(PLATFORM_TOOLS, ignore_errors=True)
    with zipfile.ZipFile(archive) as tools_zip:
        tools_zip.extractall(ROOT / 'work')
    archive.unlink()
    if not WINDOWS:
        for path in PLATFORM_TOOLS.iterdir():
            if path.is_file() and '.' not in path.name:
                path.chmod(0o755)
    if not (PLATFORM_TOOLS / ('fastboot' + ('.exe' if WINDOWS else ''))).is_file():
        die('platform-tools did not unpack: get them from https://developer.android.com/tools/releases/platform-tools')


def find_tool(name):
    exe = name + ('.exe' if WINDOWS else '')
    local = PLATFORM_TOOLS / exe
    if local.is_file():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    get_platform_tools()
    return str(local)


def windows_driver_missing():
    if not WINDOWS:
        return False
    _, out = call(['powershell', '-NoProfile', '-Command',
                   "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\" + USB_ID +
                   "*' -and $_.Status -ne 'OK' } | Select-Object -ExpandProperty InstanceId"], 20)
    return USB_ID in out.upper()


def driver():
    if not WINDOWS:
        say('Linux needs no driver; if fastboot says "no permissions", run ./hackios --udev')
        return
    folder = ROOT / 'work' / 'zadig'
    exe = folder / 'zadig.exe'
    if not exe.is_file():
        say('downloading Zadig (the WinUSB driver installer)')
        download(ZADIG, exe, 'zadig.exe')
    (folder / 'zadig.ini').write_text('[general]\nadvanced_mode = false\nexit_on_success = true\n'
                                      '[device]\nlist_all = true\ninclude_hubs = false\ntrim_whitespaces = true\n'
                                      '[driver]\ndefault_driver = 0\nextract_only = false\n')
    print(f'''
  Zadig opens now (Windows asks for administrator rights):
    1. Put the phone into fastboot (or run --boot once: it stops there).
    2. In the list choose the device whose USB ID is 18D1 D00D (often "Android" or "Fastboot").
    3. On the right "WinUSB" must be selected. Press "Install Driver" (or "Replace Driver").
    4. Wait for "The driver was installed successfully", close Zadig and run --boot again.
  The same driver serves the phone's fastboot and the iOS loader (both are 18D1 D00D).
''', flush=True)
    os.startfile(str(exe))


def usb_trouble():
    if windows_driver_missing():
        die('Windows sees the phone in fastboot but has no driver for it: run  hackios.bat --driver  once, then --boot again')
    if not WINDOWS:
        _, out = call([FASTBOOT, 'devices'], 5)
        if 'no permissions' in out:
            die('fastboot has no permission to use the phone: run  ./hackios --udev  once, replug the cable, then --boot again')
        _, out = call([ADB, 'devices'], 5)
        if 'no permissions' in out:
            die('adb has no permission to use the phone: run  ./hackios --udev  once, replug the cable, then retry')
    _, out = call([ADB, 'devices'], 5)
    if '\tunauthorized' in out:
        say('the phone asks to allow USB debugging: unlock it and press Allow')


ADB = FASTBOOT = None


def tools():
    global ADB, FASTBOOT
    if not ADB:
        ADB, FASTBOOT = find_tool('adb'), find_tool('fastboot')


def call(command, timeout=10):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout or '') + (result.stderr or '')
    except (subprocess.TimeoutExpired, OSError):
        return 1, ''


def fastboot_devices():
    _, out = call([FASTBOOT, 'devices'], 5)
    return [line.split()[0] for line in out.splitlines() if line.strip().endswith('fastboot')]


def in_loader():
    return 'xnuloader' in fastboot_devices()


def firmware_fastboot():
    return [d for d in fastboot_devices() if d != 'xnuloader']


def adb_ready():
    _, out = call([ADB, 'devices'], 5)
    return any(line.strip().endswith('\tdevice') for line in out.splitlines()[1:])


def adb_root(command, timeout=60):
    _, out = call([ADB, 'shell', 'su', '-c', command], timeout)
    return out.replace('\r', '')


def wait_for(seconds, what, check):
    deadline = time.time() + seconds
    checked = time.time()
    while not check():
        if time.time() > deadline:
            usb_trouble()
            die(f'timeout after {seconds} s waiting for {what}')
        if time.time() - checked > 15:
            checked = time.time()
            usb_trouble()
        time.sleep(2)


def boot_uefi():
    tools()
    path = KIT / 'uefi.img'
    if not path.is_file():
        die('no UEFI image: run --get (or --build)')
    if not fastboot_devices() and not adb_ready():
        usb_trouble()
        die('no phone over USB (neither fastboot nor adb): connect it and retry')
    if len(firmware_fastboot()) > 1:
        die('more than one phone in fastboot: connect only one')
    if in_loader():
        say('the phone is in the loader: back to Android first')
        call([FASTBOOT, '-s', 'xnuloader', 'reboot'], 15)
        time.sleep(5)
    if not firmware_fastboot():
        wait_for(240, 'Android over adb', adb_ready)
        wait_for(180, 'Android to finish booting',
                 lambda: call([ADB, 'shell', 'getprop', 'sys.boot_completed'], 5)[1].strip() == '1')
        if not adb_root('id', 10).startswith('uid=0'):
            die('Android has no working root (su): it cannot be sent to the bootloader')
        say('Android is up: rebooting into the bootloader')
        call([ADB, 'shell', 'su', '-c', 'reboot bootloader'], 15)
        wait_for(120, 'the bootloader (fastboot)', lambda: bool(firmware_fastboot()))
    serial = firmware_fastboot()[0]
    say('fastboot boot uefi.img (RAM only, nothing is flashed)')
    code, out = call([FASTBOOT, '-s', serial, 'boot', str(path)], 60)
    if code:
        die('fastboot boot failed:\n' + out)
    wait_for(180, 'the iOS loader', in_loader)
    say('the loader is up')


def run_ios(options):
    for need in (KIT / 'kernel', IMAGES / 'root.packfs', IMAGES / 'system.packfs'):
        if not need.is_file():
            die(f'{need.relative_to(ROOT)} is missing: run --get (or --build)')
    command = [sys.executable, str(ROOT / 'scripts' / 'run_ios.py'), '--kernel', str(KIT / 'kernel'),
               '--root-image', str(IMAGES / 'root.packfs'), '--system-image', str(IMAGES / 'system.packfs')]
    sys.exit(subprocess.call(command + options))


def latest_kit_id():
    import json
    import urllib.request
    try:
        with urllib.request.urlopen('https://api.github.com/repos/hxfuxyy/ios-macan/releases/latest', timeout=30) as response:
            release = json.load(response)
        return next(str(asset['id']) + ' ' + asset['updated_at'] for asset in release['assets'] if asset['name'] == 'hackios-kit.zip')
    except Exception:
        return ''


def get_kit():
    import zipfile
    KIT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / 'work' / 'hackios-kit.zip'
    stamp = KIT / 'RELEASE'
    latest = latest_kit_id()
    complete = all((KIT / name).exists() for name in ('kernel', 'uefi.img', 'root-base.tar', 'system-overlay.tar', 'tools'))
    if latest and complete and stamp.is_file() and stamp.read_text().strip() == latest:
        say('the release kit is up to date')
        return
    say('downloading the release kit (kernel, UEFI, userland) from GitHub')
    download(RELEASE, archive, 'hackios-kit.zip')
    say('unpacking the kit')
    try:
        with zipfile.ZipFile(archive) as kit:
            kit.extractall(KIT)
    except zipfile.BadZipFile:
        archive.unlink(missing_ok=True)
        die('the downloaded kit is damaged: run this again')
    archive.unlink()
    if latest:
        stamp.write_text(latest + '\n')
    if not WINDOWS:
        for name in ('unzbm',):
            path = KIT / 'tools' / name
            if path.exists():
                path.chmod(0o755)
    say('kit ready in work/kit: ' + ', '.join(sorted(p.name for p in KIT.iterdir())))


def fetch_ios():
    run_python('ios165/fetch.py', 'getting iOS 16.5')


def assemble():
    run_python('tools/assemble.py', 'making the images')


def locate(name):
    where = adb_root('for d in /vendor/firmware_mnt/image /vendor/firmware /odm/firmware /vendor/firmware/wcn7750 /odm/etc; '
                     f'do [ -f $d/{name} ] && echo $d/{name} && break; done').strip()
    if not where:
        where = adb_root(f"find /vendor /odm -name '{name}' 2>/dev/null | head -1").strip()
    return where


def pull_named(name, dest):
    where = locate(name)
    if not where:
        say(f'not on the phone: {name}')
        return
    adb_root(f"cp '{where}' /data/local/tmp/hackios.fw && chmod 644 /data/local/tmp/hackios.fw")
    dest.mkdir(parents=True, exist_ok=True)
    code, out = call([ADB, 'pull', '/data/local/tmp/hackios.fw', str(dest / name)], 120)
    if code or not (dest / name).is_file():
        say(f'could not copy {name}: {out.strip()}')


def firmware():
    tools()
    if not adb_ready():
        die('the phone is not in Android over adb (USB debugging on?)')
    if not adb_root('id', 10).startswith('uid=0'):
        die('no root (su) on the phone')
    say('GPU')
    for name in ('gen80900_aqe.fw', 'gen80900_gmu.bin', 'gen80900_sqe.fw', 'gen80900_zap.mbn'):
        pull_named(name, A / 'gpu-android')
    say('Wi-Fi')
    for name in ['wpss.mdt', 'aux_ucode.elf', 'bd_m20gl.elf', 'phy_ucode.elf', 'regdb_xiaomi.bin', 'qdss_trace_config_perf_v1.cfg']:
        pull_named(name, A / 'wifi-android' / 'fw')
    folder = locate('wpss.mdt').rsplit('/', 1)[0] or '/vendor/firmware_mnt/image'
    for name in adb_root(f'ls {folder}').split():
        if re.fullmatch(r'wpss\.b\d+', name):
            pull_named(name, A / 'wifi-android' / 'fw')
    say('vibration')
    pull_named('aw8697_haptic_170.bin', HW / 'fw')
    say('audio DSP')
    for name in adb_root('ls /vendor/firmware_mnt/image').split():
        if re.fullmatch(r'adsp(_dtb)?\.(mdt|b\d+)', name):
            pull_named(name, HW / 'adsp')
    adb_root('rm -f /data/local/tmp/hackios.fw')
    say('done: the firmware is in artifacts/ace6t (it never goes into git)')


def wifi(ssid, password):
    path = A / 'wifi-android' / 'fw' / 'network'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{ssid}\n{password}\n', encoding='utf-8', newline='\n')
    if not WINDOWS:
        path.chmod(0o600)
    say('network saved: now --assemble (or --get if not done yet), then --boot')


def android():
    tools()
    if in_loader():
        call([FASTBOOT, '-s', 'xnuloader', 'reboot'], 15)
        say('rebooting into Android')
    elif firmware_fastboot():
        call([FASTBOOT, 'reboot'], 15)
        say('rebooting into Android')
    else:
        say('the phone is not in the loader or fastboot')


def status():
    tools()
    _, adb_out = call([ADB, 'devices'], 5)
    phones = [line.split()[0] for line in adb_out.splitlines()[1:] if line.strip().endswith('device')]
    print('phone in Android:  ', ', '.join(phones) or 'no')
    print('phone in fastboot: ', ', '.join(fastboot_devices()) or 'no')
    print('iOS 16.5 fetched:  ', 'yes' if (ROOT / 'ios165' / 'rootfs').is_dir() else 'no')
    print('kit (UEFI, kernel):', 'yes' if (KIT / 'uefi.img').is_file() and (KIT / 'kernel').is_file() else 'no')
    print('root image:        ', 'yes' if (IMAGES / 'root.packfs').is_file() else 'no')
    print('system image:      ', 'yes' if (IMAGES / 'system.packfs').is_file() else 'no')
    for name in ('gpu-android', 'wifi-android/fw', 'hw-android/fw', 'hw-android/adsp'):
        folder = A / name
        count = len(list(folder.iterdir())) if folder.is_dir() else 0
        print(f'firmware {name + ":":17}', count, 'files')


def main(argv):
    if not argv:
        die('usage: hackios_tool.py get | fetch | firmware | assemble | boot [-- OPTIONS] | run [-- OPTIONS] | wifi NAME PASS | android | status | tools | driver')
    command, rest = argv[0].lstrip('-'), argv[1:]
    options = []
    if '--' in rest:
        index = rest.index('--')
        rest, options = rest[:index], rest[index + 1:]
    if command == 'get':
        started = time.time()
        step(1, 4, 'the release kit')
        get_kit()
        step(2, 4, 'iOS 16.5 from Apple (about 7 GB the first time; already fetched parts are skipped)')
        fetch_ios()
        step(3, 4, "the phone's firmware")
        tools()
        if adb_ready():
            firmware()
        else:
            say('no phone in Android over adb: skipped, copy it later with --firmware, then --assemble')
        step(4, 4, 'the root and system images')
        assemble()
        minutes = int((time.time() - started) // 60)
        print(f'\n{GREEN}hackios: ready in {minutes} min. Now: --boot{RESET}', flush=True)
    elif command == 'fetch':
        fetch_ios()
    elif command == 'assemble':
        assemble()
    elif command == 'boot':
        boot_uefi()
        run_ios(options)
    elif command == 'run':
        run_ios(options)
    elif command == 'firmware':
        firmware()
    elif command == 'wifi':
        if len(rest) != 2:
            die('usage: --wifi NAME PASS')
        wifi(*rest)
    elif command == 'android':
        android()
    elif command == 'status':
        status()
    elif command == 'tools':
        get_platform_tools()
        say('adb and fastboot are in work/platform-tools')
    elif command == 'driver':
        driver()
    else:
        die('unknown command ' + command)


def guarded(argv):
    if WINDOWS and len(str(ROOT)) > 120:
        say(f'the folder path is long ({len(str(ROOT))} characters): if something fails, move the folder to e.g. C:\\ios-macan')
    try:
        main(argv)
    except KeyboardInterrupt:
        print(flush=True)
        die('stopped (Ctrl+C). Run the same command again to continue.')
    except Exception:
        import traceback
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as log:
            log.write(time.strftime('\n%Y-%m-%d %H:%M:%S ') + ' '.join(argv) + '\n')
            traceback.print_exc(file=log)
        error = sys.exc_info()[1]
        die(f'unexpected error: {type(error).__name__}: {error}\n'
            f'hackios: details in {LOG.relative_to(ROOT)}; send that file when you report the problem')


if __name__ == '__main__':
    guarded(sys.argv[1:])
