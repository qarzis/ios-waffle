#!/usr/bin/env python3
"""Actual cold HFI feature order: GMU DMS support is separate from CP DMS mode."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'kernel/files/bsd/dev/waffle_gmu.c').read_text()
code=s[s.index('static bool hfi_boot_acd('):s.index('static bool hfi_start_capture(')]
native=(ROOT/'work/waffle/gpu/vendor/adreno_gen7_hwsched_hfi.c').read_text()
ids=(ROOT/'work/waffle/gpu/vendor/adreno_hfi.h').read_text()
assert '#define HFI_FEATURE_BCL\t\t11' in ids and '#define HFI_FEATURE_IFPC\t9' in ids
import json
captured=json.loads((ROOT/'work/waffle/gpu/android-live-audit-20261026/native-matched-port-first-boot.json').read_text())['packets']
assert any(p['id']==11 and p['words'][1:]==[11,1,1] for p in captured)
dms=native[native.index('static int gen7_hfi_send_dms_feature_ctrl('):native.index('static void gen7_spin_idle_debug_lpac(')]
assert 'HFI_FEATURE_DMS, 1, 0' in dms and 'dms_enabled)' not in dms
cold=native[native.index('int gen7_hwsched_hfi_start('):] if 'int gen7_hwsched_hfi_start(' in native else native[native.index('warmboot_init_message_record_bitmask(adreno_dev);'):]
assert cold.index('gen7_hfi_send_dms_feature_ctrl(adreno_dev)')<cold.index('gen7_hfi_send_core_fw_start(adreno_dev)')
import re
minimal=(ROOT/'work/waffle/gpu/android-live-audit-20261029/minimal-native-20261029T141226Z.trace').read_text()
window=minimal.split('MINIMAL_WINDOW_BEGIN',1)[1].split('MINIMAL_WINDOW_END',1)[0]
assert re.search(r': cp_done:.*ret=0\b',window)
minimal_features=[]
for line in window.splitlines():
 if ': hfi:' not in line or 'bytes=16 id=11 ' not in line:continue
 words={int(i):int(v,16) for i,v in re.findall(r'\bw(\d+)=(0x[0-9a-f]+)',line)}
 minimal_features.append([words[i] for i in (1,2,3)])
assert len(minimal_features)==7 and not any(x[0] in (2,9,10,24) for x in minimal_features)
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "waffle_hfi.h"
typedef uintptr_t vm_offset_t;
static unsigned count,fail_at,stage;
static uint32_t sent[16][69],lengths[16];
static const char *labels[16];
static void say(const char *fmt,...) {(void)fmt;}
static bool hfi_exchange(uintptr_t gmu,uintptr_t alias,const uint32_t *p,unsigned n,const char *name,bool zero_ack) {
 assert(gmu==1 && alias==2 && n<=69 && zero_ack && count<16);
 lengths[count]=n;labels[count]=name;memcpy(sent[count],p,n*4);++count;
 return count!=fail_at;
}
'''
harness+='static const uint32_t native_minimal[][3]={'+','.join('{'+','.join(map(str,row))+'}' for row in minimal_features)+'};\n'
tests=r'''
int main(void) {
 for(stage=40;stage<=44;stage+=2) {
  count=fail_at=0;assert(hfi_boot_features(1,2,stage) && count==9);
  for(unsigned i=0;i<9;++i) assert(sent[i][0]>>20==i+4);
  unsigned core=stage>=42?5:4;
  assert((sent[core][0]&255)==14 && lengths[core]==2);
  assert(sent[0][1]==11 && sent[0][2]==(stage==44) && sent[0][3]==(stage==44));
  assert(!strcmp(labels[0],stage==44?"BCL_ON":"BCL_OFF"));
  if(stage>=42) {
   assert(!strcmp(labels[4],"DMS_CAPABILITY_ON") && sent[4][1]==27 && sent[4][2]==1 && !sent[4][3]);
   for(unsigned i=5;i<9;++i)assert(sent[i][1]!=27); /* No later feature disable. */
  } else assert(!strcmp(labels[7],"DMS_OFF") && sent[7][1]==27 && !sent[7][2]);
  uint32_t packet[11];assert(waffle_hfi_cp_init_packet(packet,11,34,waffle_gpu_global_alias(0x80070000))==11);
  assert(packet[4]==0x94b); /* CP concurrent/DMS mode stays disabled. */
  for(fail_at=1;fail_at<=9;++fail_at) {
   count=0;assert(!hfi_boot_features(1,2,stage) && count==fail_at);
  }
 }
 for(unsigned acd_stage=48;acd_stage<=49;acd_stage++) {
 count=fail_at=0;assert(hfi_boot_features(1,2,acd_stage) && count==11);
 assert(!strcmp(labels[5],"ACD_ON") && sent[5][1]==12 && sent[5][2]==1);
 assert(!strcmp(labels[6],"ACD_TABLE") && lengths[6]==69);
 assert(!strcmp(labels[7],"CORE_FW_START"));
 for(unsigned i=0;i<count;i++)for(unsigned j=i+1;j<count;j++)assert((sent[i][0]>>20)!=(sent[j][0]>>20));
 for(fail_at=1;fail_at<=11;fail_at++){count=0;assert(!hfi_boot_features(1,2,acd_stage) && count==fail_at);}
 }
 for(unsigned bail_stage=50;bail_stage<=51;bail_stage++){
 count=fail_at=0; assert(hfi_boot_features(1,2,bail_stage) && count==12);
 assert(!strcmp(labels[7],"BAILOUT_TIMER_ON") && sent[7][1]==17 && sent[7][2]==1 && sent[7][3]==0);
 assert(!strcmp(labels[8],"CORE_FW_START"));
 for(fail_at=1;fail_at<=12;fail_at++){count=0;assert(!hfi_boot_features(1,2,bail_stage) && count==fail_at);}
 }
 for(unsigned native_stage=63;native_stage<=64;native_stage++) {
 count=fail_at=0;assert(hfi_boot_features(1,2,native_stage) && count==9);
 unsigned features=0;
 for(unsigned i=0;i<count;i++) {
  for(unsigned j=i+1;j<count;j++)assert((sent[i][0]>>20)!=(sent[j][0]>>20));
  if((sent[i][0]&255)!=11)continue;
  assert(lengths[i]==4 && sent[i][1]!=2 && sent[i][1]!=9 && sent[i][1]!=10 && sent[i][1]!=24);
  bool found=false;
  for(unsigned j=0;j<7;j++)if(!memcmp(&sent[i][1],native_minimal[j],12))found=true;
  assert(found);features++;
 }
 assert(features==7 && !strcmp(labels[7],"CORE_FW_START") && !strcmp(labels[8],"AQE_ON"));
 for(fail_at=1;fail_at<=9;fail_at++){count=0;assert(!hfi_boot_features(1,2,native_stage) && count==fail_at);}
 }
 for(unsigned order_stage=65;order_stage<=66;order_stage++) {
 count=fail_at=0;assert(hfi_boot_features(1,2,order_stage) && count==9);
 unsigned feature_index=0;
 for(unsigned i=0;i<count;i++) {
  for(unsigned j=i+1;j<count;j++)assert((sent[i][0]>>20)!=(sent[j][0]>>20));
  if((sent[i][0]&255)==11) {
   assert(feature_index<7 && !memcmp(&sent[i][1],native_minimal[feature_index],12));feature_index++;
  }
 }
 assert(feature_index==7 && !strcmp(labels[0],"ACD_ON") && !strcmp(labels[1],"ACD_TABLE"));
 assert(lengths[1]==69 && !strcmp(labels[2],"BCL_ON") && !strcmp(labels[7],"CORE_FW_START"));
 for(fail_at=1;fail_at<=9;fail_at++){count=0;assert(!hfi_boot_features(1,2,order_stage) && count==fail_at);}
 }
 for(unsigned event_stage=69;event_stage<=70;event_stage++){
 count=fail_at=0;assert(hfi_boot_features(1,2,event_stage) && count==10);
 assert(!strcmp(labels[2],"ACD_LOG_EVENT_ON") && lengths[2]==4);
 assert((sent[2][0]&255)==13 && (sent[2][0]>>20)==39);
 assert(sent[2][1]==112 && sent[2][2]==44 && sent[2][3]==0);
 assert(!strcmp(labels[1],"ACD_TABLE") && !strcmp(labels[3],"BCL_ON"));
 for(unsigned i=0;i<count;i++)for(unsigned j=i+1;j<count;j++)assert((sent[i][0]>>20)!=(sent[j][0]>>20));
 for(fail_at=1;fail_at<=10;fail_at++){count=0;assert(!hfi_boot_features(1,2,event_stage) && count==fail_at);}
 }
 puts("Actual HFI features: native DMS capability before CORE, CP DMS-disabled payload, unique ordered sequences and every ACK failure stop passed");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(harness+code+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
