#!/usr/bin/env python3
"""Run the experimental PJD110 RAM port after selecting Boot iOS in UEFI."""
import argparse
import json
from datetime import datetime, timezone
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import struct
import zlib

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


def uploaded_image_pixels():
    data=(ROOT/'tools/tests/fixtures/waffle-input16.ppm').read_bytes()
    if len(data)!=781 or data[:13]!=b'P6\n16 16\n255\n':raise RuntimeError("Invalid uploaded image fixture")
    return [int.from_bytes(data[i:i+3]+b'\xff','little') for i in range(13,len(data),3)]


def extract_gpu_image(text, compute_mode, image=1):
    blocks={}
    for offset,values in re.findall(r"waffle-gmu: IMAGE pixels offset=(\d+) values=([0-9a-f]{8}(?:/[0-9a-f]{8}){7})",text):
        offset=int(offset);pixels=[int(x,16) for x in values.split('/')]
        if offset%8 or offset<0 or offset>248 or (offset in blocks and blocks[offset]!=pixels):
            raise RuntimeError("Conflicting or invalid GPU image readback")
        blocks[offset]=pixels
    if set(blocks)!=set(range(0,256,8)):
        raise RuntimeError("Incomplete GPU pixel readback")
    pixels=[v for offset in range(0,256,8) for v in blocks[offset]]
    expected=(uploaded_image_pixels() if image>=2 else [0xff000000|i for i in range(256)]) if compute_mode==2 else [0xdead0000+i for i in range(256)]
    if pixels!=expected:raise RuntimeError("GPU pixel pattern did not match")
    return pixels


def extract_copy_jobs(text):
    blocks={}
    for fence,offset,values in re.findall(r"COPY_JOB pixels fence=(\d+) offset=(\d+) values=([0-9a-f]{8}(?:/[0-9a-f]{8}){7})",text):
        key=(int(fence),int(offset));pixels=[int(v,16) for v in values.split('/')]
        if key[0] not in (1,2,3) or key[1] not in range(0,256,8) or (key in blocks and blocks[key]!=pixels):
            raise RuntimeError("Invalid or conflicting copy job pixels")
        blocks[key]=pixels
    if set(blocks)!={(f,o) for f in (1,2,3) for o in range(0,256,8)}:raise RuntimeError("Incomplete copy job pixels")
    inputs=uploaded_image_pixels();result=[]
    for fence,mask in enumerate((0x00010101,0x002a173c,0x0065ab19),1):
        pixels=[v for offset in range(0,256,8) for v in blocks[fence,offset]]
        if pixels!=[v^mask for v in inputs]:raise RuntimeError("Stale or corrupt copy job result")
        result.append(pixels)
    return result


def write_gpu_png(path, pixels):
    if len(pixels)!=256:raise RuntimeError("Expected 16x16 GPU image")
    rgba=b''.join(word.to_bytes(4,'little') for word in pixels)
    raw=b''.join(b'\0'+rgba[y*64:(y+1)*64] for y in range(16))
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


