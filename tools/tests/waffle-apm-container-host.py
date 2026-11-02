#!/usr/bin/env python3
"""Compare emitted container type with the pinned AudioReach container factory."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--engine', type=Path, required=True)
args = ap.parse_args()
props = (args.engine/'fwk/api/apm/apm_graph_properties.h').read_text()
cu = (args.engine/'fwk/spf/containers/cmn/container_utils/core/src/cu.c').read_text()
constants = '\n'.join(re.findall(r'^#define APM_CONTAINER_TYPE_ID_\w+\s+0x[0-9a-fA-F]+', props, re.M))
table = cu[cu.index('const uint32_t global_cntr_list_t[]'):cu.index('const spf_cntr_create_function_t global_cntr_create_ftable[]')]
lookup = cu[cu.index('static ar_result_t cu_get_index_for_cntr_type('):cu.index('static ar_result_t cu_cmn_get_container_type_id(')]
program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "waffle_apm.h"
typedef uint32_t ar_result_t;
#define AR_EOK 0
#define AR_EFAILED 1
#define SIZE_OF_ARRAY(a) (sizeof(a)/sizeof(a[0]))
''' + constants + '\n' + table + lookup + r'''
int main(void) {
 uint32_t index,packet[128];
 assert(cu_get_index_for_cntr_type(1,&index)==AR_EFAILED && index==UINT32_MAX);
 assert(cu_get_index_for_cntr_type(APM_CONTAINER_TYPE_ID_GC,&index)==AR_EOK && index==1);
 assert(cu_get_index_for_cntr_type(APM_CONTAINER_TYPE_ID_SC,&index)==AR_EOK && index==0);
 assert(cu_get_index_for_cntr_type(2,&index)==AR_EFAILED);
 assert(waffle_apm_packet(packet,sizeof(packet),WAFFLE_APM_GRAPH_OPEN,2)==344);
 unsigned found=0;
 for(unsigned i=10;i+3<344/4;i++)if(packet[i]==0x08001011){
  assert(packet[i+1]==8 && packet[i+2]==1);
  assert(packet[i+3]==APM_CONTAINER_TYPE_ID_GC);
  assert(cu_get_index_for_cntr_type(packet[i+3],&index)==AR_EOK && index==1);
  found++;
 }
 assert(found==1);
 puts("PASS actual pinned AudioReach factory rejects legacy capability1; emitted generic container type accepted. Host ABI hypothesis only; native firmware unqualified.");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path/'test.c').write_text(program)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I', str(root/'kernel/files/bsd/sys'),
                    str(path/'test.c'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
