#!/usr/bin/env python3
"""Execute pinned native PLL1 configure/rate/prepare code without hardware.

Compare the isolated port sequence with the native reference and exercise
rollback. Neither implementation supplies or restores APSS regulator votes.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'work/waffle/gpu/vendor'
source = (VENDOR / 'clk-alpha-pll.c').read_text()
header = (VENDOR / 'clk-alpha-pll.h').read_text()
gpucc = (VENDOR / 'gpucc-pineapple.c').read_text()


def function(name):
    match = re.search(r'\n(?:static )?(?:unsigned long\n|int |void )' + name + r'\(', source)
    assert match, name
    start = match.start() + 1
    opening = source.index('{', match.end())
    depth = 1
    pos = opening + 1
    while depth:
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    return source[start:pos] + '\n'


assert '#define clk_alpha_pll_lucid_ole_ops clk_alpha_pll_lucid_evo_ops' in header
assert 'clk_lucid_evo_pll_configure(pll, regmap, config)' in header
assert 'F(625000000, P_GPU_CC_PLL1_OUT_MAIN, 2, 0, 0)' in gpucc
offset_block = re.search(r'\[CLK_ALPHA_PLL_TYPE_LUCID_OLE\] = \{(.*?)\n\t\}', source, re.S)[1]
offsets = dict((name, int(value, 16)) for name, value in re.findall(r'\[PLL_OFF_(\w+)\] = (0x\w+)', offset_block))
defines = '\n'.join(f'#define PLL_{name}(p) ((p)->offset+{value})' for name, value in offsets.items())
defines += '\n#define PLL_MODE(p) ((p)->offset)\n#define PLL_CAL_L_VAL(p) ((p)->offset)\n'
for name in ('PLL_OUTCTRL', 'PLL_RESET_N', 'PLL_LOCK_DET', 'PLL_STANDBY', 'PLL_RUN',
             'PLL_OUT_MASK', 'PLL_RATE_MARGIN', 'LUCID_EVO_ENABLE_VOTE_RUN',
             'LUCID_EVO_PLL_L_VAL_MASK', 'LUCID_EVO_PLL_CAL_L_VAL_MASK',
             'LUCID_EVO_PLL_CAL_L_VAL_SHIFT', 'LUCID_OLE_PROCESS_CAL_L_VAL_MASK',
             'LUCID_OLE_PROCESS_CAL_L_VAL_SHIFT', 'LUCID_OLE_RINGOSC_CAL_L_VAL_MASK',
             'LUCID_OLE_RINGOSC_CAL_L_VAL_SHIFT', 'LUCID_EVO_PCAL_NOT_DONE',
             'LUCID_5LPE_PLL_LATCH_INPUT', 'LUCID_5LPE_ALPHA_PLL_ACK_LATCH'):
    match = re.search(r'^#\s*define\s+' + name + r'\s+([^\n]+)', source, re.M)
    assert match, name
    defines += '#define ' + name + ' ' + match[1] + '\n'

config = re.search(r'static const struct alpha_pll_config gpu_cc_pll1_config = \{.*?\n\};', gpucc, re.S)[0]
functions = ''.join(function(name) for name in ('alpha_pll_calc_rate', 'alpha_pll_round_rate',
    'trion_pll_is_enabled', 'clk_lucid_evo_pll_configure', '_alpha_pll_lucid_evo_enable',
    '_alpha_pll_lucid_evo_disable', '_alpha_pll_lucid_evo_prepare', 'alpha_pll_lucid_evo_set_rate'))

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1u<<(n))
#define GENMASK(h,l) ((0xffffffffu>>(31-(h))) & (0xffffffffu<<(l)))
#define min(a,b) ((a)<(b)?(a):(b))
#define roundup(a,b) ((((a)+(b)-1)/(b))*(b))
#define ALPHA_SHIFT(w) min(w,32u)
#define ALPHA_REG_16BIT_WIDTH 16
#define do_div(a,b) ({u64 rem=(a)%(b);(a)/=(b);rem;})
#define TRION_PLL_CAL_VAL 0x44
#define ENABLE_IN_PREPARE 1
#define DISABLE_TO_OFF 2
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define WARN_CLK(...) ((void)0)
static unsigned barriers, delays, preparations, lock_waits;
static bool no_lock, no_latch, emit;
static unsigned cx_level,mx_level;
struct alpha_pll_config {
 u32 l,cal_l,cal_l_ringosc,alpha,config_ctl_val,config_ctl_hi_val,config_ctl_hi1_val;
 u32 user_ctl_val,user_ctl_hi_val,test_ctl_val,test_ctl_hi_val,test_ctl_hi1_val,test_ctl_hi2_val;
};
struct regmap {u32 values[0x1100/4];};
struct clk_alpha_pll;
struct clk_hw {struct clk_alpha_pll *owner;};
struct clk_alpha_pll {
 unsigned offset,flags;const struct alpha_pll_config *config;
 struct {struct regmap *regmap;struct clk_hw hw;} clkr;
};
#define to_clk_alpha_pll(hw) ((hw)->owner)
static void wmb(void) {++barriers;}
static void mb(void) {++barriers;}
static void udelay(unsigned n) {assert(n==1);++delays;}
static int regmap_read(struct regmap *r,unsigned off,u32 *out) {
 assert(off>=0x1000 && off<=0x1038 && !(off&3));*out=r->values[off/4];return 0;
}
static int regmap_write(struct regmap *r,unsigned off,u32 value) {
 assert(cx_level>=128 && mx_level>=192);
 assert(off>=0x1000 && off<=0x1038 && !(off&3));
 if(emit)printf("WRITE %04x %08x\n",off,value);
 r->values[off/4]=value;
 if(off==0x1004 && value==1 && !no_lock) {
  r->values[0x1000/4]|=1u<<31;r->values[0x1000/4]&=~(1u<<8);
 }
 if(off==0x1000) {
  if(value&(1u<<14)) {if(!no_latch)r->values[off/4]|=1u<<13;}
  else r->values[off/4]&=~(1u<<13);
 }
 return 0;
}
static int regmap_update_bits(struct regmap *r,unsigned off,u32 mask,u32 value) {
 u32 old;regmap_read(r,off,&old);u32 next=(old&~mask)|(value&mask);
 return old==next?0:regmap_write(r,off,next);
}
static int clk_enable_regmap(struct clk_hw *hw) {(void)hw;assert(0);return -EINVAL;}
static void clk_disable_regmap(struct clk_hw *hw) {(void)hw;assert(0);}
static int clk_prepare_regmap(struct clk_hw *hw) {
 assert(hw && cx_level>=128 && mx_level>=192);++preparations;return 0;
}
static struct clk_hw *clk_hw_get_parent(struct clk_hw *hw) {return hw;}
static unsigned long clk_hw_get_rate(struct clk_hw *hw) {assert(hw);return 19200000;}
static bool clk_hw_is_enabled(struct clk_hw *hw) {
 struct regmap *r=hw->owner->clkr.regmap;
 return r->values[0x1004/4]==1 && (r->values[0x1000/4]&1);
}
static int wait_for_pll_enable_lock(struct clk_alpha_pll *p) {
 ++lock_waits;return (p->clkr.regmap->values[0x1000/4]&(1u<<31))?0:-ETIMEDOUT;
}
'''
port = r'''
#include "waffle_gpu_pll.h"
static bool detached,powered;
static unsigned write_attempts,fail_write;
static uint32_t port_read(void *context,unsigned offset) {
 u32 value;regmap_read(context,offset,&value);return value;
}
static bool port_write(void *context,unsigned offset,uint32_t value) {
 if(++write_attempts==fail_write)return false;
 return regmap_write(context,offset,value)==0;
}
static bool port_wait(void *context,unsigned offset,uint32_t mask,uint32_t value,unsigned us) {
 assert(offset==0x1000 && mask==(1u<<31) && value==mask && us==200);
 return (port_read(context,offset)&mask)==value;
}
static void port_barrier(void *context) {(void)context;mb();}
static void port_delay(void *context,unsigned us) {(void)context;udelay(us);}
static bool port_power(void *context,unsigned cx,unsigned mx) {
 (void)context;assert(cx==128 && mx==192);return powered && cx_level>=cx && mx_level>=mx;
}
static bool port_unused(void *context) {(void)context;return detached;}
static void run_port(void) {
 for(unsigned scenario=0;scenario<70;scenario++) {
  struct regmap r={0};struct waffle_pll1_state state={0};
  struct waffle_pll1_io io={&r,port_read,port_write,port_wait,port_barrier,port_delay,port_power,port_unused};
  r.values[0x1000/4]=1u<<8;
  struct regmap saved=r;
  powered=detached=true;cx_level=128;mx_level=192;
  no_lock=scenario==1;no_latch=scenario==2;emit=scenario==0;
  write_attempts=0;fail_write=scenario>=10?scenario-9:0;
  if(scenario==3)powered=false;
  if(scenario==4)detached=false;
  if(scenario==5)r.values[0x1010/4]=0x1b;
  if(scenario==6)r.values[0x1004/4]=1;
  if(scenario==7)r.values[0x1018/4]=1u<<25;
  if(scenario==8)r.values[0x1000/4]|=1;
  if(scenario==9)r.values[0x1000/4]|=1u<<14;
  bool ok=waffle_pll1_begin(&io,&state);
  if(scenario>=3 && scenario<=9) {
   assert(!ok && !state.owned && write_attempts==0);continue;
  }
  if(ok) {
   assert(!waffle_pll1_begin(&io,&state));
   assert(r.values[0x1010/4]==0x44440041 && r.values[0x1014/4]==0x1aaa);
   assert(!waffle_pll1_rate(&io,&state,600000000));
   ok=waffle_pll1_rate(&io,&state,520000000);
   if(ok)ok=waffle_pll1_standby(&io);
  }
  if(scenario==0) {assert(ok);puts("PORT_PLL1_NORMAL_PASS");}
  if(scenario==1 || scenario==2)assert(!ok && state.owned);
  /* A failed or live session cannot silently release power or forget ownership. */
  powered=false;assert(!waffle_pll1_restore(&io,&state) && state.owned);
  powered=true;detached=false;assert(!waffle_pll1_restore(&io,&state) && state.owned);
  detached=true;fail_write=0;no_lock=no_latch=false;emit=false;
  assert(waffle_pll1_restore(&io,&state) && !state.owned);
  for(unsigned i=1;i<13;i++) {
   unsigned off=waffle_pll1_offsets[i];assert(r.values[off/4]==saved.values[off/4]);
  }
  assert((r.values[0x1000/4]&(1|4|(1u<<14)))==(saved.values[0x1000/4]&(1|4|(1u<<14))));
  assert(waffle_pll1_restore(&io,&state));
 }
 for(unsigned failure=1;failure<=20;failure++) {
  struct regmap r={0};struct waffle_pll1_state state={0};
  struct waffle_pll1_io io={&r,port_read,port_write,port_wait,port_barrier,port_delay,port_power,port_unused};
  /* Match the nonzero inactive firmware configuration measured by PLL87. */
  r.values[0x1000/4]=1u<<8;r.values[0x1018/4]=1;r.values[0x101c/4]=0x805;
  r.values[0x1020/4]=0x20485699;r.values[0x1024/4]=0x182261;r.values[0x1028/4]=0x82aa299c;
  r.values[0x1034/4]=0x8000;r.values[0x1038/4]=0x32;
  struct regmap saved=r;
  powered=detached=true;no_lock=no_latch=emit=false;write_attempts=fail_write=0;
  assert(waffle_pll1_begin(&io,&state));
  write_attempts=0;fail_write=failure;
  bool restored=waffle_pll1_restore(&io,&state);
  if(!restored)assert(state.owned && powered);
  else assert(!state.owned);
  fail_write=0;assert(waffle_pll1_restore(&io,&state));
  for(unsigned i=1;i<13;i++)assert(r.values[waffle_pll1_offsets[i]/4]==saved.values[waffle_pll1_offsets[i]/4]);
 }
 puts("Port PLL1 guards, every write failure, lock/latch errors and powered/detached rollback passed");
}
'''
tests = r'''
int main(void) {
 for(unsigned scenario=0;scenario<3;scenario++) {
  struct regmap r={0};
  struct clk_alpha_pll p={.offset=0x1000,.config=&gpu_cc_pll1_config,.clkr={.regmap=&r}};
  p.clkr.hw.owner=&p;
  no_lock=scenario==1;no_latch=scenario==2;emit=scenario==0;
  cx_level=128;mx_level=192;barriers=delays=preparations=lock_waits=0;
  r.values[0x1000/4]=1u<<8;
  assert(clk_lucid_evo_pll_configure(&p,&r,&gpu_cc_pll1_config)==0);
  assert(r.values[0x1010/4]==0x4444001b && r.values[0x1014/4]==0x1555);
  assert(r.values[0x1030/4]==3 && r.values[0x1034/4]==0x9000 && r.values[0x1038/4]==0x34);
  assert(r.values[0x1004/4]==0 && !(r.values[0x1000/4]&1));
  int result=alpha_pll_lucid_evo_set_rate(&p.clkr.hw,1250000000,19200000);
  if(no_latch) {assert(result==-EINVAL && cx_level==128 && mx_level==192);continue;}
  assert(result==0 && r.values[0x1010/4]==0x44440041 && r.values[0x1014/4]==0x1aaa);
  result=_alpha_pll_lucid_evo_prepare(&p.clkr.hw,false);
  assert(preparations==1 && lock_waits==1);
  if(no_lock) {assert(result==-ETIMEDOUT && cx_level==128 && mx_level==192);continue;}
  assert(result==0 && r.values[0x1004/4]==0 && !(r.values[0x1000/4]&1));
  assert(_alpha_pll_lucid_evo_enable(&p.clkr.hw)==0);
  assert(clk_hw_is_enabled(&p.clkr.hw));
  assert(alpha_pll_lucid_evo_set_rate(&p.clkr.hw,520000000,19200000)==0);
  assert(r.values[0x1010/4]==0x4444001b && r.values[0x1014/4]==0x1555);
  _alpha_pll_lucid_evo_disable(&p.clkr.hw,false);
  assert(!clk_hw_is_enabled(&p.clkr.hw));
  puts("NATIVE_PLL1_NORMAL_PASS");
 }
 puts("Native PLL1 configure,1250MHz/calibration/enable,520MHz/disable; latch and lock errors passed");
 run_port();
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + defines + config + functions + port + tests)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g', '-I', str(ROOT/'kernel/files/bsd/sys'),str(path / 'test.c'),
                    '-o', str(path / 'test')], check=True)
    result = subprocess.run([str(path / 'test')], capture_output=True, text=True, check=True)
native_output,port_output=result.stdout.split('NATIVE_PLL1_NORMAL_PASS\n',1)
native_writes=[line for line in native_output.splitlines() if line.startswith('WRITE ')]
port_writes=[line for line in port_output.split('PORT_PLL1_NORMAL_PASS',1)[0].splitlines() if line.startswith('WRITE ')]
assert native_writes==port_writes, (native_writes,port_writes)
print(result.stdout, end='')
print('Port sequence matches native configure/1250/calibration/enable/520/standby writes')
report = {'native_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
          'native_gpucc_sha256': hashlib.sha256(gpucc.encode()).hexdigest(),
          'offsets': offsets, 'normal_writes': native_writes,
          'passed': True, 'hardware_tested': False,
          'port_matches_native': True,
          'limits': 'Host sequence oracle only; actual hardware results are recorded separately. Firmware supplies must remain held for every live caller.'}
(ROOT / 'work/waffle/gpu/native-pll1-sequence-audit.json').write_text(json.dumps(report, indent=2) + '\n')
