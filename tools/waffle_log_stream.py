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
            seed=previous[-4096:]
            at=data.rfind(seed)
            if len(seed)!=4096 or at<0 or data.find(seed)!=at:
                raise ValueError('Missing/ambiguous exact snapshot overlap: '+path.name)
            extra=data[at+4096:];overlap=4096
        stream+=extra;previous=data
        records.append({'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),'overlap_bytes':overlap,'appended_bytes':len(extra)})
    return stream,{'bytes':len(stream),'sha256':hashlib.sha256(stream).hexdigest(),'minimum_nonprefix_overlap_bytes':4096,'snapshots':records}
