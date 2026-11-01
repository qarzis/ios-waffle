"""FD750 assembly determinism, ISA decode/reassemble and malformed input handling."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tool', type=Path, default=root / 'work/waffle/gpu/forensic-audit/compute-tools/waffle-ir3-assemble')
args = parser.parse_args()
tool = args.tool.resolve()
shader = root / 'tools/tests/fixtures/waffle-invocation-8.asm'
with tempfile.TemporaryDirectory() as directory:
    out = Path(directory)

    def assemble(source, stem):
        binary, metadata, disasm = [out / (stem + ext) for ext in ('.bin', '.json', '.disasm')]
        subprocess.run([str(tool), str(source), str(binary), str(metadata), str(disasm)], check=True)
        return binary.read_bytes(), json.loads(metadata.read_text()), disasm.read_text()

    first, metadata, disasm = assemble(shader, 'first')
    second, again, decoded_again = assemble(shader, 'second')
    assert first == second and metadata == again and disasm == decoded_again
    assert len(first) == metadata['binary_bytes'] == 128
    assert metadata['chip_id'] == '0x43051401' and metadata['generation'] == 7
    assert metadata['local_size'] == [8, 1, 1] and metadata['buffer_dwords'] == [8]
    assert metadata['local_invocation_id_regid'] == 0
    assert not metadata['device_opened'] and not metadata['gpu_executed']
    instructions = re.findall(r'^\s*\d+\[[0-9a-f]+_[0-9a-f]+\]\s*(.*)$', disasm, re.M)
    assert len(instructions) * 8 == len(first)
    assert any('stib.b.untyped.1d.u32.1.imm r1.x, r0.x, 0' in s for s in instructions)
    roundtrip = out / 'roundtrip.asm'
    headers = '\n'.join(s for s in shader.read_text().splitlines() if s.startswith('@'))
    roundtrip.write_text(headers + '\n' + '\n'.join(instructions) + '\n')
    rebuilt, _, _ = assemble(roundtrip, 'roundtrip')
    def without_padding(binary):
        while binary.endswith(bytes(8)):
            binary = binary[:-8]
        return binary

    assert without_padding(rebuilt) == without_padding(first)
    invalid = out / 'invalid.asm'
    invalid.write_text('@localsize 8, 1, 1\nnot_an_ir3_instruction\n')
    result = subprocess.run([str(tool), str(invalid), str(out / 'invalid.bin'), str(out / 'invalid.json'), str(out / 'invalid.disasm')], capture_output=True)
    assert result.returncode != 0 and not (out / 'invalid.bin').exists()
    print(json.dumps({'FD750_offline_assembly': 'passed', 'deterministic': True,
                      'decode_reassemble_instruction_bytes_identical': True,
                      'padding_normalized_like_Mesa_validator': True, 'bytes': len(first),
                      'sha256': hashlib.sha256(first).hexdigest(), 'gpu_executed': False}))
