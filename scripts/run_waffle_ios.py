#!/usr/bin/env python3
"""Run the experimental PJD110 RAM port after selecting Boot iOS in UEFI."""
import argparse
from datetime import datetime, timezone
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT if (ROOT / "root.packfs").is_file() else ROOT / "work/waffle/images"
KERNEL_DIR = ROOT if (ROOT / "kernel").is_file() else ROOT / "work/waffle/diagnostic-userland"


def result_from_log(data):
    """Recover status when older EFI fills its log-backed getvar buffer."""
    prefix = data.split("\n== KERNEL LOG", 1)[0]
    for marker in ("EARLY KERNEL EXCEPTION", "STOPPED AT CHECKPOINT", "THE KERNEL HUNG",
                   "did not start: PSCI error", "was started but never arrived"):
        if marker in prefix:
            raise RuntimeError(f"Loader diagnostic: {marker}")
    if "\n== KERNEL LOG (the kernel is still running) ==" in data[:8192]:
        return "result: running 0 0"
    match = re.search(r"^kernel returned: log at [0-9a-f]+, (\d+) bytes$", prefix, re.MULTILINE)
    return f"result: returned {match[1]} 0" if match else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60, choices=range(1, 301), metavar="1..300")
    parser.add_argument("--bootcpu", type=int, default=7, choices=range(1, 8))
    parser.add_argument("--fbscale", type=int, default=2, choices=(1, 2, 3), help="Render scale: 1 is faster, 2 is sharper")
    parser.add_argument("--reuse-system", action="store_true", help="Reuse the system image in this same loader session")
    parser.add_argument("--gpu-probe", type=int, choices=range(1, 95), help="Probe SM8650 GPU power/clocks/SMMU/firmware or AOP QMP; return before iOS starts")
    parser.add_argument("--kernel", type=Path, default=KERNEL_DIR / "kernel")
    parser.add_argument("--root", type=Path, default=IMAGE_DIR / "root.packfs")
    parser.add_argument("--system", type=Path, default=IMAGE_DIR / "system.packfs")
    parser.add_argument("--fastboot", default=os.environ.get("FASTBOOT"))
    args = parser.parse_args()
    local_fastboot = next((path for path in (ROOT.parent / "platform-tools/fastboot",
                          ROOT.parent.parent / "platform-tools/fastboot") if path.is_file()), None)
    fastboot = args.fastboot or (str(local_fastboot) if local_fastboot else shutil.which("fastboot"))
    if not fastboot:
        parser.error("fastboot is missing; pass --fastboot PATH")
    for path in (args.kernel, args.root, args.system):
        if not path.is_file():
            parser.error(f"Missing {path}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "work/waffle/runs" / stamp
    out.mkdir(parents=True, exist_ok=False)

    def command(*items, timeout=15):
        result = subprocess.run([fastboot, "-s", "xnuloader", *map(str, items)],
                                capture_output=True, text=True, timeout=timeout)
        text = result.stdout + result.stderr
        with (out / "host.log").open("a") as log:
            log.write(" ".join(map(str, items)) + "\n" + text + "\n")
        if result.returncode:
            raise RuntimeError(text)
        return text

    if "platform: waffle" not in command("getvar", "platform"):
        raise RuntimeError("Expected the waffle loader; select Boot iOS in the PJD110 UEFI menu")
    if "kernel-supported: software-userland-test" not in command("getvar", "kernel-supported"):
        raise RuntimeError("This loader only supports early checkpoints; boot the userland test image")
    arguments = f"bootcpu={args.bootcpu} loader_return_after={args.seconds} fbscale={args.fbscale} epoch={int(time.time())}"
    if args.gpu_probe:
        arguments += f" waffle_gpu={args.gpu_probe}"
    payload = out / "payload.xnup"
    subprocess.run([sys.executable, str(ROOT / "loader/mkpayload.py"), "-o", str(payload), "--usb",
                    "--checkpoint", "0", "--cmdline", arguments,
                    f"kernel={args.kernel.resolve()}", f"ramdisk={args.root.resolve()}"], check=True)
    if payload.stat().st_size > 0x03f00000:
        raise RuntimeError("Kernel/root payload exceeds the loader's download limit")
    print(command("stage", payload, timeout=60), flush=True)
    if not args.reuse_system:
        command("oem", "ramdisk")
        print("Transferring the system RAM image…", flush=True)
        print(command("stage", args.system.resolve(), timeout=180), flush=True)
    # Preserve loader allocation addresses before a fatal kernel/GPU fault can
    # take USB down. RAM-only builds do not persist a log to flash.
    command("oem", "log")
    command("get_staged", out / "loader-before-run.log")
    print(command("oem", "run", "0"), flush=True)
    deadline = time.monotonic() + args.seconds + 90
    sequence = 0
    while time.monotonic() < deadline:
        time.sleep(0.05 if args.gpu_probe in (36,52,53,55,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94) else 5)
        response = command("getvar", "result")
        line = next((s for s in response.splitlines() if s.startswith("result: ")), "")
        sequence += 1
        command("oem", "log")
        log_path = out / f"kernel-{sequence}.log"
        command("get_staged", log_path)
        if not line.strip().removeprefix("result:").strip():
            line = result_from_log(log_path.read_text(errors="replace"))
            if not line:
                continue
        print(line, flush=True)
        if "running" not in line:
            command("oem", "log")
            command("get_staged", out / "kernel-final.log")
            (out / "result.txt").write_text(line + "\n")
            print(f"Logs: {out}", flush=True)
            final_text = (out / "kernel-final.log").read_text(errors="replace")
            if re.search(r"(?:^|\n)(?:\[[^\n]*\]: )?panic\(cpu \d", final_text):
                (out / "result.txt").write_text(line + "\nKERNEL PANIC (see kernel-final.log)\n")
                raise RuntimeError(f"Kernel panicked before returning; logs: {out}")
            if args.gpu_probe in (93,94) and not all(marker in final_text for marker in (
                    "FW_HOLD verified CX=100 MX=100; dedicated clients retained until reset; no clock writes",
                    f"PLL{args.gpu_probe} verified firmware CX/MX256 handoff",
                    f"NATIVE{args.gpu_probe} startup GMU625 PLL1250 ready=1",
                    f"NATIVE{args.gpu_probe} runtime GMU260 PLL520",
                    f"NATIVE{args.gpu_probe} detached and PLL scalar restore=1 owned=0",
                    f"NATIVE{args.gpu_probe} clock control passed=1")):
                raise RuntimeError(f"NATIVE{args.gpu_probe} clock session did not pass; logs: {out}")
            if args.gpu_probe == 92 and not all(marker in final_text for marker in (
                    "FW_HOLD verified CX=100 MX=100; dedicated clients retained until reset; no clock writes",
                    "PLL92 verified firmware CX/MX256 handoff",
                    "PLL92 1250MHz locked", "PLL92 520MHz locked",
                    "PLL92 scalar restore=1 owned=0",
                    "PLL92 control passed=1; no GMU firmware or CP started",
                    "clock controls restored", "probe ended; returning to loader")):
                raise RuntimeError(f"PLL92 isolated clock control did not pass; logs: {out}")
            if args.gpu_probe == 92:
                return
            if "waffle-gmu: REBOOT REQUIRED" in final_text:
                raise RuntimeError(f"GMU could not stop cleanly; reboot Android before another test; logs: {out}")
            if args.gpu_probe in (46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
                    f"AOP channel{args.gpu_probe} result=0 channel=ffff0000 ack=ffff0000 link=0000ffff linkack=0000ffff",
                    f"AOP channel{args.gpu_probe} cleanup complete")):
                raise RuntimeError(f"AOP channel roundtrip failed; logs: {out}")
            if args.gpu_probe in (48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
                    "ACD_ON ACK matched seq36 value=00000000 valid=1",
                    "ACD_TABLE ACK matched seq37 value=00000000 valid=1")):
                raise RuntimeError(f"ACD HFI prerequisite not acknowledged; logs: {out}")
            if args.gpu_probe in (50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "BAILOUT_TIMER_ON ACK matched seq38 value=00000000 valid=1" not in final_text:
                raise RuntimeError(f"Bailout timer not acknowledged; logs: {out}")
            if args.gpu_probe in (56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
                    "protected pool ready VA=100000000", "native trusted window base=f0000000 size=fffff000")):
                raise RuntimeError(f"Native protected window not confirmed; logs: {out}")
            if args.gpu_probe in (64,66) and "PRE_RAW_HOLD begin 5s; RAW not sent yet" not in final_text:
                raise RuntimeError(f"RAW64 live snapshot missing; logs: {out}")
            if args.gpu_probe in (90,91,93,94) and f"SEC_STALL{args.gpu_probe} CB2 SCTLR=000000a7; CFIE masked" not in final_text:
                raise RuntimeError(f"Protected CB2 stall policy not confirmed; logs: {out}")
            if args.gpu_probe in (88,89,90,91,93,94) and not re.search(r"GMU 200MHz GPLL0, hub 200MHz requested; GMU_CFG=[0-9a-f]+ valid=1",final_text):
                raise RuntimeError(f"GMU 200MHz clock readback not confirmed; logs: {out}")
            if args.gpu_probe == 87 and not all(f"PLL87_READY pll={i} MODE=" in final_text for i in range(2)):
                raise RuntimeError(f"Post-prepare GPU PLL snapshot incomplete; logs: {out}")
            if args.gpu_probe == 87 and not all(f"PLL87 pll={i} CONFIG=" in final_text or
                    re.search(rf"PLL87 pll={i} USER=.* CONFIG=",final_text) for i in range(2)):
                raise RuntimeError(f"GPU PLL snapshot incomplete; logs: {out}")
            if args.gpu_probe in (85,86,89,91,94) and f"HUPCF{args.gpu_probe} RAW fault readback armed; no fault clear/resume" not in final_text:
                raise RuntimeError(f"RAW fault readback not armed; logs: {out}")
            if args.gpu_probe in (84,85,86,87,88,89,90,91,93,94) and not re.search(r"fault-continue CB0 SCTLR=[0-9a-f]+ ready=1; CFIE masked",final_text):
                raise RuntimeError(f"Native HUPCF continuation policy was not confirmed; logs: {out}")
            if args.gpu_probe in (83,84,85) and f"SMMU{args.gpu_probe} CB0 SCTLR=" not in final_text:
                raise RuntimeError(f"CB0 readback snapshot missing; logs: {out}")
            if args.gpu_probe in (81,82,83,84,85,86,87,88,89,90,91,93,94) and "GPU split TTBR1 enabled=1 TCR=b5193519" not in final_text:
                raise RuntimeError(f"Native 4KB TG1 encoding was not confirmed; logs: {out}")
            if args.gpu_probe in (79,81,83,84,87,88,90,93) and not all(marker in final_text for marker in (
                    "POST_PREPARE_QUERY ACK matched seq42 value=00000001 valid=1",
                    f"QUERY{args.gpu_probe} post-prepare query passed; no RAW sent")):
                raise RuntimeError(f"SEQ79 post-prepare query did not pass; logs: {out}")
            if args.gpu_probe == 78 and "STATE78 TRUST=" not in final_text:
                raise RuntimeError(f"CP state snapshot absent; logs: {out}")
            if args.gpu_probe == 77 and "TIMER77 after hold remaining_us=" not in final_text:
                raise RuntimeError(f"Timer hold control incomplete; logs: {out}")
            if args.gpu_probe in (75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "NATIVE_DDR_AB ACK matched seq41 value=00000000 valid=1" not in final_text:
                raise RuntimeError(f"Native DDR AB vote failed; logs: {out}")
            if args.gpu_probe == 74 and "QUERY74 post-prepare query passed; no RAW sent" not in final_text:
                raise RuntimeError(f"Post-prepare HFI query failed; logs: {out}")
            if args.gpu_probe in (72,73,74) and "allocation GPU permissions VA=1ff8000502000 size=4096 flags=339 applied" not in final_text:
                raise RuntimeError(f"GPU allocation permissions not confirmed; logs: {out}")
            if args.gpu_probe in (69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "ACD_LOG_EVENT_ON ACK matched seq39 value=00000000 valid=1" not in final_text:
                raise RuntimeError(f"ACD log event ACK missing; logs: {out}")
            if args.gpu_probe == 67 and not all(marker in final_text for marker in (
                    "RAW_STAGE67 debug preflight passed", "RAW_STAGE67 staged/restored words=11",
                    "no publication or doorbell")):
                raise RuntimeError(f"RAW staging control did not complete; logs: {out}")
            if args.gpu_probe >= 65 and "native ACD-first HFI order active" not in final_text:
                raise RuntimeError(f"Native ACD-first HFI ordering not confirmed; logs: {out}")
            if args.gpu_probe >= 63:
                if "native optional-off profile: NAP/PREEMPTION/LPAC messages omitted" not in final_text or any(marker in final_text for marker in ("NAP_OFF ACK", "PREEMPTION_OFF ACK", "LPAC_OFF ACK")):
                    raise RuntimeError(f"Native optional-off profile not confirmed; logs: {out}")
            if args.gpu_probe == 62 and not re.search(r"LLCC62 GPU GBIF_SCACHE_CNTL0=[0-9a-f]{8} GBIF_SCACHE_CNTL1=[0-9a-f]{8}; RAW not sent", final_text):
                raise RuntimeError(f"GPU LLCC routing snapshot missing; logs: {out}")
            if args.gpu_probe == 61 and not all(marker in final_text for marker in (
                    "LLCC61 sid=9 ", "LLCC61 sid=11 ",
                    "LLCC61 read-only snapshot complete; no LLCC or GPU writes")):
                raise RuntimeError(f"LLCC read-only snapshot did not complete; logs: {out}")
            if args.gpu_probe == 60 and "RESTORE_SNAPSHOT complete probe=60 words=154; RAW not sent" not in final_text:
                raise RuntimeError(f"Full restore snapshot did not complete; logs: {out}")
            if args.gpu_probe == 59 and not all(marker in final_text for marker in (
                    "RAM_LOG_MANIFEST complete probe=59 pages=5", "PRE_RAW_HOLD end; publishing RAW")):
                raise RuntimeError(f"RAW RAM-log export did not complete; logs: {out}")
            if args.gpu_probe == 58 and not all(marker in final_text for marker in (
                    "RAM_LOG_MANIFEST complete probe=58 pages=5", "RAMLOG_HOLD end; RAW not sent")):
                raise RuntimeError(f"RAM-log export control did not complete; logs: {out}")
            if args.gpu_probe == 45 and not all(marker in final_text for marker in (
                    "AOP QMP magic=4d41494c version=1", "geometry=1",
                    "AOP QMP preflight complete; no mailbox or GPU writes")):
                raise RuntimeError(f"AOP QMP read-only preflight did not complete; logs: {out}")
            if args.gpu_probe and args.gpu_probe >= 8 and args.gpu_probe not in (27,28,29,45,46,47,61):
                if "waffle-iommu: GMU test passed" not in final_text:
                    raise RuntimeError(f"GPU probe{args.gpu_probe} did not pass; logs: {out}")
                if args.gpu_probe >= 10 and not re.search(r"HFI init status=[0-9a-f]+ ready=1", final_text):
                    raise RuntimeError(f"HFI was not ready; logs: {out}")
                if args.gpu_probe >= 11 and not re.search(r"GET_VALUE122 ACK matched seq1 value=[0-9a-f]+ valid=1", final_text):
                    raise RuntimeError(f"HFI query was not acknowledged; logs: {out}")
                if args.gpu_probe >= 12 and "PERF_TABLE ACK matched seq2 value=00000000 valid=1" not in final_text:
                    raise RuntimeError(f"HFI performance table was not acknowledged; logs: {out}")
                if args.gpu_probe >= 13 and "BW_TABLE ACK matched seq3 value=00000000 valid=1" not in final_text:
                    raise RuntimeError(f"HFI bandwidth table was not acknowledged; logs: {out}")
                if args.gpu_probe >= 14 and f"CORE_FW_START ACK matched seq{9 if args.gpu_probe >= 41 else 8 if args.gpu_probe >= 24 else 6} value=00000000 valid=1" not in final_text:
                    raise RuntimeError(f"GMU core firmware did not start; logs: {out}")
                if args.gpu_probe >= 15 and ("RSC/PDC Gen7.9 sequence readback=matches" not in final_text or
                                            ("RSC/PDC configuration restored" not in final_text and
                                             "RSC/PDC retained in native asleep state" not in final_text)):
                    raise RuntimeError(f"Power sequence prepare/restore failed; logs: {out}")
                if args.gpu_probe >= 16 and args.gpu_probe < 25 and (not re.search(r"PREPARE_SLUMBER ACK matched seq(?:7|8|14) value=00000000 valid=1", final_text) or
                                            "RSC sleep complete=1" not in final_text):
                    raise RuntimeError(f"GMU/RSC sleep sequence did not complete; logs: {out}")
                if args.gpu_probe >= 17 and args.gpu_probe < 25 and (f"MINIMUM_DCVS ACK matched seq{13 if args.gpu_probe >= 24 else 7} value=00000000 valid=1" not in final_text or
                                            "SCM GPU_INIT_REGS status=0" not in final_text):
                    raise RuntimeError(f"Minimum GPU vote/secure init did not pass; logs: {out}")
                if args.gpu_probe >= 18 and args.gpu_probe < 25 and ("OOB_GPU ack=1 GXon=1" not in final_text or
                                            "GX registers RBBM=" not in final_text):
                    raise RuntimeError(f"GPU power-on/register access did not pass; logs: {out}")
                if args.gpu_probe >= 19 and ("GPU SID0 translation matches allocated PA" not in final_text or
                                            "GPU context0 restored TLB=done faults=00000000" not in final_text):
                    raise RuntimeError(f"GPU context translation/cleanup did not pass; logs: {out}")
                if args.gpu_probe in (20,24) and ("SQE/AQE base readback=matches" not in final_text or
                                            "SQE/AQE register restore=matches" not in final_text):
                    raise RuntimeError(f"GPU firmware mapping/register test did not pass; logs: {out}")
                if args.gpu_probe == 21 and "CP init result=1" not in final_text:
                    raise RuntimeError(f"GPU command processor did not initialize; logs: {out}")
                if args.gpu_probe == 22 and "CP disabled setup result=1 restore=1" not in final_text:
                    raise RuntimeError(f"GPU disabled CP setup/restore did not pass; logs: {out}")
                if args.gpu_probe == 23 and "CP enable-only result=1" not in final_text:
                    raise RuntimeError(f"GPU CP startup without packets did not pass; logs: {out}")
                if args.gpu_probe >= 24 and "HWSCHED feature preflight result=1" not in final_text:
                    raise RuntimeError(f"GPU HWSCHED feature preflight did not pass; logs: {out}")
                if args.gpu_probe == 25 and "valid_memalloc=1" not in final_text:
                    raise RuntimeError(f"GPU HWSCHED START allocation request not captured; logs: {out}")
                if args.gpu_probe in (26,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not re.search(r"HWSCHED START ACK status=00000000 allocations=[1-9][0-9]* bytes=[0-9]+ valid=1", final_text):
                    raise RuntimeError(f"GPU HWSCHED memory handshake did not complete; logs: {out}")
            if args.gpu_probe in (27,28) and not all(marker in final_text for marker in (
                    f"SCM {'table' if args.gpu_probe==28 else 'protected'} page roundtrip=1", "waffle-iommu: GMU test passed",
                    "GPU context0 restored TLB=done faults=00000000")):
                raise RuntimeError(f"Protected page ownership roundtrip did not pass; logs: {out}")
            if args.gpu_probe == 29 and not all(marker in final_text for marker in (
                    "GPU protected SID2 translation=1", "protected context result=1 resources_returned=1",
                    "GPU context2 restored TLB=done faults=00000000",
                    "GPU context0 restored TLB=done faults=00000000")):
                raise RuntimeError(f"Protected GPU context translation/cleanup did not pass; logs: {out}")
            if args.gpu_probe in (30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
                    "protected pool ready", "protected pool released, all pages HLOS-owned",
                    "GPU context2 restored TLB=done faults=00000000")):
                raise RuntimeError(f"Persistent protected GPU pool did not clean up; logs: {out}")
            if args.gpu_probe in (31,32) and not all(marker in final_text for marker in (
                    "MINIMUM_DCVS ACK matched seq32 value=00000000 valid=1",
                    "OOB_GPU ack=1 GXon=1", "Gen7 native configuration result=0",
                    "Gen7 restore list ready VA=80070000 bytes=616",
                    "PREPARE_SLUMBER ACK matched seq33 value=00000000 valid=1",
                    "RSC sleep complete=1")):
                raise RuntimeError(f"Native disabled Gen7 configuration/slumber did not pass; logs: {out}")
            if args.gpu_probe == 32 and "Gen7 HWCG result=0 TXDONE=1" not in final_text:
                raise RuntimeError(f"Native Gen7 clock-gating handshake did not pass; logs: {out}")
            if args.gpu_probe in (33,38,40,42,44,49,51,53,55,57,59,64,66,68,70,86,89,91,94) and not all(marker in final_text for marker in (
                    "MINIMUM_DCVS ACK matched seq32 value=00000000 valid=1",
                    "OOB_GPU ack=1 GXon=1", f"CP_INIT_RAW ACK matched seq{42 if args.gpu_probe in (86,89,91,94) else 34}",
                    "Gen7 polled CP start result=0 detail=0",
                    f"PREPARE_SLUMBER ACK matched seq{43 if args.gpu_probe in (86,89,91,94) else 35} value=00000000 valid=1",
                    "RSC sleep complete=1",
                    "Gen7 CP lifecycle released after full collapse; no gated GX access")):
                raise RuntimeError(f"Polled CP init or full-collapse cleanup did not pass; logs: {out}")
            if args.gpu_probe in (34,37,39,41,43,48,50,52,54,56,58,60,62,63,65,67,69,72,74,75,77,78,79,81,83,84,87,88,90,93) and not all(marker in final_text for marker in (
                    "MINIMUM_DCVS ACK matched seq32 value=00000000 valid=1",
                    "OOB_GPU ack=1 GXon=1",
                    "Gen7 live preparation passed HWCG=3; hold until collapse, RAW not sent",
                    f"PREPARE_SLUMBER ACK matched seq{43 if args.gpu_probe in (79,81,83,84,87,88,90,93) else 35} value=00000000 valid=1",
                    "RSC sleep complete=1",
                    "Gen7 CP lifecycle released after full collapse; no gated GX access")):
                raise RuntimeError(f"Live pre-CP preparation/collapse did not pass; logs: {out}")
            if args.gpu_probe in (35,36,71,73,76,80,82,85) and not all(marker in final_text for marker in (
                    "MINIMUM_DCVS ACK matched seq32 value=00000000 valid=1",
                    "OOB_GPU ack=1 GXon=1", f"CP_THREAD_RAW ACK matched seq{42 if args.gpu_probe in (80,82,85) else 34}",
                    "Gen7 thread-only result=0 detail=0 ACK=1",
                    f"PREPARE_SLUMBER ACK matched seq{43 if args.gpu_probe in (80,82,85) else 35} value=00000000 valid=1",
                    "RSC sleep complete=1",
                    "Gen7 CP lifecycle released after full collapse; no gated GX access")):
                raise RuntimeError(f"CP thread-control-only or full cleanup did not pass; logs: {out}")
            if args.gpu_probe == 36 and "stall diagnostics armed for CB0/CB1/CB2; CFIE masked" not in final_text:
                raise RuntimeError(f"Stalled-fault diagnostic contexts were not armed; logs: {out}")
            if args.gpu_probe in (37,38,39,40,41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "SCM CP SMMU aperture CB0 status=0" not in final_text:
                raise RuntimeError(f"CP SMMU aperture not configured; logs: {out}")
            if args.gpu_probe in (39,40,41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
                    "GPU split TTBR1 enabled=1", "native global GPU VA SQE="+("1ff8000410000" if args.gpu_probe>=54 else "1ff8080010000"))):
                raise RuntimeError(f"Native split GPU VA setup not confirmed; logs: {out}")
            if args.gpu_probe in (41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "DMS_CAPABILITY_ON ACK matched seq8 value=00000000 valid=1" not in final_text:
                raise RuntimeError(f"GMU DMS capability not enabled; logs: {out}")
            if args.gpu_probe in (43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and "BCL_ON ACK matched seq4 value=00000000 valid=1" not in final_text:
                raise RuntimeError(f"Native BCL feature not enabled; logs: {out}")
            if not line.startswith("result: returned "):
                raise RuntimeError(f"Unexpected kernel result: {line}")
            return
        if not args.gpu_probe and (sequence in (2, 6, 9, 11) or (args.seconds > 60 and sequence % 6 == 0)):
            command("oem", "screenshot")
            command("get_staged", out / f"screen-{sequence}.raw")
    raise RuntimeError(f"No final result yet; logs: {out}. No automatic reboot was requested.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        sys.exit(f"waffle-run: {error}")
