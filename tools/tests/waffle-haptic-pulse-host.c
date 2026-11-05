#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_haptic_pulse.h"
struct model {uint8_t reg[3][256];unsigned reads,writes,fail_read,fail_write;uint64_t now;bool stuck,fault,frozen,stuck_after_start;};
static void init(struct model *m){*m=(struct model){0};m->reg[0][1]=m->reg[1][1]=4;m->reg[2][0]=2;m->reg[0][0x46]=0x80;m->reg[0][0x4c]=1;m->reg[0][0x48]=0x30;m->reg[0][0x63]=0x89;m->reg[1][0x26]=0xff;m->reg[2][0x41]=0xe0;}
static bool read8(void *p,uint16_t pp,uint8_t a,uint8_t *v){struct model *m=p;assert(pp>=0x7f0&&pp<=0x7f2&&waffle_haptic_read_allowed(pp,a));if(++m->reads==m->fail_read)return false;*v=m->reg[pp-0x7f0][a];if(pp==0x7f0&&a==0x0b&&m->stuck)*v=3;if(pp==0x7f0&&a==0x0c&&m->fault&&(m->reg[0][0x4c]&0x80))*v=4;return true;}
static bool write8(void *p,uint16_t pp,uint8_t a,uint8_t v){struct model *m=p;assert(waffle_haptic_pulse_write_allowed(pp,a)&&pp!=0x7f2);m->writes++;m->reg[pp-0x7f0][a]=v;if(pp==0x7f0&&a==0x4c&&v==0x81&&m->stuck_after_start)m->stuck=true;return m->writes!=m->fail_write;/* ambiguous error AFTER physical write */}
static uint64_t now(void *p){return ((struct model *)p)->now;}
static void wait(void *p,uint32_t us){struct model *m=p;assert(us<=1000);if(!m->frozen)m->now+=us;}
static struct waffle_haptic_pulse_io io(struct model *m){return (struct waffle_haptic_pulse_io){{m,read8},write8,now,wait,true};}
int main(void){struct model m;struct waffle_haptic_pulse_result r;init(&m);struct waffle_haptic_pulse_io bus=io(&m);assert(waffle_haptic_pulse(&bus,&r)&&r.passed&&r.admitted&&r.start_attempted&&r.stopped&&r.restored&&!r.emergency_disabled);assert(m.now==16000&&m.reg[0][0x63]==0x89&&m.reg[1][0x26]==0xff&&m.reg[0][0x4c]==1&&m.reg[0][0x46]==0x80);unsigned reads=m.reads,writes=m.writes;assert(writes==7);
 for(unsigned f=1;f<=reads;f++){init(&m);m.fail_read=f;assert(!waffle_haptic_pulse(&bus,&r)&&!r.passed);assert(!(m.reg[0][0x4c]&0x80)||r.emergency_disabled);assert(m.now<=36000);}
 for(unsigned f=1;f<=writes;f++){init(&m);m.fail_write=f;assert(!waffle_haptic_pulse(&bus,&r)&&!r.passed);assert(!(m.reg[0][0x4c]&0x80)||r.emergency_disabled);assert(m.now<=36000);}
 init(&m);m.fault=true;assert(!waffle_haptic_pulse(&bus,&r)&&r.stopped&&r.restored&&m.now==0);
 init(&m);m.frozen=true;assert(!waffle_haptic_pulse(&bus,&r)&&r.stopped&&r.restored&&!r.passed);assert(m.now==0);/* iteration bound independent of timer */
 init(&m);m.stuck_after_start=true;assert(!waffle_haptic_pulse(&bus,&r)&&r.start_attempted&&!r.stopped&&r.emergency_disabled&&!r.restored&&m.now==36000&&!(m.reg[0][0x46]&0x80));
 init(&m);m.stuck=true;assert(!waffle_haptic_pulse(&bus,&r)&&!r.admitted&&m.writes==0);
 for(unsigned k=0;k<8;k++){init(&m);switch(k){case 0:m.reg[2][0]=1;break;case 1:m.reg[0][0x4c]=0x81;break;case 2:m.reg[0][0x0c]=4;break;case 3:m.reg[0][0x48]=0x31;break;case 4:m.reg[2][0x46]=0x80;break;case 5:m.reg[2][0x41]=0;break;case 6:m.reg[0][0x68]=1;break;case 7:m.reg[0][0x46]=0;break;}assert(!waffle_haptic_pulse(&bus,&r)&&!r.admitted&&!m.writes);}
 init(&m);bus.exclusive_owned=false;assert(!waffle_haptic_pulse(&bus,&r)&&!m.reads&&!m.writes);
 puts("PASS bounded HAP525_HV transaction: every read and ambiguous write failure, fault stop, timer stall, exact restore, power/owner rejection; no PMIC or motor accessed.");}
