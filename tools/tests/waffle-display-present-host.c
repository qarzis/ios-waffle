#define main previous_display_flip_main
#include "waffle-display-flip-host.c"
#undef main
#include "waffle_display_present.h"
static uint32_t ram[2][64],working[64],hardware_active,copies;static bool copy_fail;
static void present_delay(void *p,unsigned ms){delay(p,ms);if(!mem[0x16018/4])hardware_active=mem[0x5014/4]==mem[0x7014/4]?mem[0x5014/4]:0;}
static bool copy(void *p,uint32_t address){(void)p;assert(address!=hardware_active);if(copy_fail)return false;unsigned slot=address==WAFFLE_DISPLAY_FRONT?0:1;assert(address==WAFFLE_DISPLAY_FRONT||address==WAFFLE_DISPLAY_TEST);memcpy(ram[slot],working,sizeof(working));copies++;return true;}
static void setup(void){reset();hardware_active=WAFFLE_DISPLAY_FRONT;copies=0;copy_fail=false;prepared=1;for(unsigned i=0;i<64;i++){working[i]=ram[0][i]=i;ram[1][i]=0xdeadbeef;}}
int main(void){struct waffle_display_present_io io={{{{NULL,rd},wr,present_delay},domain,NULL},copy};struct waffle_display_present_state s;struct waffle_display_present_result r;
 setup();assert(waffle_display_present_init(&io,&s));
 for(unsigned n=0;n<1000;n++){working[n%64]^=0x1234;assert(waffle_display_present_frame(&io,&s,&r)&&r.committed&&r.copied);assert(hardware_active==s.active);assert(!memcmp(ram[s.active==WAFFLE_DISPLAY_FRONT?0:1],working,sizeof(working)));}
 assert(s.completed==1000&&copies==1000);assert(waffle_display_present_restore(&io,&s)&&s.active==WAFFLE_DISPLAY_FRONT&&s.failed);
 unsigned saved=writes;assert(!waffle_display_present_frame(&io,&s,&r)&&writes==saved);
 setup();assert(waffle_display_present_init(&io,&s));bad_domain=true;saved=writes;assert(!waffle_display_present_frame(&io,&s,&r)&&s.failed&&writes==saved&&!copies);
 setup();assert(waffle_display_present_init(&io,&s));copy_fail=true;saved=writes;assert(!waffle_display_present_frame(&io,&s,&r)&&s.failed&&writes==saved&&!copies);
 setup();assert(waffle_display_present_init(&io,&s));fail_write=writes+2;assert(!waffle_display_present_frame(&io,&s,&r)&&r.rollback_attempted&&r.rollback_ok&&s.failed&&hardware_active==WAFFLE_DISPLAY_FRONT);
 setup();assert(waffle_display_present_init(&io,&s));stuck_flip=true;assert(!waffle_display_present_frame(&io,&s,&r)&&r.rollback_attempted&&r.rollback_ok&&s.failed);
 setup();assert(waffle_display_present_init(&io,&s));assert(waffle_display_present_frame(&io,&s,&r)&&hardware_active==WAFFLE_DISPLAY_TEST);assert(waffle_display_present_restore(&io,&s)&&hardware_active==WAFFLE_DISPLAY_FRONT);
 puts("PASS actual double-buffer state:1000 full/partial working-frame updates, copy only inactive target, complete-frame commit before reuse, domain/copy/partial-write/stall failures latched, rollback and shutdown restore; hardware mocked");}
