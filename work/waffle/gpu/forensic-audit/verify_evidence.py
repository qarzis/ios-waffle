#!/usr/bin/env python3
"""Read-only audit of saved evidence. Never talks to a device or builds a kernel."""
import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def main():
    frozen = json.loads((OUT / "code-freeze.json").read_text())
    changed = [name for name, record in frozen["files"].items()
               if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != record["sha256"]]
    save("freeze-verification.json", {"checked_files": len(frozen["files"]),
                                      "changed_files": changed})
    run = ROOT / "work/waffle/runs/20261031T074659Z"
    logs = sorted(run.glob("kernel-*.log"))
    checkpoints, acknowledgements, faults = {}, set(), set()
    for path in logs:
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if "RAW checkpoint " in line:
                checkpoints.setdefault(line, {"file": str(path.relative_to(ROOT)), "line": number})
            if re.search(r"(?:CP_INIT_RAW|CP_THREAD_RAW) ACK matched", line):
                acknowledgements.add(line)
            if re.search(r"(?:fault FAR=|reported firmware fault during RAW|RAW.*FSR)", line):
                faults.add(line)
    port_log = run / "kernel-88.log"
    text = port_log.read_text(errors="replace")
    packet_map = {int(i): int(v, 16) for i, v in
                  re.findall(r"PRE_RAW packet\[(\d+)\]=([0-9a-f]+)", text)}
    assert sorted(packet_map) == list(range(11)), "Incomplete saved port packet"
    port = [packet_map[i] for i in range(11)]
    save("test94-boundary.json", {
        "kernel_log_files_scanned": len(logs), "checkpoints": checkpoints,
        "saved_raw_acknowledgements": sorted(acknowledgements),
        "saved_fault_lines_matching_search": sorted(faults),
        "limitation": "Missing logs do not establish nonexecution, nor absence of faults.",
        "port_packet": [f"{v:08x}" for v in port]})

    # Independent captured native packets, not a second copy of port constants.
    # Normalize only session sequence and the separately allocated restore VA.
    comparisons = []
    for path in sorted((ROOT / "work/waffle/gpu").glob("android-live-audit*/*.trace")):
        with path.open(errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                if not re.search(r"\bhfi:.*?bytes=44 id=131\b", line):
                    continue
                fields = {int(i): int(v, 16) for i, v in
                          re.findall(r"\bw(\d+)=0x([0-9a-fA-F]+)", line.split("pwrup0=")[0])}
                if sorted(fields) != list(range(11)):
                    continue
                native = [fields[i] for i in range(11)]
                a, b = port.copy(), native.copy()
                a[0] &= 0xfffff
                b[0] &= 0xfffff
                a[8:10] = b[8:10] = [0, 0]
                comparisons.append({"file": str(path.relative_to(ROOT)), "line": number,
                    "native_packet": [f"{v:08x}" for v in native],
                    "mismatched_word_indices_after_normalization":
                        [i for i in range(11) if a[i] != b[i]]})
    assert comparisons, "No independent native CP_INIT records"
    save("raw-packet-comparison.json", {
        "normalizations": ["header sequence bits 31:20", "restore GPU VA words 8 and 9"],
        "records": comparisons,
        "limitation": "Does not validate mapped restore contents, DMA, timing or hardware state."})

    # Compare exactly the source snapshots associated with the two build directories.
    old = ROOT / "work/waffle/diagnostic-gpu-native93/source"
    new = ROOT / "work/waffle/diagnostic-gpu-native94/source"
    differences, diff_text = [], []
    for path in sorted(new.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(new)
        prior = old / relative
        if not prior.exists():
            differences.append({"file": str(relative), "status": "only_in_94_snapshot"})
        elif prior.read_bytes() != path.read_bytes():
            differences.append({"file": str(relative), "status": "changed"})
            try:
                diff_text.extend(difflib.unified_diff(
                    prior.read_text().splitlines(True), path.read_text().splitlines(True),
                    fromfile="93/" + str(relative), tofile="94/" + str(relative)))
            except UnicodeDecodeError:
                pass
    assert old.is_dir() and new.is_dir(), "Build source snapshots missing"
    save("source93-vs94.json", {"differences": differences,
         "limitation": "Source differences alone do not prove complete equivalence of run state."})
    (OUT / "source93-vs94.diff").write_text("".join(diff_text))
    print(json.dumps({"frozen_sources_changed": changed,
        "test94_logs_scanned": len(logs), "unique_checkpoints": len(checkpoints),
        "native_cp_init_records": len(comparisons),
        "packet_mismatches": sum(bool(x["mismatched_word_indices_after_normalization"])
                                 for x in comparisons),
        "source_snapshot_differences": len(differences)}, indent=2))
    assert not changed, "Production source changed during audit"


if __name__ == "__main__":
    main()
