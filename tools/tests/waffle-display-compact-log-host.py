#!/usr/bin/env python3
"""Actual C++ display formatter, full-width data and strict packet decoding."""
from pathlib import Path
import subprocess,tempfile,runpy,re
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_text()
types=s[s.index('struct WaffleDisplayCompletionRecord'):s.index('static bool waffleDisplayIRQProbeRead(')]
code=s[s.index('static void waffleDisplayCompactLog('):s.index('static bool waffleDisplayFlipRead(')].replace('__builtin_arm_rsr64("CNTFRQ_EL0")','19200000ULL')
h=r'''
#include <cassert>
#include <cstdint>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "waffle_display_irq_probe.h"
#define __printflike(a,b) __attribute__((format(printf,a,b)))
using vm_offset_t=uintptr_t;
static unsigned gWaffleDisplayIRQProbe=1;
static void loader_log_line(const char *line){assert(strlen(line)<64 && line[strlen(line)-1]=='\n');fputs(line,stdout);}
static void redwood_tl(const char *,...){assert(false);}
'''
t=r'''
int main(int argc,char **argv){assert(argc==2);bool maximum=atoi(argv[1]);
 WaffleDisplayFlipContext c{};WaffleDisplayCompletionRecord records[128]{};c.audit=records;c.auditCount=maximum?128:5;c.probeWrites=maximum?0:1;
 for(unsigned i=0;i<c.auditCount;i++){
  auto &r=records[i];r.sequence=1;r.stage=i==0?2:i==1?3:1;r.ticks=1000+100*i;r.valid=true;
  auto &v=r.sample;v.frame_before=v.frame_after=i<2?10:i==4?12:11;v.flush=i==1?3:0;v.scheduler=v.auto_status=1;
  v.write_line=maximum?UINT32_MAX:3168;v.address0=v.address1=i==0?WAFFLE_DISPLAY_FRONT:WAFFLE_DISPLAY_TEST;
  v.irq_top=0x100;v.irq_ctl=0x200;v.irq_tear=0x4f;v.ctl_active=2;
  if(maximum){r.sequence=9;r.stage=3;r.ticks=UINT64_MAX-128+i;v.frame_before=v.frame_after=UINT32_MAX;v.address0=v.address1=UINT32_MAX;v.irq_top=v.irq_ctl=v.irq_tear=UINT32_MAX;}
 }
 if(!maximum){records[2].probe={.action=1,.status_after=0,.mux=0xf0000,.version=0xa0000000,.wrote=true};records[3].probe={.action=2,.status_after=0x100};}
 waffleDisplayCompletionLog(&c);assert(c.auditLogged && !c.auditStage);
}
'''
normalize=runpy.run_path(str(r/'tools/waffle_display_log.py'))['normalize'];analyze=runpy.run_path(str(r/'tools/analyze-waffle-display-completion.py'))['analyze']
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(h+types+code+t)
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-missing-field-initializers','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 raw=subprocess.check_output([str(p/'test'),'0'],text=True);a=analyze(raw);assert a['wire_protocol']=='compact_v1' and a['irq_probe']['writes']==a['irq_probe']['fresh_events']==1 and not a['one_frame_retirement_qualified']
 assert analyze(raw+raw)==a
 maximum=subprocess.check_output([str(p/'test'),'1'],text=True);decoded=normalize(maximum);assert 'ticks=18446744073709551614' in decoded and 'address1=ffffffff' in decoded and 'write_line=4294967295' in decoded
 missing=re.sub(r'!dpc:2/[^!]+!','',raw,count=1)
 for bad in [missing,raw+'!dpc:2/1/2/3/4!\n',raw.replace('!dph:v1/5/','!dph:v1/81/'),raw+'!dph:error!\n']:
  try:analyze(bad)
  except ValueError:pass
  else:raise AssertionError('Incomplete/conflicting/overflowed display data accepted')
print('PASS actual C++ display packets <64 bytes: full 64-bit ticks/32-bit addresses, replay, clear/fresh transaction and strict incomplete/conflict/overflow refusal; no hardware claim.')
