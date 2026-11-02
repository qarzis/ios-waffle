#!/usr/bin/env python3
"""Reproduce A11 credit loss and exercise the actual GLINK sender after admission."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/macan_adsp.c').read_text()
types=s[s.index('#define GLINK_RESERVE'):s.index('static LCK_MTX_DECLARE(glink_lock')]
sender=s[s.index('static int\nglink_send('):s.index('#define QRTR_US')]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "waffle_glink_intent.h"
#include "waffle_apm.h"
'''
stubs=r'''
static struct { bool up,broken;uint32_t ours_size; } glink;
static bool stopping;
static int glink_lock,locked;
static unsigned requests,sends,selected,slept;
static struct glink_channel *active;
static void lck_mtx_lock(int *p) { assert(p==&glink_lock && !locked);locked=1; }
static void lck_mtx_unlock(int *p) { assert(p==&glink_lock && locked);locked=0; }
static void glink_pump(void) { assert(locked); }
static uint32_t glink_room(void) { return 16368; }
static void sleep_ms(unsigned ms) { assert(!locked);slept+=ms; }
static bool glink_say(uint16_t command,uint16_t channel,uint32_t size,const void *data,unsigned bytes) {
 assert(locked && command==GLINK_INTENT_REQUEST && channel==active->ours && size==344 && !data && !bytes);
 requests++;active->request_answered=true;active->request_granted=true;return true;
}
static bool glink_put(const void *header,unsigned hsize,const void *data,unsigned size) {
 const struct glink_message *m=header;
 assert(locked && hsize==16 && m->command==GLINK_DATA && m->param1==active->ours && data && size==344);
 selected=m->param2;sends++;return true;
}
static void reset(struct glink_channel *channel) {
 memset(channel,0,sizeof(*channel));strcpy(channel->name,"adsp_apps");channel->ours=2;channel->open=true;
 active=channel;glink.up=true;glink.broken=false;glink.ours_size=16384;stopping=false;
 requests=sends=selected=slept=0;
}
'''
cases=r'''
int main(void) {
 struct glink_channel channel;
 uint32_t packet[128],old_size;
 assert(waffle_apm_packet(packet,sizeof(packet),WAFFLE_APM_GRAPH_OPEN,2)==344);
 reset(&channel);
 for(unsigned i=0;i<64;i++) assert(waffle_glink_intent_admit(channel.their_intents,64,i,128,&old_size)==(int)i && !old_size);
 /* A11 snapshot: only the64 small advertisements survived the old receiver. */
 assert(glink_send(&channel,packet,344)==ENOBUFS && !sends && requests==1 && slept==5000 && !locked);
 requests=sends=slept=0;
 unsigned sizes[]={512,1024,4096};
 for(unsigned i=0;i<3;i++) {
  int slot=waffle_glink_intent_admit(channel.their_intents,64,64+i,sizes[i],&old_size);
  assert(slot>=0 && old_size==128);
 }
 assert(glink_send(&channel,packet,344)==0 && sends==1 && !requests && selected==64 && !locked);
 unsigned entries=0;
 for(unsigned i=0;i<64;i++) entries+=channel.their_intents[i].there;
 assert(entries==64 && channel.their_intents[0].in_use);
 int duplicate=waffle_glink_intent_admit(channel.their_intents,64,64,512,&old_size);
 assert(duplicate==0 && channel.their_intents[0].in_use && !old_size);
 struct waffle_glink_remote_intent saved[64];memcpy(saved,channel.their_intents,sizeof(saved));
 assert(waffle_glink_intent_admit(channel.their_intents,64,64,1024,&old_size)<0 && !memcmp(saved,channel.their_intents,sizeof(saved)));
 for(unsigned i=0;i<64;i++) channel.their_intents[i].in_use=true;
 memcpy(saved,channel.their_intents,sizeof(saved));
 assert(waffle_glink_intent_admit(channel.their_intents,64,99,8192,&old_size)<0 && !memcmp(saved,channel.their_intents,sizeof(saved)));
 reset(&channel);channel.their_intents[30]=(struct waffle_glink_remote_intent){7,128,true,true};
 assert(waffle_glink_intent_admit(channel.their_intents,64,7,128,&old_size)==30 && channel.their_intents[30].in_use && !channel.their_intents[0].there);
 assert(waffle_glink_intent_admit(NULL,64,1,128,&old_size)<0);
 assert(waffle_glink_intent_admit(channel.their_intents,65,1,128,&old_size)<0);
 assert(waffle_glink_intent_admit(channel.their_intents,64,1,0,&old_size)<0);
 puts("PASS: actual GLINK sender reproduces A11 ENOBUFS with64 small credits; unchanged344-byte packet sends through admitted512-byte credit without request or table growth; in-flight IDs, duplicates and full-busy refusal preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='waffle-glink-intent-') as temp:
    p=Path(temp)
    (p/'test.c').write_text(prefix+types+stubs+sender+cases)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
