"""Actual split QMP protocol against the pinned E18 transaction, including IO trace."""
from pathlib import Path
import subprocess, tempfile

root = Path(__file__).resolve().parents[2]
legacy = (root / 'tools/tests/fixtures/waffle-aop-transaction-e18.inc').read_text()
import hashlib
assert hashlib.sha256(legacy.encode()).hexdigest() == 'edd4da2de647dcbb35aeb23287c284ee95f0e94136f1e44343ad47513044ee5b'
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_aop.h"
struct model {uint32_t ram[256],trace[1024];unsigned count,waits,fail_wait,fail_on,fail_off,tasks,on,off;};
static void event(struct model *m,unsigned type,unsigned offset,unsigned value){assert(m->count+3<1024);m->trace[m->count++]=type;m->trace[m->count++]=offset;m->trace[m->count++]=value;}
static uint32_t rd(void *arg,uint32_t offset){struct model *m=arg;assert(!(offset&3) && offset<sizeof(m->ram));return m->ram[offset/4];}
static void wr(void *arg,uint32_t offset,uint32_t value){struct model *m=arg;assert(!(offset&3) && offset<sizeof(m->ram));event(m,1,offset,value);m->ram[offset/4]=value;}
static void kick(void *arg){struct model *m=arg;event(m,2,0,0);m->ram[0x30/4]=m->ram[0x2c/4];if(m->ram[0x128/4]){bool on=!memcmp(&m->ram[0x12c/4],"{class: gpu, res: acd, val: 1}",31);if(on)m->on++;else m->off++;if(!(on?m->fail_on:m->fail_off))m->ram[0x128/4]=0;}}
static bool wait_for(void *arg,uint32_t offset,uint32_t value){struct model *m=arg;event(m,3,offset,value);return ++m->waits!=m->fail_wait && rd(arg,offset)==value;}
static void task(void *arg){struct model *m=arg;event(m,4,0,0);assert(m->ram[0x2c/4]==WAFFLE_AOP_QMP_UP);m->tasks++;}
static void reset(struct model *m,unsigned mode){memset(m,0,sizeof(*m));m->ram[0]=WAFFLE_AOP_QMP_MAGIC;m->ram[1]=1;m->ram[0x34/4]=728;m->ram[0x38/4]=0x128;const unsigned up[]={0x0c,0x10,0x14,0x18,0x24,0x28};for(unsigned i=0;i<6;i++)m->ram[up[i]/4]=WAFFLE_AOP_QMP_UP;m->ram[0x2c/4]=m->ram[0x30/4]=WAFFLE_AOP_QMP_DOWN;if(mode<6)m->fail_wait=mode;if(mode==6)m->fail_on=1;if(mode==7)m->fail_off=1;if(mode==8)m->ram[0x128/4]=1;if(mode==9)m->ram[0]=0;if(mode==10)m->ram[0x2c/4]=WAFFLE_AOP_QMP_UP;}
'''
tests = r'''
int main(void){
 for(unsigned acd=0;acd<2;acd++)for(unsigned mode=0;mode<11;mode++){
  struct model before,after;reset(&before,mode);reset(&after,mode);
  struct waffle_aop_qmp_io a={&before,rd,wr,kick,wait_for},b={&after,rd,wr,kick,wait_for};
  enum waffle_aop_qmp_result expected=legacy_transaction_run(&a,acd,task,&before);
  enum waffle_aop_qmp_result actual=waffle_aop_qmp_transaction_run(&b,acd,task,&after);
  assert(expected==actual && !memcmp(&before,&after,sizeof(before)));
 }
 struct model m;reset(&m,0);struct waffle_aop_qmp_io io={&m,rd,wr,kick,wait_for};
 struct waffle_aop_qmp_session session={0};
 assert(waffle_aop_qmp_session_begin(&io,&session,true)==WAFFLE_AOP_QMP_OK);
 assert(session.changed && session.opened && session.acd_attempted && !session.restored && m.on==1 && !m.off);
 unsigned writes=m.count;
 assert(waffle_aop_qmp_session_begin(&io,&session,true)==WAFFLE_AOP_QMP_REFUSED && m.count==writes);
 task(&m); /* A separate caller uses the still-open channel after begin returns. */
 assert(waffle_aop_qmp_session_end(&session)==WAFFLE_AOP_QMP_OK && session.restored && !session.changed && m.off==1);
 writes=m.count;assert(waffle_aop_qmp_session_end(&session)==WAFFLE_AOP_QMP_REFUSED && m.count==writes);
 assert(waffle_aop_qmp_session_begin(NULL,NULL,true)==WAFFLE_AOP_QMP_REFUSED);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(code + legacy + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-I', str(root / 'kernel/files/bsd/sys'), str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Actual split QMP: 22 pinned-E18 IO trace/result parity cases, live return and duplicate begin/end refusal passed (host only)')
