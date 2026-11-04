#!/usr/bin/env python3
"""Generate typed probe calls using the existing iOS16.5 EAGL slot catalog."""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--extra-source",type=Path,action="append",default=[])
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sources=[root / "userland/src/waffle_gl_probe.c",*args.extra_source]
names = sorted(set(name for source in sources for name in re.findall(r"\b(gl[A-Z]\w*)\s*\(",source.read_text())))
slots = {}
for line in (root / "userland/src/eagl_slots.txt").read_text().splitlines():
    fields = line.split("#")[0].split()
    if fields:
        for name in fields[2:]:
            slots[name] = int(fields[0], 16)
commands = {}
for command in ET.parse(root / "xnu-deps/build/mesa/out-26.3.0-rc1/gl.xml").getroot().iter("command"):
    proto = command.find("proto")
    if proto is not None:
        commands[proto.find("name").text] = command
out = ["/* Generated from existing eagl_slots.txt and pinned Mesa gl.xml. */", "static void **waffle_hook_table;"]
for name in names:
    command = commands[name]
    proto = "".join(command.find("proto").itertext())
    returns = proto[:proto.rindex(name)].strip()
    declarations, types, values = [], [], []
    for param in command.findall("param"):
        text = "".join(param.itertext()).strip()
        value = param.find("name").text
        declarations.append(text)
        types.append(text[:text.rindex(value)].strip())
        values.append(value)
    offset = slots[name]
    assert offset % 8 == 0 and offset > 0
    call_types = ", ".join(["void *", *types])
    call_values = ", ".join(["waffle_hook_table[0]", *values])
    body = f"(({returns} (*)({call_types}))waffle_hook_table[{offset // 8}])({call_values})"
    out.append(f"static {returns} waffle_hook_{name}({', '.join(declarations) or 'void'}) {{ {'return ' if returns != 'void' else ''}{body}; }}")
    out.append(f"#define {name} waffle_hook_{name}")
args.output.write_text("\n".join(out) + "\n")
