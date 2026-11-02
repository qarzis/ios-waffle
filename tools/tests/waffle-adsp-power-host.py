#!/usr/bin/env python3
"""Compare the Waffle power planner with captured cmd-db and native BCM encoding."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmd-db', type=Path, required=True)
    ap.add_argument('--native', type=Path, required=True)
    args = ap.parse_args()
    database = {}
    for line in args.cmd_db.read_bytes().decode().replace('\0', '').splitlines():
        m = re.fullmatch(r'0x([0-9a-f]+): (\S+) \[([0-9a-f ]+)\]', line)
        if m:
            database[m[2]] = (int(m[1], 16), bytes.fromhex(m[3]))
    names = ['lcx.lvl','lmx.lvl','xo.lvl','MC0','SH0','SH1','SN0','SN3','CE0','LP0','ACV']
    fixture = []
    for name in names:
        address, aux = database[name]
        fixture.append('{'+json.dumps(name)+f',{{{address}, {len(aux)}, {{'+','.join(map(str,aux))+'}}}')
    source = (args.native/'drivers/interconnect/qcom/bcm-voter.c').read_text()
    native = source[source.index('static inline void tcs_cmd_gen('):source.index('static void tcs_list_gen(')]
    kernel = (ROOT/'kernel/files/bsd/dev/macan_adsp.c').read_text()
    lookup_source = kernel[kernel.index('#define CMD_DB_PHYS'):kernel.index('static bool\nwaffle_power_preflight(')]
    c = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define cpu_to_le32(v) (v)
#include "include/soc/qcom/tcs.h"
#include "waffle_adsp_power.h"
#define __unused __attribute__((unused))
#define VM_WIMG_WCOMB 0
typedef uintptr_t vm_offset_t;
static vm_offset_t ml_io_map_unmappable(vm_offset_t p, size_t n, unsigned f) {
 (void)p; (void)n; (void)f; return 0;
}
static size_t strlcpy(char *dst,const char *src,size_t size) {
 size_t n=strlen(src);
 if(size) { size_t copy=n<size-1?n:size-1; memcpy(dst,src,copy);dst[copy]=0; }
 return n;
}
'''
    c += native
    c += lookup_source
    c += '\nstatic const struct { const char *name; struct waffle_adsp_resource r; } fixture[] = {\n'+',\n'.join(fixture)+'\n};\n'
    c += r'''
static int fault;
static bool lookup(void *unused, const char *name, struct waffle_adsp_resource *r) {
 (void)unused;
 for (unsigned i=0;i<11;i++) if (!strcmp(name,fixture[i].name)) {
  *r=fixture[i].r;
  if (fault==1 && i==0) ++r->address;
  if (fault==2 && i==0) r->length=33;
  if (fault==3 && i==0) memset(r->aux,0,sizeof(r->aux));
  if (fault==4 && i==5) ++r->aux[6];
  if (fault==5 && i==0) r->aux[2]=255;
  if (fault==6 && i==7) return false;
  return true;
 }
 return false;
}
int main(void) {
 struct waffle_adsp_power_command plan[11];
 assert(waffle_adsp_power_plan(lookup,NULL,plan));
 assert(plan[0].value==7 && plan[1].value==4 && plan[2].value==3);
 unsigned commits=0;
 for (unsigned i=3;i<11;i++) {
  bool mask=!strcmp(plan[i].name,"SH1") || !strcmp(plan[i].name,"ACV");
  bool commit=i==10 || fixture[i].r.aux[6]!=fixture[i+1].r.aux[6];
  struct tcs_cmd reference;
  tcs_cmd_gen(&reference,mask?0:UINT64_MAX,mask?1:UINT64_MAX,fixture[i].r.address,commit,true);
  assert(plan[i].address==reference.addr && plan[i].value==reference.data);
  assert(plan[i].commit==commit);
  commits+=commit;
 }
 assert(commits==6);
 for (fault=1;fault<=6;fault++) assert(!waffle_adsp_power_plan(lookup,NULL,plan));
 _Alignas(16) unsigned char raw[CMD_DB_SIZE]={0};
 struct cmd_db_header *db=(void *)raw;
 memcpy(db->magic,"\xdb\x30\x03\x0c",4);
 db->slave[0].id=3; db->slave[0].count=3;
 db->slave[1].id=5; db->slave[1].count=8;
 db->slave[1].header_offset=3*sizeof(struct cmd_db_entry);
 unsigned aux=11*sizeof(struct cmd_db_entry);
 for(unsigned i=0;i<11;i++) {
  struct cmd_db_entry *entry=(void *)(db->data+i*sizeof(*entry));
  memcpy(entry->id,fixture[i].name,strlen(fixture[i].name));
  entry->address=fixture[i].r.address;entry->length=fixture[i].r.length;
  entry->offset=aux;
  memcpy(db->data+aux,fixture[i].r.aux,entry->length);aux+=entry->length;
 }
 cmd_db=db;
 assert(waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));
 db->magic[0]=0;assert(!waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));db->magic[0]=0xdb;
 db->slave[0].count=513;assert(!waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));db->slave[0].count=3;
 db->slave[0].data_offset=65535;
 struct cmd_db_entry *first=(void *)db->data;unsigned saved=first->offset;first->offset=65535;
 assert(!waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));first->offset=saved;db->slave[0].data_offset=0;
 db->slave[0].id=5;assert(!waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));db->slave[0].id=3;
 assert(waffle_adsp_power_plan(waffle_power_lookup,NULL,plan));
 puts("PASS: native rail indices7/4/3; all8 BCMs match native tcs_cmd_gen;6 VCD commits;6 corrupt/missing-resource cases rejected");
 puts("PASS: actual kernel cmd-db parser accepts native resource layout and rejects invalid magic/count/aux bounds/slave ID");
}
'''
    with tempfile.TemporaryDirectory(prefix='waffle-adsp-power-') as temp:
        p = Path(temp)
        (p/'test.c').write_text(c)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(args.native.resolve()),'-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
        subprocess.run([str(p/'test')],check=True)


if __name__=='__main__':
    main()
