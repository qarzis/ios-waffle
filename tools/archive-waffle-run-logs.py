#!/usr/bin/env python3
"""Pack completed rolling log snapshots, verifying every byte before removal."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def archive(run):
    run = run.resolve()
    if not (run/'kernel-final.log').is_file() or not (run/'result.txt').is_file():
        raise ValueError('A final kernel log and result are required; active runs are not archived')
    files = sorted(run.glob('kernel-[0-9]*.log'))
    if not files:
        return
    target = run/'rolling-kernel-logs.tar.zst'
    temporary = target.with_suffix('.zst.tmp')
    if target.exists() or temporary.exists():
        raise ValueError('Archive already exists; refusing to overwrite evidence')
    records = {}
    for path in files:
        if path.is_symlink():
            raise ValueError('Snapshot symlinks are not archived')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        stat = path.stat()
        records[path.name] = dict(sha256=digest, bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
    process = subprocess.Popen(['zstd', '-3', '-T2', '-q', '-o', str(temporary)], stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdin, mode='w|', dereference=True) as output:
            for path in files:
                output.add(path, arcname=path.name, recursive=False)
        process.stdin.close()
        if process.wait():
            raise RuntimeError('Compression failed; original snapshots retained')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    process = subprocess.Popen(['zstd', '-q', '-d', '-c', str(temporary)], stdout=subprocess.PIPE)
    seen = set()
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as source:
            for member in source:
                if member.name not in records or member.name in seen or not member.isfile():
                    raise ValueError('Unexpected archive member; original snapshots retained')
                with source.extractfile(member) as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != records[member.name]['sha256']:
                    raise ValueError('Archive verification failed; original snapshots retained')
                seen.add(member.name)
        process.stdout.close()
        if process.wait() or seen != set(records):
            raise ValueError('Incomplete archive; original snapshots retained')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    for path in files:
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (records[path.name]['bytes'], records[path.name]['mtime_ns']):
            raise ValueError('Snapshots changed during archival; originals retained')
    temporary.rename(target)
    (run/'rolling-kernel-logs.index.json').write_text(json.dumps(records, indent=2)+'\n')
    for path in files:
        path.unlink()
    print(json.dumps(dict(run=str(run), verified_snapshots=len(files),
                          original_bytes=sum(r['bytes'] for r in records.values()),
                          archive_bytes=target.stat().st_size, final_log_retained=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, nargs='+')
    for run in parser.parse_args().run:
        archive(run)
