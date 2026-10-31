#!/usr/bin/env python3
"""Real loader log composition: preserve completed logs beyond console capacity."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / 'loader/loader.c').read_text()
code = s[s.index('static char out_buf['):s.index('static void\nflush_log(void)')]
branch = s[s.index('  } else if (starts_with(cmd, "oem log")) {'):]
branch = branch[branch.index('   if (busy) {'):branch.index('   fb_reply(')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define XNU_OWNED_RAM 1
#define EFI_ERROR(x) ((x)!=0)
typedef struct efi_block_io efi_block_io;
struct media {uint64_t block_size,media_id;};
struct efi_block_io {struct media *media;int (*write_blocks)(efi_block_io *,uint64_t,uint64_t,uint64_t,void *);void (*flush_blocks)(efi_block_io *);};
static char log_buf[32768];static uint64_t log_len;
static void put_char(char c) {if(log_len<sizeof(log_buf)-1)log_buf[log_len++]=c;}
static void print(const char *s) {while(*s)put_char(*s++);}
static int busy,running_live,running_slide,live_calls;
static void compose_live_log(int a,int b) {(void)a;(void)b;++live_calls;}
'''
tests = r'''
static char full[71702];
int main(void) {
 memset(full,'x',sizeof(full));memcpy(full+70000,"FINAL_SHUTDOWN_COMPLETE",23);
 write_logs(full,sizeof(full));
 assert(log_len==32767 && completed_kernel_log==full);
 oem_log();
 assert(staged_data==out_buf && staged_len>sizeof(full));
 assert(strstr(out_buf,"FINAL_SHUTDOWN_COMPLETE"));
 assert(strstr(out_buf,"== END OF LOG =="));
 busy=1;oem_log();assert(live_calls==1);busy=0;
 write_logs(NULL,0);oem_log();assert(!completed_kernel_log && !completed_kernel_log_len);
 puts("Loader: actual oem log retains completed 71KB kernel log despite 32KB console, live path and reset tested");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    (p / 'test.c').write_text(harness + code + '\nstatic void oem_log(void) {\n' + branch + '\n}\n' + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g', str(p / 'test.c'),
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
