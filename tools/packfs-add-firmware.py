#!/usr/bin/env python3
"""Append a raw /fw tree to a private packfs copy, preserving original extents."""
import argparse
from collections import deque
import hashlib
import json
import mmap
import os
from pathlib import Path
import stat
import subprocess
import tempfile

import mkpackfs as pf


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def inspect(image):
    """Validate ranges and tree before using untrusted metadata as offsets."""
    if len(image) < pf.SUPER_SIZE:
        raise ValueError('short superblock')
    s = list(pf.SUPER.unpack_from(image))
    magic, block, count, no, so, ss, data, size, _ = s
    def bounds(at, length, limit=size):
        if at < 0 or length < 0 or at > limit or length > limit-at:
            raise ValueError('out-of-range extent')
    if magic != pf.MAGIC or block < 4096 or block & (block-1) or not 0 < count <= 4*1024*1024:
        raise ValueError('invalid packfs header')
    if size != len(image) or no % 4096 or so % 4096 or not 0 < ss <= 256*1024*1024 or data > size:
        raise ValueError('invalid metadata layout')
    bounds(no, count*pf.DNODE.size); bounds(so, ss)
    strings = bytes(image[so:so+ss])
    nodes = [list(pf.DNODE.unpack_from(image, no+i*pf.DNODE.size)) for i in range(count)]
    names = []
    for i, n in enumerate(nodes):
        mode, _, _, _, length, at, parent, name, nl, _, _, flags = n
        bounds(name, nl+1, ss)
        if nl > 255 or strings[name+nl] or parent >= count or not stat.S_ISDIR(nodes[parent][0]):
            raise ValueError('invalid name or parent')
        nm = strings[name:name+nl]
        if i and (not nm or b'/' in nm or b'\0' in nm or nm in (b'.', b'..')):
            raise ValueError('invalid filename')
        names.append(nm)
        if stat.S_ISDIR(mode):
            bounds(at, length, count)
        elif stat.S_ISLNK(mode):
            if not 0 < length < 1024:
                raise ValueError('invalid symlink')
            bounds(at, length, ss)
        elif stat.S_ISREG(mode):
            if flags & ~3 or flags == pf.F_ZSTD:
                raise ValueError('unknown regular-file flags')
            if not length:
                continue
            if at < data or at % (8 if flags & pf.F_CHUNKED else block):
                raise ValueError('invalid file alignment')
            if flags & pf.F_CHUNKED:
                chunks = (length+pf.CHUNK-1)//pf.CHUNK
                previous = (chunks+1)*4
                bounds(at, previous)
                for c in range(chunks+1):
                    offset = int.from_bytes(image[at+c*4:at+c*4+4], 'little')
                    if offset < previous or (c == 0 and offset != previous) or (c and offset-previous > pf.CHUNK):
                        raise ValueError('invalid chunk table')
                    bounds(at, offset)
                    previous = offset
            else:
                bounds(at, length)
        else:
            raise ValueError('unsupported inode type')
    if not stat.S_ISDIR(nodes[0][0]) or nodes[0][6] != 0:
        raise ValueError('invalid root')
    paths = {b'': 0}; visited = {0}; queue = deque([b''])
    while queue:
        path = queue.popleft(); index = paths[path]; n = nodes[index]
        if not stat.S_ISDIR(n[0]):
            continue
        last = None
        for child in range(n[5], n[5]+n[4]):
            name = names[child]
            if child in visited or nodes[child][6] != index or (last is not None and name <= last):
                raise ValueError('cyclic, duplicate or unsorted directory')
            last = name; visited.add(child)
            cp = path+b'/'+name; paths[cp] = child; queue.append(cp)
    if len(visited) != count:
        raise ValueError('unreachable nodes')
    return s, nodes, strings, paths


