#!/usr/bin/env python3
"""Reboot a Qualcomm 900E (Sahara crashdump) device via its Windows COM port."""
import ctypes
from ctypes import wintypes
import re
import struct
import subprocess
import sys
import time

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [
        ("ReadIntervalTimeout", wintypes.DWORD),
        ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
        ("ReadTotalTimeoutConstant", wintypes.DWORD),
        ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
        ("WriteTotalTimeoutConstant", wintypes.DWORD),
    ]


def find_900e_com():
    cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -match 'VID_05C6&PID_900E' } | Select-Object -ExpandProperty Name"
    ]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    m = re.search(r"\((COM\d+)\)", out)
    return m.group(1) if m else None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_900e_com()
    if not port:
        print("No Qualcomm 900E COM port found", file=sys.stderr)
        return 1
    print(f"Found Qualcomm 900E on {port}")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    h = k32.CreateFileW(f"\\\\.\\{port}", GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        print(f"CreateFileW({port}) failed: err={ctypes.get_last_error()}", file=sys.stderr)
        return 1
    try:
        to = COMMTIMEOUTS(100, 0, 1500, 0, 1500)
        k32.SetCommTimeouts(h, ctypes.byref(to))
        buf = ctypes.create_string_buffer(256)
        nread = wintypes.DWORD(0)
        nwrote = wintypes.DWORD(0)

        # Read Sahara HELLO if waiting
        ok = k32.ReadFile(h, buf, 48, ctypes.byref(nread), None)
        if ok and nread.value >= 16:
            cmd_id, pkt_len, ver, ver_min = struct.unpack_from("<IIII", buf.raw, 0)
            print(f"Sahara RX: len={nread.value} cmd={cmd_id:#x} pkt_len={pkt_len} ver={ver} min={ver_min}")
            if cmd_id == 1:
                # Send HELLO_RESP with mode=2 (SAHARA_MODE_MEMORY_DEBUG)
                resp = struct.pack("<IIIIIIIIIIII", 2, 48, ver, ver_min, 0, 2, 0, 0, 0, 0, 0, 0)
                k32.WriteFile(h, resp, len(resp), ctypes.byref(nwrote), None)
                print(f"Sahara TX HELLO_RESP: {nwrote.value} bytes")
                nread.value = 0
                if k32.ReadFile(h, buf, 64, ctypes.byref(nread), None) and nread.value >= 8:
                    r_cmd, r_len = struct.unpack_from("<II", buf.raw, 0)
                    print(f"Sahara RX after HELLO_RESP: len={nread.value} cmd={r_cmd:#x} pkt_len={r_len}")

        # Send SAHARA_RESET (cmd=7, len=8)
        reset_pkt = struct.pack("<II", 7, 8)
        ok_w = k32.WriteFile(h, reset_pkt, len(reset_pkt), ctypes.byref(nwrote), None)
        print(f"Sahara TX RESET: ok={ok_w} wrote={nwrote.value} bytes")
        nread.value = 0
        if k32.ReadFile(h, buf, 16, ctypes.byref(nread), None) and nread.value >= 8:
            r_cmd, r_len = struct.unpack_from("<II", buf.raw, 0)
            print(f"Sahara RX RESET_RESP: len={nread.value} cmd={r_cmd:#x} pkt_len={r_len}")
    finally:
        k32.CloseHandle(h)
    print("Sahara reset sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
