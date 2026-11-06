"""Recover one run's stream using exact byte overlaps of immutable snapshots."""
from pathlib import Path
import hashlib

def merge_run_logs(directory):
    directory=Path(directory)
    logs=sorted((p for p in directory.glob('kernel-*.log') if p.stem.removeprefix('kernel-').isdigit()),key=lambda p:int(p.stem.removeprefix('kernel-')))
    final=directory/'kernel-final.log'
    if not final.is_file():raise ValueError('Final kernel snapshot missing')
    logs.append(final)
    stream=b'';previous=b'';identity=None;records=[]
    for path in logs:
        data=path.read_bytes()
        if len(data)<256:raise ValueError('Short/empty kernel snapshot: '+path.name)
        if identity is None:identity=data[:256]
        elif data[:256]!=identity:raise ValueError('Different run/payload header: '+path.name)
        overlap=0
        if not previous:extra=data
        elif data.startswith(previous):extra=data[len(previous):];overlap=len(previous)
        else:
            # Repeated service errors can duplicate a 4-KB suffix. Require a
            # unique *longer exact* suffix rather than choosing an occurrence.
            at=-1;size=4096
            while size<=min(len(previous),65536):
                seed=previous[-size:]
                candidate=data.rfind(seed)
                if candidate<0:break
                if data.find(seed)==candidate:
                    at=candidate;break
                size*=2
            if at<0:
                raise ValueError('Missing/ambiguous exact snapshot overlap: '+path.name)
            extra=data[at+size:];overlap=size
        stream+=extra;previous=data
        records.append({'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),'overlap_bytes':overlap,'appended_bytes':len(extra)})
    return stream,{'bytes':len(stream),'sha256':hashlib.sha256(stream).hexdigest(),'minimum_nonprefix_overlap_bytes':4096,'snapshots':records}
