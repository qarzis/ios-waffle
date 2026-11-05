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


def gl_sequence(completed):
    return (43+completed%4094)%4094+1


def gl_completed_fences(text):
    fences={}
    for fence,seq,control in re.findall(r"GENERAL_SUBMIT done fence=(\d+) seq=(\d+) control=([0-9a-f]{8}) checked=4096 wrong_words=0",text):
        fence,seq,control=int(fence),int(seq),int(control,16)
        if seq!=gl_sequence(fence-1) or control!=fence or (fence in fences and fences[fence]!=(seq,control)):raise RuntimeError("Invalid GL GPU completion token")
        fences[fence]=(seq,control)
    if not fences or set(fences)!=set(range(1,max(fences)+1)):raise RuntimeError("Missing or discontinuous GL GPU fences")
    return max(fences)


def gl_va_budget(text,pid,capacity,budget):
    declaration=re.search(rf"GENERAL open pid={pid} BO_limit={capacity} heap_bytes={budget}([^\n]*)",text)
    if not declaration:raise RuntimeError("Missing GPU physical/virtual budget declaration")
    tail=declaration[1]
    if "VA_bytes" not in tail:return budget # Historical shared budget.
    value=re.search(r"\bVA_bytes=(\d+)\b",tail)
    if not value:raise RuntimeError("Malformed GPU VA budget")
    span=int(value[1])
    if span!=budget and (budget,span) not in ((134217728,268435456),(201326592,268435456)):
        raise RuntimeError("Unqualified GPU virtual/physical budget pair")
    return span


def gl_generation_handles(text):
    declarations=re.findall(r"GENERAL open [^\n]*",text)
    values=[]
    for declaration in declarations:
        fields=re.findall(r"\bgeneration_handles=([^\s]+)",declaration)
        if 'generation_handles' in declaration and fields!=['1']:
            raise RuntimeError("Malformed GPU generation handle declaration")
        values.append(bool(fields))
    if values and any(value!=values[0] for value in values):
        raise RuntimeError("Conflicting GPU generation handle declarations")
    return bool(values and values[0])


def validate_gl_generation_handles(text,capacity,buffers,retired):
    """Bind each issued identity to one public generation, including reuse."""
    new=r"GENERAL gem_new handle=(\d+) bytes=(\d+) allocated=(\d+) flags=([0-9a-f]+) VA=([0-9a-f]+)"
    close=r"GENERAL bo_retired handle=(\d+) bytes=(\d+) backing_retained=0"
    seen={};previous={};active={};issued=0;closed=set()
    for event in re.finditer(f"(?P<new>{new})|(?P<close>{close})",text):
        kind='new' if event.group('new') else 'close'
        values=re.fullmatch(new if kind=='new' else close,event.group(0)).groups()
        handle=int(values[0]);key=(kind,handle)
        if key in seen:
            if seen[key]!=values:raise RuntimeError("Conflicting GPU generation event")
            continue
        seen[key]=values
        if not 0<handle<=0xffffffff:raise RuntimeError("Invalid GPU generation handle")
        slot=(handle-1)%capacity
        if kind=='new':
            expected=previous[slot]+capacity if slot in previous else slot+1
            if slot in active or handle!=expected:raise RuntimeError("GPU handle reused before retirement or generation mismatch")
            issued+=1
            logical,allocated,flags,va=int(values[1]),int(values[2]),int(values[3],16),int(values[4],16)
            if issued not in buffers or buffers[issued][:4]!=(va,logical,allocated,flags):
                raise RuntimeError("GPU generation does not match backing publication")
            previous[slot]=handle;active[slot]=(handle,issued,allocated)
        else:
            if slot not in active or active[slot][0]!=handle or active[slot][2]!=int(values[1]):
                raise RuntimeError("Stale GPU generation retirement")
            closed.add(active.pop(slot)[1])
    if issued!=len(buffers) or closed!=retired:
        raise RuntimeError("Incomplete GPU generation lifetime proof")


def validate_surface_lease_log(text):
    pattern=r'waffle-gl-surface-lease: passed=1 sid=(\d+) CPU_writer_refused_GPU_lease=1 AvoidSync_refused=1 reader_allowed=1 kernel_waiter_seen=1 writer_resumed=1 manual_no_GPU=1'
    markers=re.findall(pattern,text)
    if not markers or len(set(markers))!=1 or 'waffle-gl-surface-lease: passed=0' in text:
        raise RuntimeError('Native lease contention user proof missing')
    begin=re.search(r'SURFACE_LEASE_TEST op=1 handle=(\d+) active=1 waiting=0 manual_no_GPU=1',text)
    if not begin:raise RuntimeError('Native read lease acquisition missing')
    handle=begin[1]
    end=re.search(rf'SURFACE_LEASE_TEST op=2 handle={handle} active=0 waiting=0 manual_no_GPU=1',text[begin.end():])
    if not end:raise RuntimeError('Native read lease release missing')
    interval=text[begin.end():begin.end()+end.start()]
    if f'SURFACE_LEASE_TEST op=3 handle={handle} active=1 waiting=1 manual_no_GPU=1' not in interval:
        raise RuntimeError('Actual kernel CPU waiter not observed')
    if 'GENERAL_SUBMIT begin' in interval or 'GENERAL submitted' in interval:
        raise RuntimeError('GPU submission during manual lease')
    sid=markers[0]
    if not re.search(rf'waffle-surface-lock: seq=\d+ pid=1 sid={sid} unlock=0 options=2 seed=\d+ result=e00002cc',interval):
        raise RuntimeError('Actual AvoidSync refusal missing')


