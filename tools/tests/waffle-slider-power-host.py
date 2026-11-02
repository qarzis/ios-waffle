from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_synaptics.c').read_text();a=s.index('static int sensor_power_vote(');b=s.index('static int enable_vdd(',a);actual=s[a:b]
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
static uint32_t regs[0x10000/4];static int stopping,locked,writes,mode,calls;
static uint32_t commands[3],values[3];static int macan_rpmh_lock;
#define NSEC_PER_USEC 1000
static void say(const char *format,...){(void)format;}
static void delay_for_interval(unsigned n,unsigned u){(void)n;(void)u;}
static vm_offset_t ml_io_map(uint64_t a,unsigned size){assert(a==0x17a20000 && size==0x10000);calls++;return (uintptr_t)regs;}
static uint32_t rr(uintptr_t base,unsigned off){return *(uint32_t *)(base+off);}
static void rw(uintptr_t base,unsigned off,uint32_t value){
 assert(locked);writes++;unsigned at=((base-(uintptr_t)regs)+off)/4;regs[at]=value;
 if(at==(0xd00+0x24)/4 && (value&(1u<<24))){
  for(unsigned i=0;i<3;i++){commands[i]=regs[(0xd38+i*24)/4];values[i]=regs[(0xd3c+i*24)/4];regs[(0xd40+i*24)/4]=mode==2?0:0x10100;}
  if(mode!=1)regs[0xd04/4]=1;else regs[0xd28/4]=0;
 }
 if(at==0xd08/4 && value==1)regs[0xd04/4]=0;
}
static void lck_mtx_lock(int *p){assert(p==&macan_rpmh_lock && !locked);locked=1;}
static void lck_mtx_unlock(int *p){assert(p==&macan_rpmh_lock && locked);locked=0;}
static void reset(void){memset(regs,0,sizeof(regs));regs[0]=3<<16;regs[3]=(3<<12)|(3u<<27);regs[0xd28/4]=1;stopping=locked=writes=mode=calls=0;}
'''
t=r'''
int main(void){
 unsigned resource[]={0x41c00,0x40700,0x40f00},mv[]={1800,1800,3000};
 for(unsigned i=0;i<3;i++){
  reset();assert(waffle_sensor_power(resource[i],mv[i]));assert(!locked);
  assert(commands[0]==resource[i] && commands[1]==resource[i]+8 && commands[2]==resource[i]+4);
  assert(values[0]==mv[i] && values[1]==7 && values[2]==1);
  assert(regs[0xd24/4]==0 && regs[0xd20/4]==0 && regs[0xd2c/4]==0);
 }
 reset();assert(!waffle_sensor_power(0x40700,3000) && !writes && !calls);
 assert(!waffle_sensor_power(0x40704,1800) && !writes && !calls);
 reset();regs[0xd28/4]=0;assert(!waffle_sensor_power(0x40700,1800) && !writes && !locked);
 reset();regs[0xd04/4]=1;assert(!waffle_sensor_power(0x40700,1800) && !writes && !locked);
 reset();stopping=1;assert(!waffle_sensor_power(0x40700,1800) && !writes && !locked);
 reset();mode=2;assert(!waffle_sensor_power(0x40700,1800) && !locked);
 reset();mode=1;assert(!waffle_sensor_power(0x40700,1800) && !locked);assert(regs[0xd24/4]&(1u<<24));
 int old=writes;assert(!waffle_sensor_power(0x40f00,3000) && writes==old);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+actual+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual sensor power helper: three whitelisted resource/voltage tuples, shared lock, idle/pending/stopping guards, completion status, trigger cleanup, timeout retention and no reuse of busy TCS: PASS. Mocked RSC only.')
