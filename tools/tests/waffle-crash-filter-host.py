#!/usr/bin/env python3
"""Run the actual pinned qdl filename filter on observed PJD110 segment names."""
from pathlib import Path
import importlib.util, re, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('capture',ROOT/'tools/capture-waffle-crash.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
source=(ROOT/'work/waffle/gpu/qdl-source/src/sahara.c').read_text()
code=source[source.index('bool pattern_match('):source.index('static int write_zeroes(')]
code='#define _GNU_SOURCE\n#include <stdbool.h>\n#include <stdlib.h>\n#include <string.h>\n#include <limits.h>\n#include <assert.h>\n#include <stdio.h>\n'+code
code+='\nint main(void) {\nconst char *filter="'+capture.SEGMENTS+'";\n'
for stem in capture.DIAGNOSTIC_SEGMENTS+[f'md_MSGRAM{i}' for i in range(16)]:
    code+=f'assert(!sahara_debug64_filter("{stem}.BIN",filter));\n'
for name in ['md_TZ_AES_KEY.BIN','md_TZ_AES_IV.BIN','md_TZ_HMAC.BIN','md_wrpd_keys.BIN',
             'md_encr_iv.BIN','md_encr_mac.BIN','md_CPUCP_DDRMEM.BIN','DDR.BIN','load.cmm']:
    code+=f'assert(sahara_debug64_filter("{name}",filter));\n'
code+='puts("Native qdl filter: all27 selected PJD110 diagnostic segments match, 9 other segments excluded");}\n'
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
