from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2];s=(root/'kernel/files/bsd/dev/macan_buttons.c').read_text();a=s.index('static bool slider_config(');b=s.index('static void slider_poll(',a);actual=s[a:b]
h=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
struct macan_i2c {int unused;};static struct macan_i2c slider_bus;
static unsigned takes,gives,stops,writes,used,failAt;static uint8_t sequence[3],sensitivity,opf;static bool mismatch;
#define printf(...) ((void)0)
static void macan_pins_take(void *p){assert(p==&slider_bus);takes++;used=0;}
static void macan_pins_give_back(void *p){assert(p==&slider_bus);gives++;}
static bool macan_start(void *p){assert(p==&slider_bus);return true;}
static void macan_stop(void *p){assert(p==&slider_bus);stops++;if(used==3){if(sequence[1]==1)sensitivity=sequence[2];else if(sequence[1]==8)opf=sequence[2];}}
static bool macan_write_byte(void *p,uint8_t byte){assert(p==&slider_bus && used<3);sequence[used++]=byte;writes++;return !failAt || used!=failAt;}
static bool slider_read(unsigned address,uint8_t reg,uint8_t *value,unsigned count){assert((address==12 || address==13) && count==1 && (reg==1 || reg==8));*value=mismatch?255:reg==1?sensitivity:opf;return true;}
static void reset(void){takes=gives=stops=writes=used=failAt=0;sensitivity=2;opf=0;mismatch=false;}
'''
t=r'''
int main(void){
 reset();assert(!slider_config(11,8,0x41) && !writes && !takes);
 assert(!slider_config(12,7,1) && !writes && !takes);
 assert(!slider_config(12,1,7) && !writes && !takes);
 for(unsigned address=12;address<=13;address++){
  reset();assert(slider_start_measurement(address,0));assert(sensitivity==0 && opf==0x41);
  assert(writes==6 && takes==2 && gives==2 && stops==2);
  reset();sensitivity=0x82;assert(slider_start_measurement(address,0));assert(sensitivity==0x80 && opf==0x41);
  reset();sensitivity=0x80;opf=0x41;assert(slider_start_measurement(address,0x41));assert(!writes && !takes);
  reset();mismatch=true;assert(!slider_config(address,8,0x41));assert(takes==1 && gives==1 && stops==1);
  for(unsigned failure=1;failure<=3;failure++){
   reset();failAt=failure;assert(!slider_config(address,8,0x41));assert(takes==1 && gives==1 && stops==1);
  }
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+actual+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual Hall config functions: addresses0c/0d and volatile gain/measurement writes only, native gain0/readback, inherited active mode preservation, ACK/mismatch failures always restore pins: PASS. Mocked I2C only.')
