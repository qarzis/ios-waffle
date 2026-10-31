#!/usr/bin/env python3
"""Check a waffle diagnostic's boot container, embedded EFI, kernel and XNUP.

Requires pefile and uefi_firmware. Does not communicate with a phone.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import uuid
import zlib

import pefile
from uefi_firmware import AutoParser
from uefi_firmware.uefi import FirmwareFile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def walk(obj):
    yield obj
    for child in getattr(obj, "objects", []):
        yield from walk(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    folder = args.directory
    image = (folder / "HackiOS-waffle-PJD110-XNU-DIAGNOSTIC.img").read_bytes()
    manifest = json.loads((folder / "manifest.json").read_text())
    require(hashlib.sha256(image).hexdigest() == manifest["boot_image_sha256"], "Boot image hash mismatch")
    require(image[:8] == b"ANDROID!", "Missing Android boot header")
    kernel_size, ramdisk_size = struct.unpack_from("<II", image, 8)
    header_size, = struct.unpack_from("<I", image, 20)
    version, = struct.unpack_from("<I", image, 40)
    require(version == 4 and header_size == 1584 and kernel_size > 0, "Unexpected boot v4 layout")
    require(4096 + ((kernel_size + 4095) & ~4095) + ((ramdisk_size + 4095) & ~4095) <= len(image),
            "Truncated boot container")
    compressed = image[4096:4096 + kernel_size]
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    firmware = inflater.decompress(compressed) + inflater.flush()
    require(inflater.eof, "Incomplete gzip firmware")
    dtbs = inflater.unused_data
    dtb_hashes = []
    while dtbs:
        magic, size = struct.unpack_from(">II", dtbs)
        require(magic == 0xd00dfeed and 40 <= size <= len(dtbs), "Invalid appended DTB")
        dtb_hashes.append(hashlib.sha256(dtbs[:size]).hexdigest())
        dtbs = dtbs[size:]
    profiles = json.loads((folder / "hardware-provenance.json").read_text())
    require(set(dtb_hashes) == {profile["sha256"] for profile in profiles}, "Stock DTBs changed during packaging")
    # The uncompressed data begins with BootShim, followed by the FD.
    volume_offset = firmware.find(b"_FVH") - 40
    require(volume_offset >= 0, "Packaged firmware has no FV header")
    volume = AutoParser(firmware[volume_offset:]).parse()
    require(volume is not None, "Cannot parse packaged firmware volume")
    modules = [obj for obj in walk(volume) if isinstance(obj, FirmwareFile) and
               str(uuid.UUID(bytes_le=obj.guid)) == "8148efc2-c15b-4518-9478-c98f6d3c7215"]
    require(len(modules) == 1, "Expected one embedded waffle loader")
    executables = [section.data for section in modules[0].sections if section.type == 0x10]
    loader = (folder / "loader-waffle.efi").read_bytes()
    require(executables == [loader], "Packaged loader differs from diagnostic EFI")
    pe = pefile.PE(data=loader)
    require(pe.FILE_HEADER.Machine == 0xaa64 and pe.OPTIONAL_HEADER.Subsystem == 10, "Expected AArch64 EFI application")
    kernel = (folder / "kernel").read_bytes()
    require(hashlib.sha256(kernel).hexdigest() == manifest["kernel_sha256"], "Kernel hash mismatch")
    require(f"{zlib.crc32(kernel):08x}" == manifest["kernel_crc32"], "Kernel CRC mismatch")
    require(struct.unpack_from("<II", kernel) == (0xfeedfacf, 0x100000c), "Expected ARM64 Mach-O kernel")
    payload = (folder / "xnu-diagnostic.xnup").read_bytes()
    magic, size = struct.unpack_from("<II", payload)
    require(magic == 0x50554e58 and size == len(payload) - 8, "Invalid XNUP header")
    offset, entries = 8, {}
    while offset + 24 <= len(payload):
        name, size, reserved = struct.unpack_from("<16sII", payload, offset)
        offset += 24
        if not name.strip(b"\0"):
            require(size == 0 and reserved == 0 and offset == len(payload), "Invalid XNUP terminator")
            break
        name = name.split(b"\0", 1)[0].decode("ascii")
        require(name not in entries and reserved == 0 and offset + size <= len(payload), "Invalid XNUP entry")
        entries[name] = payload[offset:offset + size]
        offset += (size + 15) & ~15
    else:
        raise ValueError("XNUP has no terminator")
    require(entries == {"kernel": kernel, "checkpoint": b"1\0", "usb": b"1\0",
                        "cmdline": b"-v bootcpu=1 loader_return_after=10\0"}, "Unexpected diagnostic payload contents")
    report = {"android_boot_version": version, "embedded_loader_bytes": len(loader),
              "embedded_loader_matches": True, "stock_dtbs": dtb_hashes,
              "kernel_bytes": len(kernel), "payload_matches": True,
              "hardware_tested": False}
    (folder / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
