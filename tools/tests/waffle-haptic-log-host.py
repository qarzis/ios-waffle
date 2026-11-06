#!/usr/bin/env python3
"""Exercise the actual torch formatter and bounded loader record wrapper."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
torch = (root / 'kernel/files/bsd/dev/macan_torch.c').read_text()
loader = (root / 'kernel/files/osfmk/arm64/loader_return.c').read_text()
formatter = torch[torch.index('static int\nsay('):torch.index('\n#define NOTES')]
wrapper = loader[loader.index('void\nloader_log_line('):loader.index('\nstatic void\nloader_log_puts')]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static bool leaving = true;
static char output[1024];
static size_t used, calls, largest;
static bool ml_get_interrupts_enabled(void) { return false; }
static void loader_log_write(const char *s, size_t n) {
 assert(n <= 64 && used + n < sizeof(output));
 memcpy(output + used, s, n); used += n; output[used] = 0;
 calls++; if (n > largest) largest = n;
}
''' + wrapper + '\n' + formatter + r'''
int main(void) {
 const char *records[] = {
  "haptic-waffle-service: ready=1\n",
  "haptic-waffle-service: format=S16_mono tap_us=16000\n",
  "haptic-waffle-service: cooldown_us=80000\n"
 };
 for (unsigned i = 0; i < 3; i++) {
  used = calls = largest = 0; say("%s", records[i]);
  assert(calls == 1 && !strcmp(output, records[i]));
 }
 char long_record[401]; memset(long_record, 'x', 400); long_record[400] = 0;
 used = calls = largest = 0; assert(say("%s", long_record) == 400);
 assert(used == 299 && calls == 5 && largest == 64);
 assert(!memcmp(output, long_record, used));
 puts("PASS actual haptic formatter: READY records single bounded copies; truncation and 64-byte maximum preserved.");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(code)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(path / 'test.c'),
                    '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
