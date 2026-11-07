#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_audio_cb_config.h"
static struct {uint32_t reg[1024];unsigned reads,writes,fail_read,fail_write;bool ambiguous,deny;} b;
static uint32_t saved[1024];
static bool read32(void *c,uint32_t a,uint32_t *v){(void)c;assert(a>=0x86000&&a<0x87000&&!(a&3));if(++b.reads==b.fail_read)return false;*v=b.reg[(a-0x86000)/4];return true;}
static bool write32(void *c,uint32_t a,uint32_t v){(void)c;bool allowed=false;for(unsigned i=0;i<8;i++)allowed|=a==0x86000+waffle_audio_cb_config_offset(i);assert(allowed);bool fail=++b.writes==b.fail_write;if(!b.deny&&(!fail||b.ambiguous))b.reg[(a-0x86000)/4]=v;return !fail;}
static void reset(void){memset(&b,0,sizeof(b));for(unsigned i=0;i<1024;i++)b.reg[i]=0x13570000+i;b.reg[0]=0x100;memcpy(saved,b.reg,sizeof(saved));}
int main(void){const struct waffle_audio_cb_access_io io={{0,read32},write32,true};struct waffle_audio_cb_access_result access={.passed=true,.restored=true,.bank=6,.offset=0x86000,.original=0x100};struct waffle_audio_cb_config_result r;reset();assert(waffle_audio_cb_config(&io,&access,0x910000000,&r)&&r.configured&&r.restored&&r.read_mask==255&&!r.mismatch_mask&&r.writes==16&&!memcmp(saved,b.reg,sizeof(saved)));unsigned reads=b.reads;
for(unsigned n=1;n<=reads;n++){reset();b.fail_read=n;assert(!waffle_audio_cb_config(&io,&access,0x910000000,&r));assert(!memcmp(saved,b.reg,sizeof(saved)));}
for(unsigned n=1;n<=16;n++)for(unsigned uncertain=0;uncertain<2;uncertain++){reset();b.fail_write=n;b.ambiguous=uncertain;assert(!waffle_audio_cb_config(&io,&access,0x910000000,&r));if(n<=8)assert(r.restored&&!memcmp(saved,b.reg,sizeof(saved)));}
reset();b.deny=true;assert(!waffle_audio_cb_config(&io,&access,0x910000000,&r)&&!r.configured&&r.restored&&r.read_mask==255&&r.mismatch_mask);
reset();access.passed=false;assert(!waffle_audio_cb_config(&io,&access,0x910000000,&r)&&!b.reads&&!b.writes);
printf("PASS disabled audio table profile:%u read failures/32 ambiguous write failures,reverse restore,denied readback rejected,M0unchanged; no stream/global/TLB/DSP. Mock only.\n",reads);}