def graft(source, firmware, output, files=None):
    source, firmware, output = map(Path, (source, firmware, output))
    if output.exists():
        raise ValueError('output already exists; refusing overwrite')
    selected = sorted(files if files is not None else [p.name for p in firmware.iterdir()])
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('empty or duplicate firmware selection')
    blobs = {}
    for name in selected:
        p = firmware/name
        if Path(name).name != name or name in ('.', '..') or not p.is_file() or p.is_symlink() or len(os.fsencode(name)) > 255:
            raise ValueError('firmware must be flat regular files')
        blobs[os.fsencode(name)] = p.read_bytes()
    with source.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as image:
        s, old, strings, paths = inspect(image)
        if b'/fw' in paths:
            raise ValueError('source already contains /fw')
        root_children = [old[i] for i in range(old[0][5], old[0][5]+old[0][4])]
        # Keep original string offsets, including every symlink target.
        strings = bytearray(strings)
        fw_name = len(strings); strings += b'fw\0'
        fw = [stat.S_IFDIR | 0o755, 0, 0, 2, len(blobs), 0, 0, fw_name, 2, 0, s[8], 0]
        children = {id(n): [old[c] for c in range(n[5], n[5]+n[4])] for n in old if stat.S_ISDIR(n[0])}
        children[id(old[0])] = root_children+[fw]
        new_files = []
        for name, payload in blobs.items():
            name_off = len(strings); strings += name+b'\0'
            n = [stat.S_IFREG | 0o644, 0, 0, 1, len(payload), 0, 0, name_off, len(name), 0, s[8], 0]
            new_files.append((n, payload))
        children[id(fw)] = [n for n, _ in new_files]
        original = {id(n): list(n) for n in old}
        old[0][3] += 1
        nodes = [old[0]]; queue = deque([old[0]])
        while queue:
            n = queue.popleft()
            entries = sorted(children[id(n)], key=lambda c: strings[c[7]:c[7]+c[8]])
            n[5] = len(nodes) if entries else 0; n[4] = len(entries)
            # Index assigned before a directory reaches the queue.
            for child in entries:
                nodes.append(child)
                if stat.S_ISDIR(child[0]): queue.append(child)
        indices = {id(n): i for i, n in enumerate(nodes)}
        for parent in nodes:
            if stat.S_ISDIR(parent[0]):
                for child in children[id(parent)]: child[6] = indices[id(parent)]
        s[2] = len(nodes); s[3] = pf.align(len(image), 4096)
        s[4] = pf.align(s[3]+len(nodes)*pf.DNODE.size, 4096); s[5] = len(strings)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=output.name+'.', dir=output.parent); os.close(fd)
        try:
            subprocess.run(['cp', '--reflink=auto', '--', str(source), temp], check=True)
            with open(temp, 'r+b') as out:
                out.seek(s[4]); out.write(strings)
                for n, payload in new_files:
                    out.seek(pf.align(out.tell(), s[1])); n[5] = out.tell(); out.write(payload)
                s[7] = pf.align(out.tell(), s[1]); out.truncate(s[7])
                out.seek(s[3])
                for n in nodes: out.write(pf.DNODE.pack(*n))
                out.seek(0); out.write(pf.SUPER.pack(*s)); out.flush(); os.fsync(out.fileno())
            with open(temp, 'rb') as check, mmap.mmap(check.fileno(), 0, access=mmap.ACCESS_READ) as result:
                _, verified, _, vp = inspect(result)
                # Entire original image except header remains byte-identical.
                for at in range(pf.SUPER.size, len(image), 8 << 20):
                    end = min(at+(8 << 20), len(image))
                    if image[at:end] != result[at:end]: raise ValueError('original extent changed')
                for path, index in paths.items():
                    before = original[id(old[index])]; after = verified[vp[path]]
                    keep = [0, 1, 2, 9, 10, 11]
                    if not stat.S_ISDIR(before[0]): keep += [3, 4, 5, 7, 8]
                    if any(before[k] != after[k] for k in keep): raise ValueError('original metadata changed')
                for name, payload in blobs.items():
                    n = verified[vp[b'/fw/'+name]]
                    if result[n[5]:n[5]+n[4]] != payload or n[11]: raise ValueError('firmware verification failed')
            # Hard-link publication refuses a concurrent output creator.
            os.link(temp, output)
        finally:
            os.unlink(temp)
    return {'source': str(source), 'source_sha256': digest(source), 'output': str(output),
            'output_sha256': digest(output), 'original_extents_preserved': True,
            'firmware': {os.fsdecode(k): {'size': len(v), 'sha256': hashlib.sha256(v).hexdigest()} for k,v in blobs.items()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--file', action='append', dest='files')
    args = p.parse_args()
    result = graft(args.source, args.firmware, args.output, args.files)
    report = args.output.with_suffix(args.output.suffix+'.json')
    with report.open('x') as f: json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
