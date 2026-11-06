#!/usr/bin/env python3
"""Compare count/flag interpretation with the actual pinned native functions."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2]
source=(r/'work/waffle/haptics/upstream/qcom-hv-haptics.c').read_text()
def function(name):
 start=source.index('static int '+name+'(');brace=source.index('{',start);depth=1;end=brace+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
native=function('haptics_get_fifo_fill_status')+'\n'+function('haptics_get_available_fifo_memory')
code=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "waffle_haptic_fifo_status.h"
typedef uint8_t u8;typedef uint32_t u32;
enum {HAP520,HAP520_MV,HAP525_HV};
#define OPLUS_FEATURE_CHG_BASIC 1
#define FIFO_REAL_TIME_STS 0x8005
#define FIFO_REAL_TIME_FILL_STATUS_MSB_MASK_V2 3
#define FIFO_REAL_TIME_FILL_STATUS_MSB_MASK_V3 7
#define FIFO_REAL_TIME_FILL_STATUS_MSB_MASK_V4 15
#define FIFO_EMPTY_FLAG_BIT 64
#define FIFO_FULL_FLAG_BIT 32
#define dev_err(...) ((void)0)
#define trace_qcom_haptics_fifo_hw_status(a,b,c,d) ((void)(a),(void)(b),(void)(c),(void)(d))
struct haptics_chip {unsigned hw_type;uint8_t high,low;};
static unsigned get_max_fifo_samples(struct haptics_chip *c){(void)c;return 1920;}
static int haptics_get_status_data(struct haptics_chip *c,unsigned selector,u8 *out){assert(selector==0x8005);out[0]=c->high;out[1]=c->low;return 0;}
''' + native + r'''
static uint8_t selector,extension,high,low;
static bool read8(void *ctx,uint16_t p,uint8_t a,uint8_t *v){
 (void)ctx;assert(waffle_haptic_fifo_status_read_allowed(p,a));*v=0;
 if(a==1)*v=4;
 if(p==0x7f1){if(a==8)*v=1;if(a==0xa0)*v=0x8f;return true;}
 if(a==0x46)*v=0x80;if(a==0x4c)*v=1;
 if(a==0x70)*v=selector;if(a==0x71)*v=extension;
 if(a==9||a==10){assert(selector==5&&extension==0x80);*v=a==9?high:low;}
 return true;
}
static bool write8(void *ctx,uint16_t p,uint8_t a,uint8_t v){(void)ctx;assert(waffle_haptic_fifo_status_write_allowed(p,a));if(a==0x70)selector=v;else extension=v;return true;}
int main(void){
 const struct waffle_haptic_fifo_status_io io={NULL,read8,write8,true};
 for(unsigned fill=0;fill<4096;fill++)for(unsigned flags=0;flags<4;flags++){
  high=(fill>>8)|((flags&1)?0x20:0)|((flags&2)?0x40:0);low=fill;selector=0x33;extension=0x12;
  struct haptics_chip chip={HAP525_HV,high,low};u32 measured;
  assert(!haptics_get_fifo_fill_status(&chip,&measured)&&measured==fill);
  int available=haptics_get_available_fifo_memory(&chip);
  assert(available==(fill>1920?-EINVAL:fill==1920?-EBUSY:1920-(int)fill));
  struct waffle_haptic_fifo_status_result result;
  assert(waffle_haptic_fifo_status(&io,&result)==(fill<=1920));
  assert(result.fill==measured&&result.status_high==high&&result.status_low==low&&result.restored);
  assert(selector==0x33&&extension==0x12);
 }
 puts("PASS actual native HAP525 fill/available functions vs selector transaction:16384 count/flag cases, full/overflow distinguished, H14 zero-count/zero-flags accepted; mock hardware only.");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