def validate_msm_log(text):
    markers=["MSM registered BO2 submit191 root_only=1 gated=1",
      "AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1",
      "full GPU owner returned live to init caller; no mutex held","SERVICE begin root_live=1 serialized=1",
      "USER_BO published VA=100000000 pages=4 lower39=1 unprivileged=1",
      "MSM open pid=1 actual_gpu_bos=2 user_commands=1","COPY_SEQUENCE begin jobs=3 kernel_caller=1",
      "MSM gem_new handle=1 bytes=16384 VA=1ff8000478000","MSM gem_new handle=2 bytes=16384 VA=100000000",
      "MSM invalid_command refused=1 next_fence=1"]
    for fence in (1,2,3):
        markers += [f"MSM_COMMAND accepted fence={fence} words=191 source=user_bo",
          "GLSL_JOB mode=dispatch command_words=191 bindless=1 source=GLSL450",
          f"COPY_JOB begin fence={fence} seq={43+fence} pixels=256",
          f"COMPUTE_IB ACK matched seq{43+fence} value=00000000 valid=1",
          f"DATA_BO checked=4096 wrong_words=0 fence={fence} independent=1",
          f"COPY_JOB done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0",
          f"COPY_CALLER fence={fence} checked=256 wrong=0",f"MSM submitted fence={fence} user_ib=1 bo_handles=2"]
    markers += ["MSM report pid=1 checks=768 wrong=0 fence=3 negative=7",
      "MSM gem_close handle=1 retained_until_context_stop=1","MSM gem_close handle=2 retained_until_context_stop=1",
      "SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session",
      "USER_BO released after GPU stop and context detach","DYNAMIC_BO released after GPU stop and context detach",
      "SMMU_OWNER released after child stop and context detach","CLOCK_OWNER released before CX restore result=1",
      "POWER_OWNER released after clock child, CX and CFG restore result=1",
      "AOP_OWNER released after power child and channel restore result=1 transport=0",
      "SERVICE end consumed=1 result=1","MSM close passed=1 report=1 context_null=1"]
    # Repeated identical GLSL markers must be found after each previous fence.
    cursor=0
    for marker in markers:
        at=text.find(marker,cursor)
        if at<0:raise RuntimeError("MSM BO/command/lifetime proof missing: "+marker)
        cursor=at+len(marker)
    if "REBOOT REQUIRED" in text:raise RuntimeError("MSM requires reset")
    return extract_copy_jobs(text)[-1]


def validate_mapped_log(text):
    pixels=validate_msm_log(text)
    markers=["MSM_MAP enabled IOMemoryMap=1 revoke_before_submit=1",
      "MSM_MAP mapped handle=1 bytes=16384 readonly=0 direct_backing=1",
      "MSM_MAP mapped handle=2 bytes=16384 readonly=0 direct_backing=1",
      "MSM_MAP revoked_before_validate next_fence=1","MSM invalid_command refused=1 next_fence=1"]
    for fence in (1,2,3):
        markers += ["MSM_MAP mapped handle=1 bytes=16384 readonly=0 direct_backing=1",
          "MSM_MAP mapped handle=2 bytes=16384 readonly=0 direct_backing=1",
          f"MSM_MAP revoked_before_validate next_fence={fence}",
          f"MSM_COMMAND accepted fence={fence} words=191 source=user_bo",
          f"MSM submitted fence={fence} user_ib=1 bo_handles=2",
          "MSM_MAP mapped handle=2 bytes=16384 readonly=1 direct_backing=1","MSM_MAP unmapped handle=2"]
    cursor=0
    for marker in markers:
        at=text.find(marker,cursor)
        if at<0:raise RuntimeError("Direct BO mapping/handoff missing: "+marker)
        cursor=at+len(marker)
    if "waffle-mesa-probe: mapped_bo=1 upload_download_copy=0 handoff=unmap_before_submit" not in text or re.search(r"MSM_TRANSFER operation=\w+ bytes=16384",text):
        raise RuntimeError("Mapped BO used copy transfers or actual client marker missing")
    return pixels


def extract_gl_pixels(text):
    blocks={}
    for offset,values in re.findall(r"waffle-gl-user: pixels offset=(\d+) values=([0-9a-f]{8}(?:/[0-9a-f]{8}){7})",text):
        offset=int(offset);words=[int(v,16) for v in values.split('/')]
        if offset not in range(0,256,8) or (offset in blocks and blocks[offset]!=words):raise RuntimeError("Invalid or conflicting GL readback")
        blocks[offset]=words
    if set(blocks)!=set(range(0,256,8)):raise RuntimeError("Incomplete actual GL pixel readback")
    pixels=[v for offset in range(0,256,8) for v in blocks[offset]]
    expected=[0xff0040ff if 4*x+2>2*y+1 and 4*x+2<63-2*y else 0xff000000 for y in range(16) for x in range(16)]
    if pixels!=expected:raise RuntimeError("Actual GL triangle pixels differ from independent reference")
    return pixels


