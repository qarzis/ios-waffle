#!/usr/bin/env python3
from pathlib import Path
import runpy,re,tempfile,subprocess
r=Path(__file__).resolve().parents[2];normalize=runpy.run_path(str(r/'tools/waffle_bo_log.py'))['normalize']
s=(r/'kernel/files/bsd/dev/waffle_smmu.c').read_text();code=s[s.index('static bool smmu_compact_bo_enabled('):s.index('static bool smmu_registry_reclaim(')]
h=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "waffle_gpu_memory.h"
static unsigned enabled,calls,emits;
static bool PE_parse_boot_argn(const char *name,void *out,int bytes){assert(!strcmp(name,"waffle_display_irq_probe") && bytes==4);*(uint32_t *)out=enabled;calls++;return enabled!=0;}
static void loader_log_line(const char *line){assert(strlen(line)<64 && line[strlen(line)-1]=='\n');emits++;fputs(line,stdout);}
'''
t=r'''
int main(int argc,char **argv){assert(argc==2);enabled=atoi(argv[1]);
 struct waffle_gpu_memory bo={.serial=0xffffffff,.gpu_va=0x10ffffffcULL,.bytes=0xc000000,.allocation_bytes=0xc000000,.flags=0x20002};
 smmu_compact_bo_new(&bo);smmu_compact_bo_retired(bo.serial,bo.gpu_va,bo.bytes,0xc000000);
 assert(calls==1 && emits==(enabled==1?3u:0u));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 for mode in ('0','1','2'):
  raw=subprocess.check_output([str(p/'test'),mode],text=True)
  if mode=='1':assert normalize(raw).count('GENERAL_BO ')==2
ns={'__file__':str(r/'tools/tests/waffle-generation-log-host.py')};source=(r/'tools/tests/waffle-generation-log-host.py').read_text();exec(source,ns)
# Reuse the existing full guarded lifecycle fixture; only event serialization changes.
m=ns['m'];text=ns['short'];validate=lambda value:m.validate_gl_bo_lifetimes(value,ns['capacity'],ns['budget'],268435456)[0]
def pub(match):return '!wbo+'+'/'.join(format(int(v,16 if i in (1,4) else 10),'x') for i,v in enumerate(match.groups()))+'!'
def free(match):
 v=match.groups();return f'!wbo-{int(v[0]):x}/{v[1]}/{int(v[2]):x}/{int(v[6]):x}!'
compact='!wbo:v1!\n'+re.sub(runpy.run_path(str(r/'tools/waffle_bo_log.py'))['FREE'],free,re.sub(runpy.run_path(str(r/'tools/waffle_bo_log.py'))['PUB'],pub,text))
assert len(validate(compact))==2
# A malformed verbose log cannot replace or supply a missing compact record.
assert len(validate(compact+'\nGENERAL_BO published index=10 user text VA=broken\n'))==2
bad=re.sub(r'!wbo\+[^!]+!','',compact,count=1)
try:validate(bad)
except RuntimeError:pass
else:raise AssertionError('Missing compact publication accepted')
print('PASS actual <=64-byte BO emitters/default off and full typed lifecycle proof; corrupt verbose text never reconstructed, missing record refused.')
