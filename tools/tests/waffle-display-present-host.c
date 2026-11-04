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
 /* Pending copies must stay immutable while private composition proceeds. */
 setup();assert(waffle_display_present_init(&io,&s));
 for(unsigned n=0;n<600;n++){
  struct waffle_display_present_result prior;
  assert(waffle_display_present_complete(&io,&s,&prior));
  assert(!s.pending && s.completed==n);
  assert(waffle_display_present_begin(&io,&s,&r) && s.pending && !r.committed);
  uint32_t target=s.pending_target,old_active=s.active,old_frame=mem[0x360a4/4];
  uint32_t immutable[64];memcpy(immutable,ram[target==WAFFLE_DISPLAY_FRONT?0:1],sizeof(immutable));
  saved=writes;unsigned saved_copies=copies;
  assert(!waffle_display_present_begin(&io,&s,&prior) && writes==saved && copies==saved_copies);
  assert(!waffle_display_present_frame(&io,&s,&prior) && writes==saved && copies==saved_copies);
  working[n%64]^=0xaabbccdd; /* Next composition only touches private RAM. */
  assert(!memcmp(immutable,ram[target==WAFFLE_DISPLAY_FRONT?0:1],sizeof(immutable)));
  assert(s.active==old_active && mem[0x360a4/4]==old_frame);
 }
 assert(waffle_display_present_complete(&io,&s,&r) && s.completed==600 && !s.pending);
 assert(waffle_display_present_restore(&io,&s) && hardware_active==WAFFLE_DISPLAY_FRONT);
 for(unsigned n=0;n<2;n++){
  setup();assert(waffle_display_present_init(&io,&s));
  assert(waffle_display_present_begin(&io,&s,&r));
  if(n){assert(waffle_display_present_complete(&io,&s,&r));assert(waffle_display_present_begin(&io,&s,&r));}
  assert(s.pending);assert(waffle_display_present_restore(&io,&s) && !s.pending && s.failed && hardware_active==WAFFLE_DISPLAY_FRONT);
 }
 setup();assert(waffle_display_present_init(&io,&s));assert(waffle_display_present_begin(&io,&s,&r));
 stuck_flip=true;assert(!waffle_display_present_complete(&io,&s,&r) && s.failed && !s.pending && r.rollback_attempted && r.rollback_ok);
 setup();assert(waffle_display_present_init(&io,&s));assert(waffle_display_present_begin(&io,&s,&r));
 post_fault=true;assert(!waffle_display_present_complete(&io,&s,&r) && s.failed && r.rollback_ok);
 for(unsigned n=1;n<=3;n++){
  setup();assert(waffle_display_present_init(&io,&s));fail_write=writes+n;
  assert(!waffle_display_present_begin(&io,&s,&r) && s.failed && !s.pending && r.rollback_attempted && r.rollback_ok);
 }
 setup();assert(waffle_display_present_init(&io,&s));mem[0x360a4/4]=0xffffffffu;
 assert(waffle_display_present_begin(&io,&s,&r));assert(waffle_display_present_complete(&io,&s,&r) && r.frame==1 && r.committed);
 /* Real UI gaps can exceed the former synchronous eight-frame window. */
 setup();assert(waffle_display_present_init(&io,&s));assert(waffle_display_present_begin(&io,&s,&r));
 for(unsigned i=0;i<240;i++)present_delay(NULL,1);
 uint32_t idle_frame=mem[0x360a4/4];assert(waffle_display_present_complete(&io,&s,&r) && r.committed);
 assert(mem[0x360a4/4]==idle_frame); /* No extra sleep after already done. */
 setup();assert(waffle_display_present_init(&io,&s));assert(waffle_display_present_begin(&io,&s,&r));
 mem[0x360a4/4]=s.pending_before-1;
 assert(!waffle_display_present_complete(&io,&s,&r) && s.failed && r.rollback_attempted);
 puts("PASS actual double-buffer state:1000 full/partial working-frame updates, copy only inactive target, complete-frame commit before reuse, domain/copy/partial-write/stall failures latched, rollback and shutdown restore; plus600 deferred waits/private composition overlaps, pending-copy rejection, both-target shutdown, partial-write/stall/domain faults and frame-counter wrap; hardware mocked");}
