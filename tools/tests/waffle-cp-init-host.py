#!/usr/bin/env python3
"""Check full-init and first-command HFI encoders against pinned native Gen7 code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
VENDOR=ROOT/'work/waffle/gpu/vendor'
pm4=(VENDOR/'adreno_pm4types.h').read_text()
assert hashlib.sha256(pm4.encode()).hexdigest()=='19208220eea356f1d260d316e958f81196766a7528569b6baf33592639468aaf'
gen7=(VENDOR/'adreno_gen7.c').read_text()
assert hashlib.sha256(gen7.encode()).hexdigest()=='1d63fca08e1d45428b80342d3d35a8c4166ad93c74ade6d125d2b3f9f4267d5d'
hfi=(VENDOR/'adreno_hfi.h').read_text()

def function(text,name):
    return re.search(r'(?:static inline uint|void) '+name+r'\([^}]+\n\}',text)[0]

code='''#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_hfi.h"
typedef uint32_t uint;
typedef uint32_t u32;
#define BIT(n) (1u<<(n))
#define CP_TYPE7_PKT (7u<<28)
#define CP_THREAD_CONTROL 0x17
#define CP_ME_INIT 0x48
#define lower_32_bits(x) ((uint32_t)(x))
#define upper_32_bits(x) ((uint32_t)((x)>>32))
struct memory { uint64_t gpuaddr; };
struct adreno_device { bool dms_enabled; struct memory *pwrup_reglist; };
'''
for name in ('CREATE_MSG_HDR','MSG_HDR_SET_SIZE','MSG_HDR_SET_SEQNUM'):
    code+=re.search(r'#define '+name+r'\([^\n]+\\\n[^\n]+',hfi)[0]+'\n'
code+='\n'.join((function(pm4,'pm4_calc_odd_parity_bit'),function(pm4,'cp_type7_packet'),
                  function(gen7,'gen7_cp_init_cmds')))
code+='''
int main(void) {
 uint64_t addresses[]={0x61000000ULL,0x101000000ULL,0x7ffffff000ULL,0x1ff8080070000ULL,0x1fffffffff000ULL};
 uint32_t output[13],expected[11],before[13],thread[5],thread_expected[3];
 for (unsigned i=0;i<sizeof(addresses)/sizeof(addresses[0]);i++) for (unsigned seq=1;seq<=4095;seq++) {
  struct memory memory={addresses[i]};
  struct adreno_device device={false,&memory};
  memset(output,0xa5,sizeof(output));
  expected[0]=CREATE_MSG_HDR(131,0);
  expected[0]=MSG_HDR_SET_SIZE(expected[0],11);
  expected[0]=MSG_HDR_SET_SEQNUM(expected[0],seq);
  gen7_cp_init_cmds(&device,&expected[1]);
  assert(waffle_hfi_cp_init_packet(output,13,seq,addresses[i])==11);
  assert(!memcmp(output,expected,sizeof(expected)));
  assert(output[11]==0xa5a5a5a5 && output[12]==0xa5a5a5a5);
  memset(thread,0xa5,sizeof(thread));
  thread_expected[0]=CREATE_MSG_HDR(131,0);
  thread_expected[0]=MSG_HDR_SET_SIZE(thread_expected[0],3);
  thread_expected[0]=MSG_HDR_SET_SEQNUM(thread_expected[0],seq);
  thread_expected[1]=expected[1];thread_expected[2]=expected[2];
  assert(waffle_hfi_cp_thread_packet(thread,5,seq)==3);
  assert(!memcmp(thread,thread_expected,sizeof(thread_expected)));
  assert(thread[3]==0xa5a5a5a5 && thread[4]==0xa5a5a5a5);
 }
 memset(output,0x5a,sizeof(output));memcpy(before,output,sizeof(output));
 assert(!waffle_hfi_cp_init_packet(output,10,1,0x61000000));
 assert(!waffle_hfi_cp_init_packet(output,13,0,0x61000000));
 assert(!waffle_hfi_cp_init_packet(output,13,4096,0x61000000));
 assert(!waffle_hfi_cp_init_packet(output,13,1,0));
 assert(!waffle_hfi_cp_init_packet(output,13,1,0x61000001));
 assert(!waffle_hfi_cp_init_packet(output,13,1,1ULL<<39));
 assert(!waffle_hfi_cp_init_packet(0,13,1,0x61000000));
 assert(!memcmp(output,before,sizeof(output)));
 memset(thread,0x5a,sizeof(thread));
 assert(!waffle_hfi_cp_thread_packet(thread,2,1));
 assert(!waffle_hfi_cp_thread_packet(thread,5,0));
 assert(!waffle_hfi_cp_thread_packet(thread,5,4096));
 assert(!waffle_hfi_cp_thread_packet(0,5,1));
 for (unsigned i=0;i<5;++i) assert(thread[i]==0x5a5a5a5a);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory);(path/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I',str(ROOT/'kernel/files/bsd/sys'),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
print(json.dumps({'native_cp_init_comparison':'passed','cases':20475,
                  'sanitizers':'ASan+UBSan','hardware_tested':False,'runtime_integrated':True}))