def validate_gl_bo_lifetimes(text,capacity,budget,va_budget=None):
    """Track unique publications/revocations across console replay duplicates."""
    if any(x in text for x in ('SURFACE_READ_', 'waffle-gl-surface-read:')):
        if any(x in text for x in ('SURFACE_WRITE_', 'waffle-gl-surface-write:','private_surface_write=1')):
            raise RuntimeError('Mixed surface read/write audits are not qualified')
        # Identical ownership/fence/pattern/restore evidence; preserve distinct
        # native/user operation names and reject mixed experiments above.
        text=text.replace('SURFACE_READ_', 'SURFACE_WRITE_').replace('waffle-gl-surface-read:', 'waffle-gl-surface-write:').replace('private_surface_read=1', 'private_surface_write=1')
    if 'SURFACE_LEASE_TEST' in text or 'waffle-gl-surface-lease:' in text:
        validate_surface_lease_log(text)
    dispatch_audit='waffle-gl-eagl-native-draw:' in text
    eagl_audit='waffle-gl-eagl-native-input:' in text
    if dispatch_audit and not eagl_audit:raise RuntimeError('EAGL draw dispatch lacks native input proof')
    reuse_audit='waffle-gl-surface-reuse:' in text
    if eagl_audit and not reuse_audit:raise RuntimeError('EAGL native input lacks native update/reuse proof')
    sample_audit='SURFACE_SAMPLE' in text or 'waffle-gl-surface-sample:' in text
    resource_audit='waffle-gl-surface-resource:' in text
    if reuse_audit and not sample_audit:raise RuntimeError('Native texture reuse lacks shader sampling proof')
    if sample_audit and not resource_audit:raise RuntimeError('Shader sampling lacks Mesa resource proof')
    import_audit='SURFACE_IMPORT' in text or 'waffle-gl-surface-import:' in text or resource_audit
    imported={};import_summary=None
    if import_audit:
        if any(x in text for x in ('SURFACE_WRITE_', 'SURFACE_MAP_TEST', 'waffle-gl-surface-map:')):
            raise RuntimeError('Mixed native import and memory-access audits')
        if resource_audit:
            if 'waffle-gl-surface-import:' in text:raise RuntimeError('Mixed native lifetime and Mesa resource audits')
            summaries=set(re.findall(r'waffle-gl-surface-resource: passed=1 sid=(\d+) textures=2 width=750 height=1624 deleted=2 GPU_memory_access='+('1' if sample_audit else '0'),text))
            created=set(re.findall(r'SURFACE_IMPORT created=1 sid=(\d+) handle=(\d+)',text))
            if len(summaries)!=1 or len(created)!=1:raise RuntimeError('Missing Mesa resource/native import proof')
            sid=int(next(iter(summaries)));native_sid,first=map(int,next(iter(created)))
            if sid!=native_sid:raise RuntimeError('Mesa resource imported a different surface')
            second=first;import_summary=(sid,first,second)
        else:
            summaries=set(re.findall(r'waffle-gl-surface-import: passed=1 sid=(\d+) first=(\d+) second=(\d+) duplicate_same=1 stale_refused=1 CPU_map_refused=1 closed=2 GPU_memory_access=0',text))
            if len(summaries)!=1:raise RuntimeError('Incomplete native import lifetime proof')
            import_summary=tuple(map(int,next(iter(summaries))))
            sid,first,second=import_summary
            if not sid or not first or second!=first+capacity:raise RuntimeError('Invalid imported handle generation')
        if any(x in text for x in ('waffle-gl-surface-import: passed=0','waffle-gl-surface-resource: passed=0','SURFACE_IMPORT cleanup_refused=1')):
            raise RuntimeError('Native import or Mesa resource audit failed')
        if set(re.findall(r'SURFACE_IMPORT reused=1 sid=(\d+) handle=(\d+)',text))!={(str(sid),str(first))}:
            raise RuntimeError('Missing duplicate native import reuse')
        for row in set(re.findall(r'SURFACE_IMPORT created=1 sid=(\d+) handle=(\d+) index=(\d+) VA=([0-9a-f]+) bytes=(\d+) lifetime_only=([01])',text)):
            surface,handle,index,va,size=int(row[0]),int(row[1]),int(row[2]),int(row[3],16),int(row[4])
            if index in imported or surface!=sid or int(row[5])!=(0 if sample_audit else 1):raise RuntimeError('Conflicting native import publication')
            imported[index]=(handle,va,size)
        if len(imported)!=(1 if resource_audit else 2) or {v[0] for v in imported.values()}!={first,second}:
            raise RuntimeError('Missing native import handle publications')
    if sample_audit:
        if 'waffle-gl-surface-sample: passed=0' in text:raise RuntimeError('Native shader sampling failed')
        sid,handle,_=import_summary
        if f'waffle-gl-surface-sample: passed=1 sid={sid} checked=256 wrong=0 GL_error=0 stage=7 GPU_readonly=1' not in text:
            raise RuntimeError('Missing complete native shader sampling proof')
        index=next(iter(imported));size=imported[index][2]
        if set(re.findall(r'SURFACE_SAMPLE imported=1 sid=(\d+) handle=(\d+) index=(\d+) GPU_readonly=1',text))!={(str(sid),str(handle),str(index))}:
            raise RuntimeError('Native sample mapping lacks readonly identity')
        sync=f'SURFACE_SAMPLE sync=1 handle={handle} bytes={size} GPU_readonly=1'
        if sync not in text:raise RuntimeError('Native sample source lacks CPU cache clean proof')
        cursor=text.index(sync)+len(sync)
        start=re.search(r'GENERAL_SUBMIT begin fence=(\d+) seq=(\d+)',text[cursor:])
        if not start or int(start[1])<3:raise RuntimeError('Native shader read lacks a later GPU command')
        completion=f'GENERAL_SUBMIT done fence={start[1]} seq={start[2]}'
        end=text.find(completion,cursor+start.end())
        if end<0 or end>text.index('waffle-gl-surface-sample: passed=1'):
            raise RuntimeError('Native shader result precedes GPU completion')
        samples={}
        for offset,values in re.findall(r'waffle-gl-surface-sample: pixels offset=(\d+) values=([0-9a-f/]+)',text):
            offset=int(offset);row=tuple(int(v,16) for v in values.split('/'))
            if len(row)!=8 or offset not in range(0,256,8) or (offset in samples and samples[offset]!=row):
                raise RuntimeError('Malformed/conflicting shader sample pixels')
            samples[offset]=row
        if len(samples)!=32:raise RuntimeError('Missing shader sample pixel rows')
        for y in range(16):
            for x in range(16):
                sx=(2*x+1)*750//32;sy=(2*y+1)*1624//32;gy=1623-sy
                inside=(2*sx+1)*3248>750*(2*gy+1) and (2*sx+1)*3248<4872000-750*(2*gy+1)
                expected=0xff0040ff if inside else 0xff000000
                at=y*16+x
                if samples[(at//8)*8][at%8]!=expected:raise RuntimeError('Incorrect native texture shader pixel')
    if reuse_audit:
        if 'waffle-gl-surface-reuse: result=1 phases=3 source_restored=1 same_native_GEM=1' not in text:
            raise RuntimeError('Native texture reuse failed or did not restore the source')
        phases=set(re.findall(r'waffle-gl-surface-reuse: phase=(\d+) passed=1 checked=256 wrong=0 GL_error=0 same_texture=1',text))
        if phases!={'1','2','3'} or re.search(r'waffle-gl-surface-reuse: (?:phase=\d+ passed=0|result=0)',text):
            raise RuntimeError('Native texture update phase missing or failed')
        reused={}
        for phase,offset,values in re.findall(r'waffle-gl-surface-reuse: phase=(\d+) offset=(\d+) values=([0-9a-f/]+)',text):
            key=(int(phase),int(offset));row=tuple(int(v,16) for v in values.split('/'))
            if key[0] not in (1,2,3) or key[1] not in range(0,256,8) or len(row)!=8 or (key in reused and reused[key]!=row):
                raise RuntimeError('Malformed/conflicting native texture reuse pixels')
            reused[key]=row
        if len(reused)!=96:raise RuntimeError('Native texture reuse pixels incomplete')
        for phase in (1,2,3):
            for offset in range(0,256,8):
                expected=(0xff00ff00,)*8 if phase==1 else (0xffff00ff,)*8 if phase==2 else samples[offset]
                if reused[(phase,offset)]!=expected:raise RuntimeError('Native texture reused stale or incorrect pixels')
        draw_fences=set()
        for sync in re.finditer(rf'SURFACE_SAMPLE sync=1 handle={handle} bytes={size} GPU_readonly=1',text):
            draw=re.search(r'GENERAL_SUBMIT begin fence=(\d+)',text[sync.end():])
            if draw and int(draw[1])>=3:draw_fences.add(int(draw[1]))
        if len(draw_fences)<4:raise RuntimeError('Native texture reuse lacks four cache-cleaned GPU draws')
    if eagl_audit:
        if f'waffle-gl-eagl-native-input: bound=2 sid={sid} selector_present=1 input_only=1' not in text:
            raise RuntimeError('Existing EAGL surface input selector proof missing')
        if "2 IOSurfaces were the textures' memory" not in text:
            raise RuntimeError('EAGL reports no pair of native surface inputs')
    if dispatch_audit and ('waffle-gl-eagl-native-draw: dispatched=1 shader_draw_readback=1' not in text or 'waffle-gl-eagl-native-draw: dispatched=0' in text):
        raise RuntimeError('Native texture sampler bypassed EAGL dispatch')
    publication=r"GENERAL_BO published index=(\d+) VA=([0-9a-f]+) bytes=(\d+) allocated=(\d+) flags=([0-9a-f]+) pages=(\d+)"
    surface_publication=r"SURFACE_BO published index=(\d+) VA=([0-9a-f]+) bytes=(\d+) cached=1 pages=(\d+)"
    reclaim=r"GENERAL_BO reclaimed index=(\d+) VA=([0-9a-f]+) bytes=(\d+) CPU_unmapped=(\d+) GPU_idle=(\d+) dual_ASID_TLBI=(\d+) used=(\d+)"
    release_pattern=r"GENERAL_BO released after GPU stop and context detach count=(\d+)(?: reclaimed_earlier=(\d+) total=(\d+))?(?=\r?$)"
    releases=list(re.finditer(release_pattern,text,re.M))
    if not releases:raise RuntimeError("Missing complete GL backing release")
    release=releases[0]
    if any(m.groups()!=release.groups() for m in releases):raise RuntimeError("Conflicting GL release counts")
    if va_budget is None:va_budget=budget
    object_limits=set(re.findall(r'object_max_bytes=([^\s]+)',text))
    object_max=10*1024*1024  # Prior qualified object bound, including E98.
    if object_limits:
        if (object_limits!={'201326592'} or capacity!=8192 or
            budget!=201326592 or va_budget!=268435456):
            raise RuntimeError("Unqualified GL object/heap/VA bound declaration")
        object_max=201326592
    generations=gl_generation_handles(text)
    write_audit='SURFACE_WRITE_TEST' in text or 'waffle-gl-surface-write:' in text or 'SURFACE_WRITE_COMMAND_BO' in text
    private_commands={}
    if write_audit:
        for row in re.findall(r'SURFACE_WRITE_COMMAND_BO index=(\d+) VA=([0-9a-f]+) bytes=(\d+) allocated=(\d+)',text):
            index=int(row[0]);value=(int(row[1],16),int(row[2]),int(row[3]))
            if index in private_commands and private_commands[index]!=value:raise RuntimeError('Conflicting private surface command')
            private_commands[index]=value
        if len(private_commands)!=1:raise RuntimeError('Missing unique private surface command')
        if ('waffle-gl-surface-write: passed=1 GPU_memory_access=1 restored=1' not in text or
            'SURFACE_WRITE_DATA values=57414646/4c454750/13579bdf/2468ace0 cached=1 GPU_memory_access=1' not in text):
            raise RuntimeError('Surface GPU write lacks independent value/restore proof')
        if any(x in text for x in ('SURFACE_WRITE_TEST passed=0','SURFACE_WRITE_TEST uncertain=1','SURFACE_WRITE_TEST command_revoke_failed=1','waffle-gl-surface-write: passed=0')):
            raise RuntimeError('Surface GPU write reported a failure')
    buffers={};active={};seen={};used=0;retired=0;retired_indices=set();surface_indices=set();append_end=0x100000000
    for event in re.finditer(f"(?P<publication>{publication})|(?P<surface>{surface_publication})|(?P<reclaim>{reclaim})",text):
        kind='surface' if event.group('surface') else 'publication' if event.group('publication') else 'reclaim'
        pattern=surface_publication if kind=='surface' else publication if kind=='publication' else reclaim
        values=re.fullmatch(pattern,event.group(0)).groups()
        index=int(values[0]);key=(kind,index)
        if key in seen:
            if seen[key]!=values:raise RuntimeError("Conflicting GL BO lifetime event")
            continue
        if event.start()>release.start():raise RuntimeError("New BO lifetime event after context detach")
        seen[key]=values
        if kind in ('publication','surface'):
            if kind=='surface':
                if ((not write_audit and not import_audit and 'waffle-gl-surface-map: passed=1 native_registry=1 mapped_then_revoked=1 GPU_memory_access=0' not in text) or
                    'waffle-gl-fullsize: width=750 height=1624 checked=1218000 wrong=0 filled=609000 padding_wrong=0 GL_error=0 hook_owned=1' not in text):
                    raise RuntimeError('Surface mapping lacks isolated audit and fullsize pixel proof')
                values=(values[0],values[1],values[2],values[2],'80002' if sample_audit else '80000',values[3])
                surface_indices.add(index)
            va,logical,allocated,flags,pages=int(values[1],16),int(values[2]),int(values[3]),int(values[4],16),int(values[5])
            if index!=len(buffers)+1 or index>0xffffffff or (index>capacity and not generations):raise RuntimeError("Missing GL BO publication")
            if len(active)>=capacity:raise RuntimeError("Live GL BO descriptor capacity exceeded")
            if (not 0<logical<=object_max or allocated!=((logical+16383)&~16383) or
                flags not in (((0x80002,) if sample_audit else (0x80000,)) if kind=='surface' else (0x20000,0x20002)) or pages!=allocated//4096 or va&16383 or
                va<0x100000000 or va+allocated>0x100000000+va_budget):
                raise RuntimeError("Invalid GL BO range/permission publication")
            if not retired and va!=append_end:raise RuntimeError("Unexpected GL VA reuse without revocation")
            if any(va<a[0]+a[2] and a[0]<va+allocated for a in active.values()):
                raise RuntimeError("Overlapping live GL BO ranges")
            used+=allocated
            if used>budget:raise RuntimeError("GL physical BO budget exceeded")
            buffers[index]=active[index]=(va,logical,allocated,flags,pages)
            append_end=va+allocated
        else:
            va,allocated=int(values[1],16),int(values[2])
            if index not in active or active[index][0]!=va or active[index][2]!=allocated:
                raise RuntimeError("GL BO revocation has no matching live publication")
            if tuple(map(int,values[3:6]))!=(1,1,1):raise RuntimeError("GL BO revocation lacks CPU/GPU/TLB proof")
            used-=allocated;active.pop(index);retired+=1;retired_indices.add(index)
            if int(values[6])!=used:raise RuntimeError("GL reclaim physical budget mismatch")
    if not buffers:raise RuntimeError("Missing GL BO publication")
    remaining=int(release[1]);earlier=int(release[2]) if release[2] else 0
    total=int(release[3]) if release[3] else remaining
    if remaining!=len(active) or earlier!=retired or total!=len(buffers) or remaining+earlier!=total:
        raise RuntimeError("GL BO backing release accounting mismatch")
    surface_audit_announced=any(marker in text for marker in ('SURFACE_MAP_TEST','SURFACE_BO published','waffle-gl-surface-map:','SURFACE_WRITE_TEST','waffle-gl-surface-write:','SURFACE_IMPORT','waffle-gl-surface-import:'))
    if surface_audit_announced!=bool(surface_indices):raise RuntimeError('Surface audit publication evidence missing')
    if any(marker in text for marker in ('SURFACE_MAP_TEST revoke_failed=1','SURFACE_MAP_TEST cleanup_refused=1','waffle-gl-surface-map: passed=0')):
        raise RuntimeError('Surface audit reported a failure')
    for index in surface_indices:
        if index not in retired_indices:raise RuntimeError('Surface audit backing was not revoked')
        va,logical,allocated,flags,pages=buffers[index]
        if import_audit:
            if index not in imported or imported[index][1:]!=(va,allocated):raise RuntimeError('Native import backing mismatch')
            handle=imported[index][0]
            if not re.search(rf'GENERAL bo_retired handle={handle} bytes={allocated} backing_retained=0',text):
                raise RuntimeError('Native imported handle not retired')
            completed=[str(import_summary[0])]
        elif write_audit:
            completed=re.findall(rf'SURFACE_WRITE_TEST passed=1 sid=(\d+) VA={va:x} bytes={allocated} fence=(\d+) checked=4 wrong=0 restored=1 retired=1',text)
            if len(set(completed))!=1:raise RuntimeError('Missing/conflicting GPU surface write completion')
            sid,fence=completed[0]
            if int(fence)<1 or f'GENERAL submitted fence={fence} private_surface_write=1' not in text:
                raise RuntimeError('Missing private surface fence accounting')
            completed=[sid]
        else:
            completed=re.findall(rf'SURFACE_MAP_TEST passed=1 sid=(\d+) VA={va:x} bytes={allocated} header_excluded=1 cached=1 retired=1 GPU_memory_access=0',text)
        if len(set(completed))!=1:raise RuntimeError('Missing/conflicting native surface audit completion')
        sid=completed[0]
        if not re.search(rf'waffle-gl-surface: sid={sid} bytes={allocated} stride=\d+ width=750 height=1624 format=42475241 metadata_expected=1',text):
            raise RuntimeError('Surface audit metadata differs from userspace')
    if import_audit and (set(imported)!=surface_indices or not generations):raise RuntimeError('Native imported publication/generation proof missing')
    if write_audit:
        if len(surface_indices)!=1:raise RuntimeError('Write audit requires exactly one surface')
        surface_index=next(iter(surface_indices))
        for index,value in private_commands.items():
            if (index!=surface_index+1 or index not in retired_indices or index not in buffers or
                buffers[index][:3]!=value or value[1:]!=(4096,16384) or buffers[index][3]!=0x20000):
                raise RuntimeError('Private surface command allocation/retirement differs')
    normal={};normal_retired=set()
    for index,bo in buffers.items():
        if (index in surface_indices and not import_audit) or index in private_commands:continue
        ordinal=len(normal)+1;normal[ordinal]=bo
        if index in retired_indices:normal_retired.add(ordinal)
    if generations:validate_gl_generation_handles(text,capacity,normal,normal_retired)
    return normal,release.group(0)


def validate_gl_queue_recycle_log(text,count):
    if 'waffle-gl-queue:' not in text:return
    done=re.search(r'waffle-gl-queue: result=1 cycles=100 queue=(\d+) stale=(\d+) stale_submit_refused=1',text)
    if (not done or 'waffle-gl-queue: result=0' in text or
        'waffle-gl-queue: begin cycles=100 existing_Mesa_context=1' not in text or
        not re.search(r'GENERAL open [^\n]*\bqueue_generations=1\b',text) or count<2):
        raise RuntimeError('Queue recycling proof incomplete')
    current,stale=map(int,done.groups())
    ids={int(value) for value in re.findall(r'GENERAL queue_new id=(\d+) priority=0 serialized=1',text)}
    if not 32<current<=0xffffffff or not 0<stale<current or len(ids)<100 or current not in ids or stale not in ids:
        raise RuntimeError('Missing queue generation creation proof')
    cursor=0
    for marker in (f'GENERAL request flags=10 fence=0 bos=1 roots=1 queue={stale}',
                   'GENERAL ioctl_refused op=46 error=22',
                   f'GENERAL request flags=10 fence=0 bos=1 roots=1 queue={current}'):
        position=text.find(marker,cursor)
        if position<0:raise RuntimeError('Stale queue refusal/new queue submission not proved')
        cursor=position+len(marker)


def validate_gl_log(text):
    if "Library not loaded:" in text:
        raise RuntimeError("GL process failed before main: "+re.search(r"Library not loaded: ([^\n]+)",text)[1])
    pixels=extract_gl_pixels(text);count=gl_completed_fences(text)
    validate_gl_queue_recycle_log(text,count)
    if 'waffle-gl-surface-sample:' in text and count<3:raise RuntimeError('Shader sampling lacks an additional GPU submission')
    capacity=re.search(r"GENERAL registered root_only=1 gated=1 BO_limit=(32|64|128|4096|8192)\b",text)
    if not capacity:raise RuntimeError("Missing bounded GL BO capacity")
    capacity=int(capacity[1])
    budget=re.search(rf"GENERAL open pid=1 BO_limit={capacity} heap_bytes=(33554432|67108864|134217728|201326592)\b",text)
    if not budget:raise RuntimeError("Missing bounded GL heap declaration")
    budget=int(budget[1])
    if capacity>=4096 and (capacity,budget) not in ((4096,67108864),(8192,134217728),(8192,201326592)):raise RuntimeError("Unqualified BO record capacity and physical heap pair")
    if "REBOOT REQUIRED" in text or "GENERAL_SUBMIT mismatch" in text:raise RuntimeError("GL GPU ownership or completion failed")
    markers=[f"GENERAL registered root_only=1 gated=1 BO_limit={capacity}",
       "waffle-gl-init: exec actual Darwin Mesa probe pid=1",
       "waffle-gl-user: begin actual_OSMesa=1 target=GPU triangle=16x16",
       "AOP_OWNER begin returned heap=1 power_live=1 mutex_held=0 channel_open=1",
       "full GPU owner returned live to init caller; no mutex held","SERVICE begin root_live=1 serialized=1",
       f"GENERAL open pid=1 BO_limit={capacity} heap_bytes={budget}"]
    cursor=0
    for marker in markers:
        at=text.find(marker,cursor)
        if at<0:raise RuntimeError("GL start/lifetime proof missing: "+marker)
        cursor=at+len(marker)
    if "waffle-gl-user: renderer=FD750" not in text:raise RuntimeError("Actual FD750 GL renderer not selected")
    for fence in range(1,count+1):
        starts=list(re.finditer(rf"GENERAL_SUBMIT begin fence={fence} seq={gl_sequence(fence-1)} root_words=(\d+) kernel_tail=15 extra_IB_depth=0",text[cursor:]))
        if not starts or not 1<=int(starts[0][1])<=1536:raise RuntimeError("GL root command publication not proved")
        cursor+=starts[0].end()
        for marker in (f"GENERAL_IB ACK matched seq{gl_sequence(fence-1)} value=00000000 valid=1",
          f"GENERAL_SUBMIT done fence={fence} seq={gl_sequence(fence-1)} control={fence:08x} checked=4096 wrong_words=0",
          f"GENERAL submitted fence={fence}"):
            at=text.find(marker,cursor)
            if at<0:raise RuntimeError("GL GPU fence not confirmed: "+marker)
            cursor=at+len(marker)
    buffers,release_marker=validate_gl_bo_lifetimes(text,capacity,budget,gl_va_budget(text,1,capacity,budget))
    if 'waffle-gl-recycle:' in text:
        begin='waffle-gl-recycle: begin cycles=9000 existing_Mesa_context=1'
        done=re.search(r'waffle-gl-recycle: result=1 cycles=9000 checked=4 wrong=0 fence=(\d+) existing_Mesa_context=1',text)
        if (begin not in text or not done or 'waffle-gl-recycle: result=0' in text or
            not gl_generation_handles(text) or len(buffers)<9000 or not 0<int(done[1])<count):
            raise RuntimeError('Recycled BO GPU writeback and later Mesa drawing not proved')
    markers=["waffle-gl-user: checked=256 wrong=0 filled=128 GL_error=0",
       release_marker,
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


def validate_ui_workload_log(text):
    """Require real backboardd GPU work and teardown, not triangle/pixel proof."""
    selected=re.search(r"waffle-ui-gpu: selected process=backboardd pid=(\d+) uid=501 bounded=1(?: stop_seconds=(\d+))?",text)
    if not selected or int(selected[1])<=1:raise RuntimeError("Actual mobile backboardd GPU selection missing")
    seconds=int(selected[2]) if selected[2] else 30
    if seconds not in (30,60,240,600):raise RuntimeError("Unsupported bounded UI observation window")
    pid=int(selected[1]);count=gl_completed_fences(text)
    capacity=re.search(r"GENERAL registered root_only=1 gated=1 BO_limit=(32|64|128|4096|8192)\b",text)
    if not capacity:raise RuntimeError("Missing bounded UI BO capacity")
    capacity=int(capacity[1])
    budget=re.search(rf"GENERAL open pid={pid} BO_limit={capacity} heap_bytes=(33554432|67108864|134217728|201326592)\b",text)
    if not budget:raise RuntimeError("Missing bounded UI heap declaration")
    budget=int(budget[1])
    if capacity>=4096 and (capacity,budget) not in ((4096,67108864),(8192,134217728),(8192,201326592)):raise RuntimeError("Unqualified BO record capacity and physical heap pair")
    for marker in (
        "waffle-ui-init: GPU device owner=501 mode=600 chown=0 chmod=0 RAM_only=1",
        f"GENERAL open pid={pid} BO_limit={capacity} heap_bytes={budget}",
        "FD750; shaders OpenGL ES GLSL ES",
        f"waffle-ui-gpu: bounded process stop pid={pid} seconds={seconds}",
        "SMMU_OWNER released after child stop and context detach",
        "CLOCK_OWNER released before CX restore result=1",
        "POWER_OWNER released after clock child, CX and CFG restore result=1",
        "AOP_OWNER released after power child and channel restore result=1",
        "SERVICE end consumed=1 result=1",
    ):
        if marker not in text:raise RuntimeError("UI workload proof missing: "+marker)
    for fence in range(1,count+1):
        if f"GENERAL_IB ACK matched seq{gl_sequence(fence-1)} value=00000000 valid=1" not in text:
            raise RuntimeError("UI workload GPU ACK missing")
    close=re.search(rf"GENERAL close passed=1 completed={count} buffers=(\d+) context_null=1",text)
    if not close or not 1<=int(close[1])<=(0xffffffff if gl_generation_handles(text) else capacity):raise RuntimeError("UI workload context teardown missing")
    buffers,_=validate_gl_bo_lifetimes(text,capacity,budget,gl_va_budget(text,pid,capacity,budget))
    if len(buffers)!=int(close[1]):raise RuntimeError("UI workload backing release count mismatch")
    if not re.search(r"redwood-gl: frame [1-9]\d*: \d+ GL calls, [1-9]\d* draws",text):
        raise RuntimeError("Actual CoreAnimation frame drawing missing")
    if not re.search(r"MiniIOMobileFramebuffer: swap \d+ layer 0: surface \d+ \(",text):
        raise RuntimeError("UI display-worker surface missing")
    if "REBOOT REQUIRED" in text or "A SHADER DOES NOT COMPILE" in text:
        raise RuntimeError("UI workload has GPU ownership or shader failure")
    return {"actual_backboardd_pid":pid,"GPU_fences":count,"BO_count":int(close[1]),
            "actual_CoreAnimation_workload":True,"full_GPU_teardown":True,
            "pixel_correctness_verified":False,"optical_visibility_verified":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60, choices=range(1, 661), metavar="1..660")
    parser.add_argument("--bootcpu", type=int, default=7, choices=range(1, 8))
    parser.add_argument("--cpus", type=int, choices=range(1, 8), help="XNU cores; one physical core remains with the resident USB loader")
    parser.add_argument("--capture-requests", type=Path, help="Read *.request screenshot requests; this runner alone owns fastboot")
    parser.add_argument("--torch-readonly", action="store_true", help="Waffle v7 SPMI flash module identification; no PMIC writes")
    parser.add_argument("--torch-pulse", action="store_true", help="Waffle qualified module: one two-second pulse and verified darkness")
    parser.add_argument("--torch-service",action="store_true",help="Expose the qualified flashlight driver to the iOS Control Center")
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
    parser.add_argument("--gpu-ui",action="store_true",help="E46 real backboardd workload; requires GL backend, no triangle/pixel success claim")
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
    parser.add_argument("--audio-preflight", action="store_true", help="Firmware-only ADSP validation; no DSP boot or amplifier writes")
    parser.add_argument("--audio-power", action="store_true", help="With --audio-preflight: bounded native RPMh upvotes retained until Android reset; no DSP boot")
    parser.add_argument("--audio-survey", action="store_true", help="With --audio-preflight: read-only native SMEM/SMP2P/GLINK state survey")
    parser.add_argument('--audio-iommu', action='store_true', help='Read-only native Apps SMMU/audio stream survey; no DSP or DMA writes')
    parser.add_argument("--audio-boot", action="store_true", help="With --audio-preflight: bounded native ADSP boot, GPR state query and shutdown; no PCM")
    parser.add_argument("--audio-graph", action="store_true", help="With --audio-boot: open/close two-module shared-memory graph, without DMA or PCM")
    parser.add_argument("--battery-readonly", action="store_true", help="With isolated --audio-boot: query seven native battery/USB properties once; no charger writes")
    parser.add_argument('--battery-report-test',action='store_true',help='With --battery-readonly: three bounded samples into the native power-source bridge')
    parser.add_argument("--system", type=Path, default=IMAGE_DIR / "system.packfs")
    parser.add_argument("--fastboot", default=os.environ.get("FASTBOOT"))
    parser.add_argument("--double-buffer", action="store_true", help="Compose offscreen and commit only complete frames to alternating scanout buffers")
    parser.add_argument("--display-flip-probe", action="store_true", help="Bounded reserved-framebuffer pattern flip and restoration")
    parser.add_argument("--display-flush-probe", action="store_true", help="Bounded unchanged-frame native CTL flush control probe")
    parser.add_argument("--display-survey", action="store_true", help="Read-only inherited Waffle DPU/TE survey")
    parser.add_argument("--surface-lock-audit",action="store_true",help="Trace bounded actual IOSurface framework lock/unlock traps; no locking behavior changes")
    parser.add_argument("--hardware-vsync", action="store_true", help="Opt-in hardware TE timestamps for native iOS VSync notifications")
    args = parser.parse_args()
    if args.double_buffer and (args.display_flip_probe or args.display_flush_probe or args.display_survey or args.audio_preflight or not args.gpu_ui or not args.gpu_gl_context):
        parser.error("--double-buffer requires isolated GPU UI and excludes other display/audio modes")
    if args.display_flip_probe and (args.display_flush_probe or args.hardware_vsync or args.display_survey or args.audio_preflight or not args.gpu_ui or not args.gpu_gl_context):
        parser.error("--display-flip-probe requires isolated GPU UI and excludes other display/audio modes")
    if args.display_flush_probe and (args.hardware_vsync or args.display_survey or args.audio_preflight or not args.gpu_ui or not args.gpu_gl_context):
        parser.error("--display-flush-probe requires isolated GPU UI and excludes other display/audio modes")
    if args.hardware_vsync and (args.display_survey or args.audio_preflight or not args.gpu_ui or not args.gpu_gl_context):
        parser.error("--hardware-vsync requires isolated GPU UI and excludes diagnostic/audio modes")
    if args.display_survey and (args.audio_preflight or not args.gpu_ui or not args.gpu_gl_context):
        parser.error("--display-survey requires isolated GPU UI and excludes audio")
    if args.audio_power and not args.audio_preflight:parser.error('--audio-power requires --audio-preflight')
    if args.audio_survey and (not args.audio_preflight or args.audio_power):parser.error('--audio-survey requires isolated --audio-preflight and excludes --audio-power')
    if args.audio_boot and (not args.audio_preflight or args.audio_power or args.audio_survey):parser.error('--audio-boot requires isolated --audio-preflight')
    if args.audio_graph and not args.audio_boot:parser.error('--audio-graph requires --audio-boot')
    if args.battery_readonly and (not args.audio_boot or args.audio_graph):parser.error('--battery-readonly requires isolated --audio-boot and excludes graph')
    if args.battery_report_test and not args.battery_readonly:parser.error('--battery-report-test requires --battery-readonly')
    if args.audio_iommu and (not args.audio_preflight or args.audio_power or args.audio_survey or args.audio_boot or args.audio_graph):parser.error('--audio-iommu requires isolated --audio-preflight')
    if args.audio_preflight and (args.gpu_probe is not None or args.cpus is not None or args.torch_readonly or args.torch_pulse or args.torch_service or args.seconds>60):
        parser.error('--audio-preflight requires an isolated test of at most60 seconds')
    if args.torch_readonly and args.gpu_probe is not None and not args.gpu_ui:parser.error('--torch-readonly requires a CPU or GPU UI workload')
    if args.torch_pulse and (args.torch_readonly or not args.gpu_gl_context):parser.error('--torch-pulse requires the controlled GPU GL workload and excludes read-only mode')
    if args.torch_service and (args.torch_pulse or args.torch_readonly or not args.gpu_ui):parser.error('--torch-service requires GPU UI and excludes torch probe modes')
    if args.gpu_ui and not args.gpu_gl_context:parser.error("--gpu-ui requires --gpu-gl-context")
    if args.seconds>300 and not (args.seconds==660 and args.gpu_ui and args.gpu_gl_context):parser.error("660 seconds is reserved for the bounded UI soak")
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
        # A lost read must not abort observation of a still-running kernel.
        # Retry only read operations, never boot/stage/run or another mutation.
        reads = items[:1] in (("getvar",),("get_staged",)) or items == ("oem","log")
        for attempt in range(6 if reads else 1):
            result = subprocess.run([fastboot, "-s", "xnuloader", *map(str, items)],
                                    capture_output=True, text=True, timeout=timeout)
            text = result.stdout + result.stderr
            with (out / "host.log").open("a") as log:
                log.write(" ".join(map(str, items)) + "\n" + text + "\n")
            if not result.returncode:
                return text
            if not reads or not any(s in text for s in ("usb_read failed","No such device","device disconnected")):
                break
            time.sleep(.5)
        raise RuntimeError(text)

    if "platform: waffle" not in command("getvar", "platform"):
        raise RuntimeError("Expected the waffle loader; select Boot iOS in the PJD110 UEFI menu")
    if "kernel-supported: software-userland-test" not in command("getvar", "kernel-supported"):
        raise RuntimeError("This loader only supports early checkpoints; boot the userland test image")
    if args.surface_lock_audit and (not args.gpu_gl_context or args.gpu_ui):parser.error("Surface lock audit requires isolated GL")
    arguments = f"bootcpu={args.bootcpu} loader_return_after={args.seconds} fbscale={args.fbscale} epoch={int(time.time())}"
    if args.surface_lock_audit:
        arguments += " waffle_surface_lock_audit=1"
    if args.hardware_vsync:
        arguments += " waffle_vsync=1"
    if args.double_buffer:
        arguments += " waffle_display_present=1"
    if args.display_flip_probe:
        arguments += " waffle_display_flip=1"
    if args.display_flush_probe:
        arguments += " waffle_display_flush=1"
    if args.display_survey:
        if args.audio_preflight:parser.error("--display-survey excludes audio tests")
        arguments += " waffle_vsync_audit=1"
    if args.audio_preflight:
        arguments += " adsp=8" if args.audio_iommu else " adsp=7" if args.audio_graph else " adsp=6" if args.audio_boot else " adsp=5" if args.audio_survey else " adsp=4" if args.audio_power else " adsp=3"
        if args.battery_readonly:arguments += " waffle_battery_readonly="+('2' if args.battery_report_test else '1')
    if args.cpus is not None:
        arguments += f" cpus={args.cpus}"
    if args.torch_readonly:
        arguments += " waffle_torch=1"
    if args.torch_pulse:
        arguments += " waffle_torch=2"
    if args.torch_service:
        arguments += " waffle_torch=3"
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
    ui_started=time.monotonic()
    ui_screenshots=set()
    ui_animation_seen=set()
    ui_animation_pending=[]
    ui_events=set()
    hud_pulses=set()
    slider_huds=set()
    sequence = 0
    while time.monotonic() < deadline:
        if args.capture_requests:
            for request in sorted(args.capture_requests.glob('*.request')):
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',request.stem):
                    continue
                if request.stem=='stop':
                    command('oem','stop')
                    request.rename(request.with_suffix('.done'))
                    continue
                screen=out/f'requested-{request.stem}.raw'
                command('oem','screenshot')
                command('get_staged',screen)
                request.rename(request.with_suffix('.done'))
                request.with_suffix('.json').write_text(json.dumps({'screenshot':str(screen),'bytes':screen.stat().st_size})+'\n')
        time.sleep(0.2 if args.capture_requests or args.gpu_ui else 0.05 if args.gpu_probe in (36,52,53,55,57,58,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94) else 5)
        response = command("getvar", "result")
        line = next((s for s in response.splitlines() if s.startswith("result: ")), "")
        sequence += 1
        command("oem", "log")
        log_path = out / f"kernel-{sequence}.log"
        command("get_staged", log_path)
        if args.capture_requests:
            for pulse in re.findall(r'waffle-hud: synthetic volume pulse=(\d+) ',log_path.read_text(errors='replace')):
                if pulse not in hud_pulses:
                    time.sleep(.3)
                    command('oem','screenshot')
                    command('get_staged',out/f'hud-pulse-{pulse}.raw')
                    hud_pulses.add(pulse)
        if args.gpu_ui:
            for position,change in re.findall(r"waffle-slider-control: position=(\d+) change=(\d+) muted=\d+ native_vibrate_when_silent=\d+ native_HUD=1",log_path.read_text(errors="replace")):
                key=(position,change)
                if key not in slider_huds:
                    slider_huds.add(key)
                    time.sleep(.15)
                    command("oem","screenshot")
                    command("get_staged",out/f"slider-hud-{position}-{change}.raw")
        if args.gpu_ui:
            for enabled,change in re.findall(r"waffle-slider-control: native_Focus_banner enabled=(\d+) sequence=(\d+)",log_path.read_text(errors="replace")):
                key=("focus",enabled,change)
                if key not in slider_huds:
                    slider_huds.add(key)
                    time.sleep(.15)
                    command("oem","screenshot")
                    command("get_staged",out/f"focus-banner-{enabled}-{change}.raw")
        if args.gpu_ui:
            # Capture settled output, not just a live scanout during motion.
            for pid,step,bundle in re.findall(r"waffle-ui-animation: pid=(\d+) step=(\d+) bundle=([A-Za-z0-9_.]+) accepted=1 state=returned",log_path.read_text(errors="replace")):
                key=(pid,step)
                if 1<=int(step)<=5 and key not in ui_animation_seen and len(ui_animation_seen)<5:
                    ui_animation_seen.add(key)
                    for delay in (2,4):
                        ui_animation_pending.append((time.monotonic()+delay,pid,step,delay,bundle))
            for capture in list(ui_animation_pending):
                due,pid,step,delay,bundle=capture
                if time.monotonic()>=due:
                    screen=out/f"animation-{pid}-{step}-{delay}s.raw"
                    command("oem","screenshot")
                    command("get_staged",screen)
                    screen.with_suffix('.json').write_text(json.dumps({'bundle':bundle,'launch_step':int(step),'delay_after_observed_return_seconds':delay,'capture_is_live_scanout':True})+'\n')
                    ui_animation_pending.remove(capture)
        if args.gpu_ui:
            # Preserve early evidence before the finite console log fills.
            with (out/"ui-gpu-events.log").open("a") as events:
                for event in log_path.read_text(errors="replace").splitlines():
                    if event not in ui_events and any(marker in event for marker in (
                        "waffle-surface:", "waffle-upload:", "waffle-snapshot:", "waffle-brightness:", "waffle-vsync:", "redwood-gl: f ", "redwood-gl: from gl.args:", "redwood-gl: glDraw", "waffle-slider", "waffle-sensor", "waffle-ui-", "GENERAL open", "GENERAL close", "GENERAL gem_new", "GENERAL bo_retired", "GENERAL allocation_refused",
                        "GENERAL bo_retired", "GENERAL_BO reclaimed", "GENERAL_BO reclaim_refused", "GENERAL request_completed", "GENERAL_SUBMIT", "A SHADER DOES NOT COMPILE",
                        "GENERAL ioctl_refused", "REBOOT REQUIRED", "an OpenGL ES", "redwood: signal")):
                        ui_events.add(event)
                        events.write(f"{log_path.name}: {event}\n")
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
                if args.gpu_ui:
                    proof=validate_ui_workload_log(final_text)
                    (out/"gpu-ui-workload.json").write_text(json.dumps(proof,indent=2)+"\n")
                else:
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
            if args.gpu_probe is not None and args.gpu_probe >= 65 and "native ACD-first HFI order active" not in final_text:
                raise RuntimeError(f"Native ACD-first HFI ordering not confirmed; logs: {out}")
            if args.gpu_probe is not None and args.gpu_probe >= 63:
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
                    f"PREPARE_SLUMBER ACK matched seq{gl_sequence(gl_completed_fences(final_text)) if image_kind==13 else 47 if (4<=image_kind<=8 or image_kind in (10,11,12)) else 45 if args.gpu_compute else 47 if args.gpu_session else 45 if args.gpu_writeback else 44 if args.gpu_zap else 43 if args.gpu_probe in (86,89,91,94) else 35} value=00000000 valid=1",
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
            if args.audio_preflight:
                if args.audio_iommu:
                    required=('waffle-audio-probe: PID1 ready', 'adsp: AUDIO_SMMU ids=',
                              'adsp: WAFFLE AUDIO_IOMMU OK: read-only Apps SMMU; no DSP, DMA, TLB or register writes')
                    forbidden=('adsp: PAS ', 'adsp: RPMh ', 'adsp: POWER_APPLY ', 'adsp: FAIL', 'AUDIO_IOMMU FAIL')
                    if not all(x in final_text for x in required) or any(x in final_text for x in forbidden):
                        raise RuntimeError(f'Audio IOMMU read-only survey failed; logs: {out}')
                    print('Read-only Apps SMMU snapshot captured; DMA ownership unqualified',flush=True)
                    return
                if args.audio_boot:
                    markers=('adsp: PAS 36 authenticated and running', 'adsp: PAS 1 authenticated and running',
                             'adsp: SMP2P ready seen', 'adsp: SMP2P handover seen',
                             'adsp: STAGE1 OK PAS=36,1 SMP2P=ready+handover GLINK=up QRTR',
                             'GPR SPF=1 mode='+('7' if args.audio_graph else '6'), 'adsp: PAS 1 shutdown=OK', 'adsp: PAS 36 shutdown=OK',
                             'adsp: WAFFLE DSP_BOOT result=1 stop_clean=1')
                    if not all(m in final_text for m in markers) or 'adsp: FAIL' in final_text:
                        raise RuntimeError(f'Native ADSP boot/GPR/shutdown not confirmed; logs: {out}')
                    if args.audio_graph and 'adsp: APM_GRAPH lifecycle=1 modules=write_shmem/read_shmem connection=1 no_DMA=1 no_PCM=1 amps_off=1' not in final_text:
                        raise RuntimeError(f'Native APM graph open/close not confirmed; logs: {out}')
                    battery_marker='adsp: BATTERY_READONLY passed=1 properties=7 setters=0 oneshot='+('0' if args.battery_report_test else '1')
                    if args.battery_readonly and (battery_marker not in final_text or 'adsp: BATTERY_READONLY FAIL' in final_text):
                        raise RuntimeError(f'Read-only battery request/response not confirmed; logs: {out}')
                    if args.battery_report_test and not all(marker in final_text for marker in (
                            'adsp: BATTERY_REPORT passed=1 samples=3 period_ms=10000 bounded=1 setters=0',
                            'waffle-battery-pid1: updates=3', 'RedwoodBattery: the battery\'s power source is up:',
                            'waffle-battery-bridge: current=')):
                        raise RuntimeError(f'Native periodic battery bridge not confirmed; logs: {out}')
                    if args.battery_report_test:
                        native=re.findall(r'BATTERY_READONLY sample soc_hundredths=(\d+)',final_text)
                        bridge=re.findall(r'waffle-battery-bridge: current=(\d+) max=(\d+) installed=(\d+)',final_text)
                        users=re.findall(r'waffle-battery-pid1: updates=(\d+) soc=(-?\d+)',final_text)
                        expected=(int(native[-1])+50)//100 if native else -1
                        if not bridge or not users or tuple(map(int,bridge[-1]))!=(expected,100,1) or int(users[-1][0])<3 or int(users[-1][1])!=expected:
                            raise RuntimeError(f'Native battery percent disagrees with IOPMPowerSource or PID1 sysctl; logs: {out}')
                    print('Native ADSP boot, GPR SPF state and shutdown validated; no PCM playback',flush=True)
                    return
                required = ('waffle-audio-probe: PID1 ready',
                            'adsp: MDT adsp_dtb phdrs=3', 'adsp: MDT adsp phdrs=57',
                            'adsp: WAFFLE POWER_PLAN OK: rails384 BCMs8 native_VCD_order=1',
                            *(['adsp: WAFFLE INPUT_CHECK OK', 'adsp: POWER_APPLY BCM result=1 wait_mask=0xf5',
                               'adsp: POWER_APPLY ARC result=1 indices=7/4/3',
                               'adsp: WAFFLE POWER_APPLY OK: TCS buffers restored=1; votes retained; DSP and amplifiers off'] if args.audio_power else
                              ['adsp: WAFFLE DSP_SURVEY OK: SMEM and IPCC read only; no DSP reset, PAS or power writes'] if args.audio_survey else
                              ['adsp: WAFFLE PREFLIGHT OK: firmware only; no PAS, mailbox, RPMh, IPCC or amplifier writes']))
                if not all(s in final_text for s in required) or any(s in final_text for s in ('adsp: FAIL', 'adsp: WAFFLE PREFLIGHT FAIL', 'adsp: WAFFLE POWER_APPLY FAIL', 'adsp: PAS ', 'adsp: RPMh ')):
                    raise RuntimeError(f'ADSP firmware preflight evidence missing or hardware path reached; logs: {out}')
            if args.torch_readonly and not all(s in final_text for s in (
                    'torch: platform=waffle-v7', 'the module says type 0x18, subtype 0x7',
                    'torch: waffle read-only module=', 'no PMIC writes')):
                raise RuntimeError(f"Waffle torch identification failed; logs: {out}")
            if args.torch_pulse and not all(s in final_text for s in (
                    'torch: platform=waffle-v7', 'the module says type 0x18, subtype 0x7',
                    'the light ON at 100 mA per channel', 'off again after 2 s', '(dark)')):
                raise RuntimeError(f"Waffle torch pulse or shutdown proof failed; logs: {out}")
            if args.torch_service and not all(s in final_text for s in (
                    "torch: THE LIGHT IS IOS'S (/dev/redwood-torch)",
                    "at the run's end the module reads: enable 0000, channels 0000")):
                raise RuntimeError(f"Waffle torch service or dark shutdown proof failed; logs: {out}")
            if args.cpus is not None and args.cpus>1:
                counts=[int(n) for n in re.findall(r"GenericARMPE: (\d+) of \d+ processors are running",final_text)]
                counts += [int(n) for n in re.findall(r"GenericARMPE: the slower cores started too: (\d+) processors running",final_text)]
                active=[int(n) for n in re.findall(r"cpu_test: hw.ncpu \d+, hw.activecpu (\d+)",final_text)]
                parallel=[float(n) for n in re.findall(r"(\d+\.\d+) processors at work, seen on",final_text)]
                failures=any(s in final_text for s in ('was not started:','has not joined:','took an exception on its way in','did not stop: it is left running','THE KERNEL LEFT CORE'))
                proof={'requested_cpus':args.cpus,'running_counts':counts,'active_cpus':active,'parallel_CPU_time_per_wall_time':parallel,'startup_or_stop_failure':failures,'GPU_requested':bool(args.gpu_probe),'passed':not failures and bool(counts) and max(counts)==args.cpus and bool(active) and max(active)==args.cpus and bool(parallel) and max(parallel)>1.0}
                (out/'cpu-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
                if not proof['passed']:
                    raise RuntimeError(f"Multicore proof failed; logs: {out}")
            if args.gpu_image and args.gpu_compute==2:
                if args.gpu_ui:
                    print("Actual UI GPU workload and teardown validated; pixel correctness unverified",flush=True)
                    return
                if image_pixels is None:raise RuntimeError("No GPU pixels validated")
                write_gpu_png(out/"first-gpu-frame.png",image_pixels)
                (out/"gpu-pixels.json").write_text(json.dumps({'width':16,'height':16,'rgba_words':image_pixels,'source':'actual kernel GPU readback'},indent=2)+"\n")
                print(f"GPU image: {out/'first-gpu-frame.png'}",flush=True)
            return
        if args.gpu_ui:
            for seconds in (15,30,32,35,40,45,60,120,180,230,300,450,590):
                if seconds not in ui_screenshots and time.monotonic()-ui_started>=seconds:
                    command("oem", "screenshot")
                    command("get_staged", out / f"ui-screen-{seconds}.raw")
                    ui_screenshots.add(seconds)
        elif not args.gpu_probe and (sequence in (2, 6, 9, 11) or (args.seconds > 60 and sequence % 6 == 0)):
            command("oem", "screenshot")
            command("get_staged", out / f"screen-{sequence}.raw")
    raise RuntimeError(f"No final result yet; logs: {out}. No automatic reboot was requested.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        sys.exit(f"waffle-run: {error}")
