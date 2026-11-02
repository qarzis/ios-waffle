#!/usr/bin/env python3
"""Exercise the kernel's actual GPR reply correlation and SPF semantics."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/macan_adsp.c').read_text()
actual=s[s.index('#define APM_CMD_GET_SPF_STATE'):s.index('static bool\nstep_gpr(')]
prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "waffle_apm.h"
#define LCK_MTX_DECLARE(n,g) int n
#define os_atomic_load(p,o) (*(p))
#define os_atomic_store(p,v,o) (*(p)=(v))
static void lck_mtx_lock(int *p) { assert(!*p);*p=1; }
static void lck_mtx_unlock(int *p) { assert(*p);*p=0; }
'''
cases=r'''
static void reset(uint32_t opcode) { gpr_token=7;gpr_expected_opcode=opcode;gpr_error=99;gpr_answered=false;gpr_state=0; }
int main(void) {
 struct { struct gpr_header h;uint32_t words[2]; } reply={
  .h={.packet=32u<<8|6u<<4,.domains=0x0203,.source_port=1,.dest_port=1,.token=7,.opcode=GPR_BASIC_RSP_RESULT},
  .words={WAFFLE_APM_GRAPH_OPEN,0}};
 reset(WAFFLE_APM_GRAPH_OPEN);gpr_input((void *)&reply,32);assert(gpr_answered && !gpr_error);
 reply.words[1]=17;gpr_input((void *)&reply,32);assert(!gpr_error);reply.words[1]=0;
 reset(WAFFLE_APM_GRAPH_OPEN);reply.h.token=6;gpr_input((void *)&reply,32);assert(!gpr_answered);reply.h.token=7;
 reply.words[0]=WAFFLE_APM_GRAPH_CLOSE;gpr_input((void *)&reply,32);assert(!gpr_answered);reply.words[0]=WAFFLE_APM_GRAPH_OPEN;
 reply.h.dest_port=9;gpr_input((void *)&reply,32);assert(!gpr_answered);reply.h.dest_port=1;
 reply.h.domains=0x0302;gpr_input((void *)&reply,32);assert(!gpr_answered);reply.h.domains=0x0203;
 reply.h.packet=36u<<8|6u<<4;gpr_input((void *)&reply,32);assert(!gpr_answered);
 reply.h.packet=28u<<8|6u<<4;gpr_input((void *)&reply,28);assert(!gpr_answered);reply.h.packet=32u<<8|6u<<4;
 reply.words[1]=17;gpr_input((void *)&reply,32);assert(gpr_answered && gpr_error==17);
 reset(WAFFLE_APM_GRAPH_CLOSE);reply.words[0]=WAFFLE_APM_GRAPH_CLOSE;reply.words[1]=0;gpr_input((void *)&reply,32);assert(gpr_answered && !gpr_error);
 reset(APM_CMD_GET_SPF_STATE);reply.words[0]=APM_CMD_GET_SPF_STATE;gpr_input((void *)&reply,32);assert(!gpr_answered);
 reply.h.opcode=APM_CMD_RSP_GET_SPF_STATE;reply.h.packet=28u<<8|6u<<4;reply.words[0]=1;
 gpr_input((void *)&reply,28);assert(gpr_answered && gpr_state==1 && !gpr_error);
 reset(WAFFLE_APM_GRAPH_OPEN);gpr_input((void *)&reply,28);assert(!gpr_answered);
 (void)gpr_out;(void)audio_up;
 puts("PASS: actual GPR parser matches token/opcode/domain/ports/length; graph ACK0/errors and duplicate refusal; SPF still requires its dedicated state response");
}
'''
with tempfile.TemporaryDirectory(prefix='waffle-gpr-reply-') as temp:
    p=Path(temp)
    (p/'test.c').write_text(prefix+actual+cases)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
