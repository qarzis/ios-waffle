#!/usr/bin/env python3
"""Exercise actual ADSP SCM continuation logic with mocked register returns."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT/'kernel/files/bsd/dev/macan_adsp.c').read_text()
macros = s[s.index('#define SCM_64'):s.index('static LCK_MTX_DECLARE(dsp_lock')]
fn = s[s.index('static int32_t\nscm('):s.index('static uint32_t\nour_item_find(')]
fn = re.sub(r'register uint64_t (x[0-7]) __asm__\("x[0-7]"\)',r'uint64_t \1',fn)
fn, count = re.subn(r'__asm__ volatile \("smc #0".*?"memory"\);',
    'mock_smc(&x0,&x1,&x2,&x3,&x4,&x5,&x6,&x7);',fn,flags=re.S)
assert count == 1
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static bool waffle_board,scm_incomplete;
static unsigned step,calls,scenario;
static uint64_t elapsed;
static char last_write[96];
static uint64_t now_us(void) { return elapsed; }
static void sleep_us(unsigned us) { elapsed+=us; }
static void mock_smc(uint64_t *x0,uint64_t *x1,uint64_t *x2,uint64_t *x3,
    uint64_t *x4,uint64_t *x5,uint64_t *x6,uint64_t *x7) {
 assert(*x1==1 && *x2==1 && !*x3 && !*x4 && !*x5 && !*x7);
 if(scenario==5) { assert(*x0==0x42000206 && !*x6); }
 else { assert(*x0==(calls?1:0x42000206));assert(*x6==calls); }
 calls++;
 if(scenario==3 || scenario==4) { *x0=scenario==3?2:3;*x1=1;*x2=0x1a9;*x3=0;return; }
 if(scenario==5 && calls<3) { *x0=(uint64_t)-12;return; }
 if(scenario==2 || scenario==6 || (scenario==1 && calls<=250)) { *x0=1;*x6=calls;return; }
 *x0=0;*x1=77;
}
'''
cases = r'''
static void reset(unsigned mode) { scenario=mode;calls=0;elapsed=0;scm_incomplete=false;waffle_board=true; }
int main(void) {
 uint64_t answer=0;
 reset(0);assert(!scm("test",0x206,1,1,0,0,&answer) && calls==1 && answer==77);
 reset(1);assert(!scm("test",0x206,1,1,0,0,&answer) && calls==251 && elapsed==25000 && !scm_incomplete);
 reset(2);assert(scm("test",0x206,1,1,0,0,&answer)==-ETIMEDOUT && scm_incomplete && elapsed==2000000);
 unsigned saved=calls;assert(scm("dependent PAS",0x206,1,36,0,0,&answer)==-EBUSY && calls==saved);
 for(unsigned mode=3;mode<=4;mode++) { reset(mode);assert(scm("test",0x206,1,1,0,0,&answer)==-EWOULDBLOCK && calls==1 && scm_incomplete); }
 reset(5);assert(!scm("test",0x206,1,1,0,0,&answer) && calls==3 && elapsed==60000 && !scm_incomplete);
 reset(6);waffle_board=false;assert(scm("test",0x206,1,1,0,0,&answer)==-1 && calls==100 && !scm_incomplete);
 puts("PASS: actual SCM loop:250 interruptions preserve A6/context,2s timeout blocks dependent calls, unhandled WAITQ is retained rather than blindly resumed, busy retries and donor behavior preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='waffle-adsp-scm-') as temp:
    p = Path(temp)
    (p/'test.c').write_text(prefix+macros+fn+cases)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-format',
        '-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