def gl_completed_fences(text):
    fences={}
    for fence,seq,control in re.findall(r"GENERAL_SUBMIT done fence=(\d+) seq=(\d+) control=([0-9a-f]{8}) checked=4096 wrong_words=0",text):
        fence,seq,control=int(fence),int(seq),int(control,16)
        if seq!=43+fence or control!=fence or (fence in fences and fences[fence]!=(seq,control)):raise RuntimeError("Invalid GL GPU completion token")
        fences[fence]=(seq,control)
    if not fences or set(fences)!=set(range(1,max(fences)+1)):raise RuntimeError("Missing or discontinuous GL GPU fences")
    return max(fences)


def validate_gl_log(text):
    if "Library not loaded:" in text:
        raise RuntimeError("GL process failed before main: "+re.search(r"Library not loaded: ([^\n]+)",text)[1])
    pixels=extract_gl_pixels(text);count=gl_completed_fences(text)
    if "REBOOT REQUIRED" in text or "GENERAL_SUBMIT mismatch" in text:raise RuntimeError("GL GPU ownership or completion failed")
    markers=["GENERAL registered root_only=1 gated=1 BO_limit=32",
       "waffle-gl-init: exec actual Darwin Mesa probe pid=1",
       "waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16",
       "AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1",
       "full GPU owner returned live to init caller; no mutex held","SERVICE begin root_live=1 serialized=1",
       "GENERAL open pid=1 BO_limit=32 heap_bytes=33554432"]
    cursor=0
    for marker in markers:
        at=text.find(marker,cursor)
        if at<0:raise RuntimeError("GL start/lifetime proof missing: "+marker)
        cursor=at+len(marker)
    if "waffle-gl-user: renderer=FD750" not in text:raise RuntimeError("Actual FD750 GL renderer not selected")
    for fence in range(1,count+1):
        starts=list(re.finditer(rf"GENERAL_SUBMIT begin fence={fence} seq={43+fence} root_words=(\d+) kernel_tail=15 extra_IB_depth=0",text[cursor:]))
        if not starts or not 1<=int(starts[0][1])<=1024:raise RuntimeError("GL root command publication not proved")
        cursor+=starts[0].end()
        for marker in (f"GENERAL_IB ACK matched seq{43+fence} value=00000000 valid=1",
          f"GENERAL_SUBMIT done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0",
          f"GENERAL submitted fence={fence}"):
            at=text.find(marker,cursor)
            if at<0:raise RuntimeError("GL GPU fence not confirmed: "+marker)
            cursor=at+len(marker)
    buffers={}
    for index,va,logical,allocated,flags,pages in re.findall(r"GENERAL_BO published index=(\d+) VA=([0-9a-f]+) bytes=(\d+) allocated=(\d+) flags=([0-9a-f]+) pages=(\d+)",text):
        key=int(index);value=(int(va,16),int(logical),int(allocated),int(flags,16),int(pages))
        if key in buffers and buffers[key]!=value:raise RuntimeError("Conflicting GL BO publication")
        buffers[key]=value
    if not buffers or set(buffers)!=set(range(1,len(buffers)+1)) or len(buffers)>32:raise RuntimeError("Missing GL BO publication")
    expected_va=0x100000000
    for key in sorted(buffers):
        va,logical,allocated,flags,pages=buffers[key]
        if va!=expected_va or not 0<logical<=8*1024*1024 or allocated!=(logical+16383)&~16383 or flags not in (0x20000,0x20002) or pages!=allocated//4096:
            raise RuntimeError("Invalid GL BO range/permission publication")
        expected_va+=allocated
    if expected_va>0x102000000:raise RuntimeError("GL BO heap budget exceeded")
    markers=["waffle-gl-user: checked=256 wrong=0 filled=128 GL_error=0",
       f"GENERAL_BO released after GPU stop and context detach count={len(buffers)}",
       "SMMU_OWNER released after child stop and context detach","CLOCK_OWNER released before CX restore result=1",
       "POWER_OWNER released after clock child, CX and CFG restore result=1",
       "AOP_OWNER released after power child and channel restore result=1 transport=0","SERVICE end consumed=1 result=1"]
    for marker in markers:
        at=text.find(marker,cursor)
        if at<0:raise RuntimeError("GL result/teardown missing: "+marker)
        cursor=at+len(marker)
    close=re.search(rf"GENERAL close passed=1 completed={count} buffers=(\d+) context_null=1",text[cursor:])
    if not close or int(close[1])!=len(buffers):raise RuntimeError("GL BO backing lifetime not confirmed")
    if "waffle-gl-user: result=1 actual_OSMesa=1" not in text[cursor+close.end():]:raise RuntimeError("GL process did not finish successfully")
    return pixels


