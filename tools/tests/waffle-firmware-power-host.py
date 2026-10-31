#!/usr/bin/env python3
"""Check extracted PJD110 firmware slots and read-only loader query behavior."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
vendor=root/'work/waffle/gpu/vendor'
reference=(vendor/'uefi-reference-Protocol-EFINpa.h').read_text()
block=reference.split('typedef struct _EFI_NPA_PROTOCOL {',1)[1].split('}EFI_NPA_PROTOCOL;',1)[0]
members=re.findall(r'^\s*(?:UINT64|EFI_\w+)\s+(\w+)\s*;',block,re.M)
assert members.index('QueryByName')==22 and members.index('Query')==21
assert members.index('CreateSyncClientEx')==2 and members.index('ScalarRequest')==5
audit={}
for name,offset,revision,slot,target,guid in (
 ('NpaDxe',0x110b8,0x10003,22,0x16ac,(0x79d6c870,0x725e,0x489e,bytes.fromhex('a0a127e7a5d0cb35'))),
 ('ClockDxe',0x20108,0x1000a,7,0x1668,(0x241afae6,0x885f,0x4f6c,bytes.fromhex('a7eac28eab79c3e5')))):
    p=root/'work/waffle/mu/Binaries/waffle/QcomPkg/Drivers'/name/(name+'.efi')
    data=p.read_bytes()
    assert data[:2]==b'MZ'
    assert struct.unpack_from('<Q',data,offset)[0]==revision
    assert struct.unpack_from('<Q',data,offset+slot*8)[0]==target
    assert struct.pack('<IHH8s',*guid) in data
    # QueryByName stores a32-bit status through x3; clock getter retains x2.
    if name=='NpaDxe':
        assert struct.unpack_from('<Q',data,offset+2*8)[0]==0x1440
        assert struct.unpack_from('<Q',data,offset+5*8)[0]==0x149c
        assert struct.pack('<I',0xaa0503f3) in data[0x1440:0x1460]
        assert struct.pack('<I',0xaa0303f3) in data[target:target+32]
        assert struct.pack('<I',0xb9000268) in data[target:target+44]
    audit[name]={'file':str(p.relative_to(root)),'sha256':hashlib.sha256(data).hexdigest(),
                 'revision':revision,'table_offset':offset,'read_slot':slot,'read_function_rva':target}

harness=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle-power.h"
static unsigned mode,npa_calls,clock_ids,clock_reads,hold_mode,created,requested;
static bool holding;
static struct waffle_npa_protocol npa;
static struct waffle_clock_protocol clock;
static void log_line(const char *format,...) {(void)format;}
static efi_status locate(const efi_guid *guid,void *registration,void **out) {
 assert(!registration);
 if(guid->a==0x79d6c870) {*out=mode==1?NULL:&npa;return mode==1?EFI_ERROR_BIT:0;}
 assert(guid->a==0x241afae6);*out=mode==2?NULL:&clock;return mode==2?EFI_ERROR_BIT:0;
}
static efi_status query(const char *name,uint32_t id,struct waffle_npa_query_result *result,uint32_t *status) {
 assert(npa.revision==0x10003 && id<3);
 assert(!strcmp(name,"/vcs/vdd_cx") || !strcmp(name,"/vcs/vdd_mx") || !strcmp(name,"/vcs/vdd_mxc"));
 npa_calls++;
 if(holding) {
  result->type=0;result->data=id?480:256;*status=0;
  if(hold_mode==8 && npa_calls>6)result->data=192;
  if(hold_mode==9 && npa_calls>6)*status=2;
  if(hold_mode==10)result->data=192;
  return 0;
 }
 result->type=mode==7?1:0;result->data=128;
 *status=mode==6?2:0;return mode==5?EFI_ERROR_BIT:0;
}
static efi_status create(const char *resource,const char *name,uint32_t type,uint32_t value,void *reference,void **out) {
 assert(holding && type==64 && !value && !reference);
 assert(!strcmp(resource,created?"/vcs/vdd_mx":"/vcs/vdd_cx"));
 assert(!strcmp(name,created?"waffle-pll1-mx":"waffle-pll1-cx"));
 created++;*out=(hold_mode==3 || (hold_mode==4 && created==2))?NULL:(void *)(uintptr_t)(0x1000+created*256);
 return hold_mode==5?EFI_ERROR_BIT:0;
}
static efi_status request(void *client,uint32_t level) {
 assert(holding && client && level==256);requested++;
 return (hold_mode==6 || (hold_mode==7 && requested==2))?EFI_ERROR_BIT:0;
}
static efi_status get_id(void *self,const char *name,uintptr_t *id) {
 assert(self==&clock && clock.version==0x1000a);assert(!strncmp(name,"gpu_cc_",7));
 clock_ids++;*id=0x100000000ull+clock_ids;return mode==8?EFI_ERROR_BIT:0;
}
static efi_status get_frequency(void *self,uintptr_t id,uint32_t *hz) {
 assert(self==&clock && id>0xffffffffu);clock_reads++;*hz=0;
 return mode==9?EFI_ERROR_BIT:0;
}
int main(void) {
 efi_boot_services bs={0};bs.locate_protocol=locate;
 for(mode=0;mode<10;mode++) {
  memset(&npa,0,sizeof(npa));memset(&clock,0,sizeof(clock));
  npa.revision=mode==3?0x10002:0x10003;npa.query_by_name=query;
  clock.version=mode==4?0x10009:0x1000a;clock.get_id=get_id;clock.get_frequency=get_frequency;
  npa_calls=clock_ids=clock_reads=0;
  assert(waffle_firmware_power_audit(&bs,log_line)==(mode==0));
  assert(npa_calls==((mode==1 || mode==3)?0:9));
  assert(clock_ids==((mode==2 || mode==4)?0:3));
  assert(clock_reads==((mode==2 || mode==4 || mode==8)?0:3));
 }
 holding=true;mode=0;
 const unsigned cases[]={0,3,4,5,6,7,8,9,10,11,12};
 for(unsigned c=0;c<sizeof(cases)/sizeof(cases[0]);c++) {
  hold_mode=cases[c];
  struct waffle_npa_hold hold={0};memset(&npa,0,sizeof(npa));
  npa.revision=hold_mode==11?0x10002:0x10003;npa.query_by_name=query;
  npa.create_client=hold_mode==12?NULL:create;npa.scalar_request=request;
  npa_calls=created=requested=0;
  bool success=waffle_firmware_power_hold(&bs,&hold,log_line);
  assert(success==(hold_mode==0));assert(hold.verified==success);
  assert(hold.attempted==(hold_mode<10));
  if(success)assert(created==2 && requested==2 && npa_calls==8);
  if(hold.attempted) {
   unsigned previous_created=created,previous_requested=requested;
   assert(!waffle_firmware_power_hold(&bs,&hold,log_line));
   assert(created==previous_created && requested==previous_requested);
  } else assert(!created && !requested);
 }
 puts("Read-only firmware audit: version guards, absent protocols/resources, ABI width, query types and getter errors passed");
 puts("NPA baseline hold: exact256 requests, partial failures retained, preflight/version/refusal and no repeated allocation passed");
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-I',str(root/'loader'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
audit['scope']='Extracted PJD110 NPA/Clock table ABI; queryByName22/CreateSyncClient2/ScalarRequest5 and wrapper argument widths verified. Audit is read-only; separately invoked hold requests the existing NOM256 baseline until reset.'
audit['hardware_tested']=False
(root/'work/waffle/gpu/firmware-power-abi-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
