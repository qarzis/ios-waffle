#!/usr/bin/env python3
"""Bounded hardware clock counter: native constants, units and rollback faults."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
vendor = (ROOT / 'work/waffle/gpu/vendor/debugcc-pineapple.c').read_text()
for name, value in (('measure_only_gpu_cc_gx_gfx3d_clk', 'F'), ('gpu_cc_cx_gmu_clk', '1F')):
    assert re.search(r'0x' + value + r',\s*/\* ' + name + r' \*/', vendor)
for field, value in (('ctl_reg', '62048'), ('status_reg', '6204C'),
                     ('xo_div4_cbcr', '62008'), ('debug_offset', '9564')):
    assert re.search(r'\.' + field + r'\s*= 0x' + value, vendor)
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_gpu_measure.h"
struct reg {unsigned bank,off;uint32_t value,saved;};
struct model {
 struct reg reg[8];unsigned writes,drop,us,samples;bool timeout,off;
};
static struct reg *reg_at(struct model *m,unsigned bank,unsigned off) {
 for(unsigned i=0;i<8;i++)if(m->reg[i].bank==bank && m->reg[i].off==off)return &m->reg[i];
 assert(0);return NULL;
}
static uint32_t read_reg(void *arg,unsigned bank,uint32_t off) {
 struct model *m=arg;
 if(!bank && off==0x6204c) {
  if(m->timeout)return 0;
  uint64_t hz=(reg_at(m,1,0x9564)->value&255)==0xf?231000000:260000000;
  unsigned ticks=reg_at(m,0,0x62048)->value&0xfffff;
  return (1u<<25)|(m->off?0:(uint32_t)((uint64_t)ticks*hz/(4*4800000)));
 }
 return reg_at(m,bank,off)->value;
}
static void write_reg(void *arg,unsigned bank,uint32_t off,uint32_t value) {
 struct model *m=arg;struct reg *r=reg_at(m,bank,off);
 if(++m->writes==m->drop)return;
 if(!bank && off==0x62048 && (value&(1u<<20)))++m->samples;
 r->value=value;
}
static void delay_us(void *arg,unsigned us) {struct model *m=arg;m->us+=us;}
static void init(struct model *m) {
 *m=(struct model){.reg={{0,0x62024,0x80100123,0},{0,0x62000,0x88000007,0},
 {0,0x62004,0x80000000,0},{0,0x62008,0x80000000,0},
 {0,0x62048,0x80000018,0},{1,0x9564,0x81000018,0},
 {1,0x9270,0x82000005,0},{1,0x9274,0x80000000,0}}};
 for(unsigned i=0;i<8;i++)m->reg[i].saved=m->reg[i].value;
}
static void restored(struct model *m) {
 for(unsigned i=0;i<8;i++)assert(m->reg[i].saved==m->reg[i].value);
}
int main(void) {
 struct model m;struct waffle_measure_io io={&m,read_reg,write_reg,delay_us};
 struct waffle_measure_result r;
 init(&m);assert(waffle_measure_clock(&io,0xf,&r) && r.complete && r.restored);
 assert(r.hz>230990000 && r.hz<231010000 && m.samples==2);restored(&m);
 unsigned total=m.writes;
 init(&m);assert(waffle_measure_clock(&io,0x1f,&r));
 assert(r.hz>259990000 && r.hz<260010000);restored(&m);
 init(&m);m.off=true;assert(waffle_measure_clock(&io,0xf,&r) && r.hz==0);restored(&m);
 init(&m);m.timeout=true;assert(!waffle_measure_clock(&io,0xf,&r) && r.restored);
 assert(m.us==40001 && m.samples==1);restored(&m);
 init(&m);reg_at(&m,0,0x62048)->value|=1u<<20;
 assert(!waffle_measure_clock(&io,0xf,&r) && m.writes==0);
 init(&m);assert(!waffle_measure_clock(&io,8,&r) && m.writes==0);
 for(unsigned fail=1;fail<=total;fail++) {
  init(&m);m.drop=fail;
  bool ok=waffle_measure_clock(&io,0xf,&r);
  if(r.restored)restored(&m);
  if(ok)assert(r.complete && r.restored);
 }
 puts("Actual clock counter: native selectors, Hz units, zero clock, bounded timeout and every dropped write/rollback tested; host only");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    (p / 'test.c').write_text(code)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g',
                    '-I', str(ROOT / 'kernel/files/bsd/sys'), str(p / 'test.c'),
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
