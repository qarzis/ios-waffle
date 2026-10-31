#!/usr/bin/env python3
"""Exercise real GMU clock-session code: detach before PLL reset/restore."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <sys/waffle_gmu_clock.h>
struct model {uint32_t r[0x1040/4],cfg;bool power,reset,gxoff,lock,latch,busy;unsigned writes,fail;};
static uint32_t read_pll(void *arg,unsigned off) {
 struct model *m=arg;assert(off>=0x1000 && off<=0x1038 && !(off&3));return m->r[off/4];
}
static bool write_pll(void *arg,unsigned off,uint32_t v) {
 struct model *m=arg;assert(m->power);assert(off>=0x1000 && off<=0x1038 && !(off&3));
 if(++m->writes==m->fail)return false;
 if(off==0x1004 && !v)assert((m->cfg&0x71f)!=0x303); /* never disable selected PLL */
 m->r[off/4]=v;
 if(off==0x1004 && v==1 && m->lock){m->r[0x1000/4]|=1u<<31;m->r[0x1000/4]&=~(1u<<8);}
 if(off==0x1000) {
  if(v&(1u<<14)){if(m->latch)m->r[off/4]|=1u<<13;}
  else m->r[off/4]&=~(1u<<13);
 }
 return true;
}
static bool wait_pll(void *arg,unsigned off,uint32_t mask,uint32_t v,unsigned us) {
 assert(us==200);return (read_pll(arg,off)&mask)==v;
}
static void barrier(void *arg){(void)arg;}
static void delay(void *arg,unsigned us){(void)arg;assert(us==1);}
static bool power(void *arg,unsigned cx,unsigned mx){assert(cx==128 && mx==192);return ((struct model *)arg)->power;}
static bool unused(void *arg){return (((struct model *)arg)->cfg&0x700)!=0x300;}
static uint32_t root(void *arg){return ((struct model *)arg)->cfg;}
static bool set_root(void *arg,uint32_t v) {
 struct model *m=arg;if(m->busy)return false;
 if(++m->writes==m->fail){m->cfg=(m->cfg&~0x71f)|v;return false;} /* timeout after selector write */
 m->cfg=(m->cfg&~0x71f)|v;return true;
}
static bool reset(void *arg){return ((struct model *)arg)->reset;}
static bool gxoff(void *arg){return ((struct model *)arg)->gxoff;}
int main(void) {
 for(unsigned scenario=0;scenario<90;scenario++) {
  struct model m={.cfg=0x100505,.power=true,.reset=true,.gxoff=true,.lock=true,.latch=true};
  m.r[0x1000/4]=1u<<8;
  uint32_t saved[sizeof(m.r)/sizeof(m.r[0])];memcpy(saved,m.r,sizeof(saved));
  struct waffle_pll1_io pll={&m,read_pll,write_pll,wait_pll,barrier,delay,power,unused};
  struct waffle_gmu_clock_io io={&pll,&m,root,set_root,reset,gxoff};
  struct waffle_gmu_clock_state state={0};
  if(scenario==1)m.power=false;
  if(scenario==2)m.reset=false;
  if(scenario==3)m.gxoff=false;
  if(scenario==4)m.lock=false;
  if(scenario==5)m.latch=false;
  if(scenario==6)m.cfg=0x100303;
  if(scenario>=10)m.fail=scenario-9;
  bool started=waffle_gmu_clock_start(&io,&state);
  if(started) {
   assert(state.active && state.pll.owned && m.cfg==0x100303);
   assert(m.r[0x1010/4]==0x44440041 && m.r[0x1014/4]==0x1aaa);
   assert(!waffle_gmu_clock_start(&io,&state));
   assert(!waffle_gmu_clock_runtime(&io,&state)); /* CM3 must run first */
   m.reset=false;
   bool low=waffle_gmu_clock_runtime(&io,&state);
   if(low) {
    assert(state.runtime && m.r[0x1010/4]==0x4444001b && m.r[0x1014/4]==0x1555);
    assert(!waffle_gmu_clock_runtime(&io,&state));
   }
   unsigned before=m.writes;
   m.power=false;
   assert(!waffle_gmu_clock_finish(&io,&state) && m.writes==before && state.pll.owned);
   m.power=true;
   assert(!waffle_gmu_clock_finish(&io,&state) && m.writes==before && state.pll.owned);
   m.reset=true;m.gxoff=false;
   assert(!waffle_gmu_clock_finish(&io,&state) && m.writes==before && state.pll.owned);
   m.gxoff=true;m.busy=true;
   assert(!waffle_gmu_clock_finish(&io,&state) && state.pll.owned);
   m.busy=false;
  }
  if(state.pll.owned || state.active) {
   m.reset=m.gxoff=m.lock=m.latch=m.power=true;m.busy=false;m.fail=0;
   assert(waffle_gmu_clock_finish(&io,&state));
   assert(!state.pll.owned && !state.active && m.cfg==0x100505);
   for(unsigned i=1;i<13;i++){unsigned off=waffle_pll1_offsets[i];assert(m.r[off/4]==saved[off/4]);}
  } else assert(m.writes==0);
 }
 /* Detach write failure must retain ownership; a retry can finish. */
 struct model m={.cfg=0x100505,.power=true,.reset=true,.gxoff=true,.lock=true,.latch=true};
 m.r[0x1000/4]=1u<<8;
 struct waffle_pll1_io pll={&m,read_pll,write_pll,wait_pll,barrier,delay,power,unused};
 struct waffle_gmu_clock_io io={&pll,&m,root,set_root,reset,gxoff};
 struct waffle_gmu_clock_state state={0};assert(waffle_gmu_clock_start(&io,&state));
 m.fail=m.writes+1;assert(!waffle_gmu_clock_finish(&io,&state) && state.pll.owned);
 m.fail=0;assert(waffle_gmu_clock_finish(&io,&state) && !state.pll.owned);
 puts("GMU native clock session:625->260, write/lock/latch/attach failures, live CM3/GX/busy detach retention and complete PLL/root rollback passed");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(root/'kernel/files/bsd'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