def validate_aop_owner_log(text, compute_mode=0, image=False):
    """Require actual GPU results and child-first teardown for the owned path."""
    if image==13:return validate_gl_log(text)
    if image==12:return validate_mapped_log(text)
    if image==11:return validate_msm_log(text)
    markers=[
        "AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1",
        "full GPU owner returned live to init caller; no mutex held",
    ]
    if image==9:
        markers += ["GLSL_JOB mode=prepare command_words=191 bindless=1 source=GLSL450",
                    "COMPUTE_IB ACK matched seq44 value=00000000 valid=1",
                    "DATA_BO checked=4096 wrong_words=0 fence=1 independent=1",
                    "COPY_JOB done fence=1 seq=44 control=00000001 checked=4096 wrong_words=0",
                    "GLSL_PREPARE output_poison=256 wrong=0 dispatch=0",
                    "SESSION result=1 submitted=1 completed=1 next_sequence=45 OOB=1; bounded kernel session"]
    elif image>=4:
        markers += ["COPY_SEQUENCE begin jobs=3 kernel_caller=1"]
        for fence in (1,2,3):
            markers += [f"COPY_JOB begin fence={fence} seq={43+fence} pixels=256",
                        f"COMPUTE_IB ACK matched seq{43+fence} value=00000000 valid=1",
                        f"COPY_JOB done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0",
                        f"COPY_CALLER fence={fence} checked=256 wrong=0"]
        markers += ["SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session"]
    elif compute_mode:
        expected_pixels=uploaded_image_pixels() if image>=2 else [0xff000000|i for i in range(256)]
        if image>=2:markers += ["IMAGE_COPY input_word=3328 output_word=3072 pixels=256"]
        values="/".join(f"{expected_pixels[i] if image and compute_mode==2 else i if compute_mode==2 else 0xdead0000+i:08x}" for i in range(8))
        if image:markers += [f"IMAGE begin width=16 height=16 pixels=256 dispatch={int(compute_mode==2)}"]
        markers += [f"COMPUTE begin mode={compute_mode} dispatch={int(compute_mode==2)} words=184 output_poison=1",
            "COMPUTE_IB ACK matched seq44 value=00000000 valid=1",
            f"COMPUTE values={values} control=00000001 checked=4096 wrong_words=0 mode={compute_mode}",
            "SESSION result=1 submitted=1 completed=1 next_sequence=45 OOB=1; bounded kernel session"]
    else:
        for fence in (1,2,3):
            values="/".join(f"{word ^ (fence * 0x01010101):08x}" for word in
                            (0x57414646,0x4c454750,0x13579bdf,0x2468ace0))
            markers.append(f"SESSION fence={fence} seq={43+fence} values={values} wrong_words=0")
    markers += [
        "SMMU_OWNER released after child stop and context detach",
        "CLOCK_OWNER released before CX restore result=1",
        "POWER_OWNER released after clock child, CX and CFG restore result=1",
        "AOP_OWNER released after power child and channel restore result=1 transport=0",
    ]
    if image==3:
        start=markers.index("SESSION result=1 submitted=1 completed=1 next_sequence=45 OOB=1; bounded kernel session")
        markers[start:start]=["PRESENT begin format=BGRA8 x=592 y=1456 width=256 height=256 cpu_blit=1",
                             "PRESENT write checked=65536 wrong=0", "PRESENT restore checked=65536 wrong=0"]
    if image==5:
        at=markers.index("COPY_SEQUENCE begin jobs=3 kernel_caller=1")
        markers[at:at]=["SERVICE begin root_live=1 serialized=1","SERVICE worker started separate_thread=1"]
        at=markers.index("COPY_JOB begin fence=1 seq=44 pixels=256")
        markers.insert(at,"SERVICE busy submit_refused=1 close_refused=1 retained=1")
        at=markers.index("SMMU_OWNER released after child stop and context detach")
        markers.insert(at,"SERVICE worker finished result=1")
        markers += ["SERVICE end consumed=1 result=1","SERVICE probe passed=1 context_null=1"]
    if 6<=image<=8 or image==10:
        markers.insert(0,"USERDEV registered abi=1 pixels=256 mode=0600; no GPU opened")
        at=markers.index("COPY_SEQUENCE begin jobs=3 kernel_caller=1")
        markers[at:at]=["SERVICE begin root_live=1 serialized=1","USERDEV open pid=1 demand_context=1"]
        at=markers.index("COPY_JOB begin fence=1 seq=44 pixels=256")
        markers[at:at]=["USERDEV busy_open refused=1 pid=1","USERDEV invalid_copy refused=1 pid=1 version=2 words=256",
                       "USERDEV invalid_copy refused=1 pid=1 version=1 words=255","USERDEV unknown_ioctl refused=1 pid=1"]
        for fence in (1,2,3):
            at=markers.index(f"COPY_CALLER fence={fence} checked=256 wrong=0")
            markers.insert(at+1,f"USERDEV returned pid=1 fence={fence} words=256")
        at=markers.index("SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session")
        markers.insert(at,"USERDEV report pid=1 checks=768 wrong=0 fence=3 negative=5")
        markers += ["SERVICE end consumed=1 result=1","USERDEV close pid=1 passed=1 report=1 context_null=1"]
    if image in (7,8):
        at=markers.index("COPY_JOB begin fence=1 seq=44 pixels=256")
        markers.insert(at,"DATA_BO published separately VA=8007c000 pages=4 aliases=2 unprivileged=1")
        for fence in (1,2,3):
            at=markers.index(f"COPY_JOB done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0")
            markers.insert(at,f"DATA_BO checked=4096 wrong_words=0 fence={fence} independent=1")
        at=markers.index("SMMU_OWNER released after child stop and context detach")
        markers.insert(at,"DATA_BO released after GPU stop and context detach")
    if image in (8,10):
        at=markers.index("COPY_JOB begin fence=1 seq=44 pixels=256")
        markers.insert(at,"GLSL_JOB mode=dispatch command_words=191 bindless=1 source=GLSL450")
    if image==9:
        at=markers.index("GLSL_JOB mode=prepare command_words=191 bindless=1 source=GLSL450")
        markers.insert(at,"DATA_BO published separately VA=8007c000 pages=4 aliases=2 unprivileged=1")
        at=markers.index("SMMU_OWNER released after child stop and context detach")
        markers.insert(at,"DATA_BO released after GPU stop and context detach")
    if image==10:
        at=markers.index("GLSL_JOB mode=dispatch command_words=191 bindless=1 source=GLSL450")
        markers.insert(at,"USER_BO published VA=100000000 pages=4 lower39=1 unprivileged=1")
        for fence in (1,2,3):
            at=markers.index(f"COPY_JOB done fence={fence} seq={43+fence} control={fence:08x} checked=4096 wrong_words=0")
            markers.insert(at,f"DATA_BO checked=4096 wrong_words=0 fence={fence} independent=1")
        at=markers.index("SMMU_OWNER released after child stop and context detach")
        markers.insert(at,"USER_BO released after GPU stop and context detach")
    positions=[text.find(marker) for marker in markers]
    if "REBOOT REQUIRED" in text or -1 in positions or positions!=sorted(positions):
        raise RuntimeError("Owned AOP lifetime, GPU memory results or child-first teardown not confirmed")
    return None if image==9 else extract_copy_jobs(text)[-1] if image>=4 else extract_gpu_image(text,compute_mode,image) if image else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60, choices=range(1, 301), metavar="1..300")
    parser.add_argument("--bootcpu", type=int, default=7, choices=range(1, 8))
    parser.add_argument("--fbscale", type=int, default=2, choices=(1, 2, 3), help="Render scale: 1 is faster, 2 is sharper")
    parser.add_argument("--reuse-system", action="store_true", help="Reuse the system image in this same loader session")
    parser.add_argument("--gpu-probe", type=int, choices=range(1, 95), help="Probe SM8650 GPU power/clocks/SMMU/firmware or AOP QMP; return before iOS starts")
    parser.add_argument("--gpu-access-matrix",action="store_true",help="Probe93 only: access-type ECATS after GMU shutdown, no CP RAW")
    parser.add_argument("--gpu-measure-clocks",action="store_true",help="Probe93 only: physically measure GFX/GMU clocks without RAW")
    parser.add_argument("--gpu-lpac-map",action="store_true",help="Probe93/94 only: validated LPAC SID1 mappings (94 sends CP_INIT)")
    parser.add_argument("--gpu-zap",action="store_true",help="E09: native PAS13 and secure transition after CP_INIT94; requires LPAC")
    parser.add_argument("--gpu-writeback",action="store_true",help="E10: GPU writes a guarded dedicated buffer after authenticated ZAP")
    parser.add_argument("--gpu-ib",action="store_true",help="E11: GPU fetches known writeback stream from dedicated BO")
    parser.add_argument("--gpu-session",action="store_true",help="E12: owned kernel session, three independent IB results and verified stop")
    parser.add_argument("--gpu-gl-context",action="store_true",help="E36 actual Darwin OSMesa GL renderer")
    parser.add_argument("--gpu-mapped",action="store_true",help="E33 direct mapped GPU BOs with revoke-before-submit")
    parser.add_argument("--gpu-mesa-transport",action="store_true",help="E32 require actual Mesa DRM shim marker and MSM proof")
    parser.add_argument("--gpu-msm",action="store_true",help="E31 actual MSM BO handles and user uploaded Mesa commands")
    parser.add_argument("--gpu-user-va",action="store_true",help="E30 64-bit lower GPU VA for GLSL data BO")
    parser.add_argument("--gpu-glsl",action="store_true",help="E29 Mesa GLSL shader: prepare1 or dispatch2")
    parser.add_argument("--gpu-data-bo",action="store_true",help="E28 user copies with separate GPU data BO")
    parser.add_argument("--gpu-user-copy",action="store_true",help="E27 static Darwin user process -> fixed-copy ioctl -> GPU")
    parser.add_argument("--gpu-worker",action="store_true",help="E26 parent-owned kernel worker and busy close refusal")
    parser.add_argument("--gpu-copy-jobs",action="store_true",help="E25 three caller-input copy jobs with GPU fences")
    parser.add_argument("--gpu-image-present",action="store_true",help="E24 CPU-present verified GPU image then restore framebuffer")
    parser.add_argument("--gpu-image-copy",action="store_true",help="E23 uploaded16x16 image copy; requires compute")
    parser.add_argument("--gpu-image",action="store_true",help="E22: compute-generated16x16 offscreen pixels; requires compute")
    parser.add_argument("--gpu-compute",type=int,choices=(1,2),help="E21: 1=state/control without dispatch; 2=eight-thread compute shader")
    parser.add_argument("--gpu-dynamic-bo",action="store_true",help="E20: allocate/map/bind test BO after GPU startup; requires session")
    parser.add_argument("--kernel", type=Path, default=KERNEL_DIR / "kernel")
    parser.add_argument("--root", type=Path, default=IMAGE_DIR / "root.packfs")
    parser.add_argument("--system", type=Path, default=IMAGE_DIR / "system.packfs")
    parser.add_argument("--fastboot", default=os.environ.get("FASTBOOT"))
    args = parser.parse_args()
    if sum((args.gpu_gl_context,args.gpu_msm,args.gpu_user_va,args.gpu_glsl,args.gpu_data_bo,args.gpu_user_copy,args.gpu_worker,args.gpu_copy_jobs,args.gpu_image_present,args.gpu_image_copy,args.gpu_image))>1:parser.error("Choose image ramp or uploaded image copy")
    if args.gpu_mesa_transport and not args.gpu_msm:parser.error("--gpu-mesa-transport requires --gpu-msm")
    if args.gpu_mapped and not (args.gpu_msm and args.gpu_mesa_transport):parser.error("--gpu-mapped requires MSM Mesa transport")
    image_kind=13 if args.gpu_gl_context else 12 if args.gpu_mapped else 11 if args.gpu_msm else 10 if args.gpu_user_va else (9 if args.gpu_compute==1 else 8) if args.gpu_glsl else 7 if args.gpu_data_bo else 6 if args.gpu_user_copy else 5 if args.gpu_worker else 4 if args.gpu_copy_jobs else 3 if args.gpu_image_present else 2 if args.gpu_image_copy else int(args.gpu_image)
    if image_kind>=3 and image_kind!=9 and args.gpu_compute!=2:parser.error("Presentation requires compute dispatch")
    args.gpu_image=bool(image_kind)
    if args.gpu_access_matrix and args.gpu_probe!=93:
        parser.error("--gpu-access-matrix requires prepare-only --gpu-probe 93")
    if args.gpu_measure_clocks and args.gpu_probe!=93:
        parser.error("--gpu-measure-clocks requires prepare-only --gpu-probe 93")
    if args.gpu_lpac_map and args.gpu_probe not in (93,94):
        parser.error("--gpu-lpac-map requires controlled --gpu-probe 93/94")
    if args.gpu_zap and (args.gpu_probe!=94 or not args.gpu_lpac_map):
        parser.error("--gpu-zap requires --gpu-probe94 and --gpu-lpac-map")
    if args.gpu_writeback and not args.gpu_zap:
        parser.error("--gpu-writeback requires --gpu-zap")
    if args.gpu_ib and not args.gpu_writeback:
        parser.error("--gpu-ib requires --gpu-writeback")
    if args.gpu_image and not args.gpu_compute:
        parser.error("--gpu-image requires --gpu-compute")
    if args.gpu_compute and not args.gpu_dynamic_bo:
        parser.error("--gpu-compute requires --gpu-dynamic-bo")
    if args.gpu_dynamic_bo and not args.gpu_session:
        parser.error("--gpu-dynamic-bo requires --gpu-session")
    if args.gpu_session and not args.gpu_ib:
        parser.error("--gpu-session requires --gpu-ib")
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
    if args.gpu_access_matrix:
        arguments += " waffle_ecats_access=1"
    if args.gpu_measure_clocks:
        arguments += " waffle_gpu_measure=1"
    if args.gpu_lpac_map:
        arguments += " waffle_lpac_map=1"
    if args.gpu_zap:
        arguments += " waffle_zap=1"
    if args.gpu_writeback:
        arguments += " waffle_writeback=1"
    if args.gpu_ib:
        arguments += " waffle_ib=1"
    if args.gpu_session:
        arguments += " waffle_session=1"
    if args.gpu_dynamic_bo:
        arguments += " waffle_dynamic_bo=1"
    if args.gpu_compute:
        arguments += f" waffle_compute={args.gpu_compute}"
    if args.gpu_image:
        arguments += f" waffle_image={image_kind}"
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
            image_pixels=None
            if args.gpu_session and not args.gpu_compute and not all(marker in final_text for marker in (
                    "SESSION OOB ownership transferred; init returned with GX retained",
                    "SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session",
                    "SESSION closed OOB_released=1 outstanding=0",
                    "SESSION destroyed after full stop; aliases and heap released",
                    *[f"SESSION_IB ACK matched seq{i} value=00000000 valid=1" for i in (44,45,46)])):
                raise RuntimeError(f"Owned session/multiple GPU results/stop not confirmed; logs: {out}")
            if args.gpu_gl_context and "Library not loaded:" in final_text:
                raise RuntimeError("GL process failed before main: "+re.search(r"Library not loaded: ([^\n]+)",final_text)[1])
            if args.gpu_dynamic_bo:
                markers=("full GPU owner returned live to init caller; no mutex held",
                    "SESSION rebound BO VA=1ff8000478000", "DYNAMIC_BO published after GPU startup VA=80078000 pages=4 aliases=2 unprivileged=1",
                    *(["GENERAL_SUBMIT done fence=1"] if image_kind==13 else ["COMPUTE values="] if args.gpu_compute else ["SESSION fence=1", "SESSION fence=2", "SESSION fence=3"]),
                    "DYNAMIC_BO released after GPU stop and context detach", "SMMU_OWNER released after child stop and context detach")
                positions=[final_text.find(marker) for marker in markers]
                if -1 in positions or positions!=sorted(positions):
                    raise RuntimeError(f"Dynamic BO publication/use/release not confirmed; logs: {out}")
            if args.gpu_ib and not args.gpu_session and "GPU_IB result=1 command_words=8; GPU fetch and writeback" not in final_text:
                raise RuntimeError(f"GPU indirect-buffer fetch/writeback not confirmed; logs: {out}")
            if args.gpu_writeback and not args.gpu_session and not all(marker in final_text for marker in (
                    "GPU_WRITEBACK ACK matched seq44 value=00000000 valid=1",
                    "GPU_WRITEBACK result=1 wrong_words=0 checked=4096; no draw")):
                raise RuntimeError(f"GPU memory result/guards not confirmed; logs: {out}")
            if args.gpu_zap and not all(marker in final_text for marker in (
                    "ZAP_LOAD authenticated=1 stage=4", "ZAP_UNSECURE ACK matched seq43 value=00000000 valid=1",
                    "ZAP_TRANSITION result=1 TRUST=00000000; no draw")):
                raise RuntimeError(f"Authenticated ZAP/native secure transition not confirmed; logs: {out}")
            if args.gpu_lpac_map and (not re.search(r"LPAC_MAP lifecycle=1 checks=[1-9][0-9]*; "+
                    ("no CP RAW" if args.gpu_probe==93 else "CP control completed"),final_text) or
                    "LPAC_MAP restored=1" not in final_text or
                    (args.gpu_probe==93 and ("RAW checkpoint" in final_text or "CP_INIT_RAW" in final_text))):
                raise RuntimeError(f"LPAC mapping/lifecycle incomplete or RAW appeared; logs: {out}")
            if args.gpu_measure_clocks and ("CLOCK_MEASURE result=1; no CP RAW" not in final_text or
                    "RAW checkpoint" in final_text or "CP_INIT_RAW" in final_text):
                raise RuntimeError(f"Clock measurement incomplete or RAW appeared; logs: {out}")
            if args.gpu_access_matrix and (not re.search(
                    r"ACCESS_MATRIX result=1 checks=[1-9][0-9]* allocations=[1-9][0-9]*; translation only, no RAW",final_text) or
                    "RAW checkpoint" in final_text or "CP_INIT_RAW" in final_text):
                raise RuntimeError(f"Access matrix did not pass or RAW appeared; logs: {out}")
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
            if args.gpu_session and b"AOP_OWNER begin returned" in args.kernel.read_bytes():
                image_pixels=validate_aop_owner_log(final_text, args.gpu_compute or 0, image_kind)
                if args.gpu_mesa_transport and "waffle-mesa-probe: transport=actual_drm_shim command_api=1 ioctl_api=1" not in final_text:
                    raise RuntimeError("Actual Mesa DRM shim transport not confirmed")
            elif args.gpu_probe in (46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not all(marker in final_text for marker in (
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
                    f"PREPARE_SLUMBER ACK matched seq{44+gl_completed_fences(final_text) if image_kind==13 else 47 if (4<=image_kind<=8 or image_kind in (10,11,12)) else 45 if args.gpu_compute else 47 if args.gpu_session else 45 if args.gpu_writeback else 44 if args.gpu_zap else 43 if args.gpu_probe in (86,89,91,94) else 35} value=00000000 valid=1",
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
            if args.gpu_probe in (37,38,39,40,41,42,43,44,48,49,50,51,52,53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,93,94) and not re.search(r"SCM CP SMMU aperture (?:selector=0 )?CB0 status=0(?: |$)",final_text):
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
            if args.gpu_image and args.gpu_compute==2:
                if image_pixels is None:raise RuntimeError("No GPU pixels validated")
                write_gpu_png(out/"first-gpu-frame.png",image_pixels)
                (out/"gpu-pixels.json").write_text(json.dumps({'width':16,'height':16,'rgba_words':image_pixels,'source':'actual kernel GPU readback'},indent=2)+"\n")
                print(f"GPU image: {out/'first-gpu-frame.png'}",flush=True)
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
