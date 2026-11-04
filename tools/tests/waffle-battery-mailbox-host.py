#!/usr/bin/env python3
"""Actual ADSP battery mailbox: reply identity, deadlines, teardown and lock order."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/macan_adsp.c').read_text()

def function(name):
    start = source.index('static ' + ('void' if name.endswith('input') else 'bool') + '\n' + name + '(')
    at = source.index('{', start)
    end, depth = at + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'

code = r'''
#include <assert.h>
#include <sys/waffle_battery_readonly.h>
static int battery_reply_lock;
static bool locked,stopping,link_failed;
static unsigned sleeps,mode;
static struct {bool pending,ready;uint32_t opcode,property,value;} battery_reply;
struct glink_channel {unsigned unused;};
static void battery_probe_input(const uint8_t*,uint32_t);
static void lck_mtx_lock(int*){assert(!locked);locked=true;}
static void lck_mtx_unlock(int*){assert(locked);locked=false;}
static void send_reply(uint32_t op,uint32_t prop,uint32_t val){
 uint8_t b[24]={0};waffle_battery_put(b,32778);waffle_battery_put(b+4,1);
 waffle_battery_put(b+8,op);waffle_battery_put(b+12,prop);waffle_battery_put(b+16,val);
 battery_probe_input(b,24);
}
static int glink_send(struct glink_channel*,const void *data,uint32_t n){
 assert(!locked && battery_reply.pending && n==24);
 const uint8_t *b=(const uint8_t*)data;
 assert(waffle_battery_u32(b)==32778 && waffle_battery_u32(b+4)==1);
 assert(waffle_battery_u32(b+12)==0 && waffle_battery_u32(b+20)==0);
 if(mode==1)send_reply(battery_reply.opcode,battery_reply.property,9600);
 if(mode==2)return 1;
 if(mode==4)send_reply(battery_reply.opcode,battery_reply.property,10001);
 if(mode==5)send_reply(0x30,2,1); // late response from a different property
 return 0;
}
static void sleep_ms(unsigned n){
 assert(!locked && n==1);sleeps++;
 if(mode==3 && sleeps==2)send_reply(battery_reply.opcode,battery_reply.property,9600);
 if(mode==6)stopping=true;
 if(mode==7 && sleeps==1000)send_reply(battery_reply.opcode,battery_reply.property,9600);
 if(mode==8){send_reply(battery_reply.opcode,battery_reply.property,9600);stopping=true;}
}
''' + function('battery_probe_input') + function('battery_probe_get') + r'''
static void reset(unsigned m){mode=m;sleeps=0;locked=stopping=link_failed=false;battery_reply={};}
int main(){
 glink_channel channel{};uint32_t v=0;
 reset(1);assert(battery_probe_get(&channel,0x30,4,&v)&&v==9600&&!sleeps&&!locked&&!battery_reply.pending);
 reset(2);assert(!battery_probe_get(&channel,0x30,4,&v)&&!sleeps&&!locked&&!battery_reply.pending);
 reset(3);assert(battery_probe_get(&channel,0x30,4,&v)&&v==9600&&sleeps==2&&!locked&&!battery_reply.pending);
 reset(0);assert(!battery_probe_get(&channel,0x30,4,&v)&&sleeps==1000&&!locked&&!battery_reply.pending);
 send_reply(0x30,4,9600);assert(!battery_reply.ready); // disarmed timeout
 reset(4);assert(!battery_probe_get(&channel,0x30,4,&v)&&!battery_reply.pending); // impossible SOC
 reset(5);assert(!battery_probe_get(&channel,0x30,4,&v)&&sleeps==1000&&!battery_reply.pending);
 reset(6);assert(!battery_probe_get(&channel,0x30,4,&v)&&sleeps==1&&!locked&&!battery_reply.pending);
 reset(7);assert(battery_probe_get(&channel,0x30,4,&v)&&sleeps==1000&&v==9600&&!locked&&!battery_reply.pending);
 reset(8);assert(!battery_probe_get(&channel,0x30,4,&v)&&sleeps==1&&!locked&&!battery_reply.pending);
 reset(0);assert(!battery_probe_get(&channel,0x31,4,&v)&&!sleeps&&!battery_reply.pending);
 reset(0);battery_reply.pending=true;battery_reply.opcode=0x30;battery_reply.property=4;
 uint8_t b[24]={0};battery_probe_input(b,24);battery_probe_input(b,0);assert(!battery_reply.ready);
}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / 'mailbox.cpp'
    binary = Path(directory) / 'mailbox'
    cpp.write_text(code)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I', str(root / 'kernel/files/bsd'),
                    str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('PASS actual battery mailbox: immediate/delayed replies, send failure, bounded timeout, late/wrong replies, invalid SOC, teardown and no lock held during transport/sleep')
