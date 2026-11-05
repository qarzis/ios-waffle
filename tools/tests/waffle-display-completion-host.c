#include <assert.h>
#include <stddef.h>
#include "waffle_display_completion.h"
static const uint32_t offsets[]={0x360a4,0x16018,0x16064,0x362c0,0x362b0,0x362ac,0x5014,0x7014,0x1014,0x1010,0x100c,0x1008,0x36804,0x36800,0x160f4,0x360a4};
static unsigned calls,fail,advance;
static bool read32(void *p,uint32_t offset,uint32_t *value)
{
 assert(p==&calls && calls<16 && offset==offsets[calls]);
 if(++calls==fail)return false;
 *value=offset==0x360a4?(calls==16?17+advance:17):offset;return true;
}
int main(void)
{
 struct waffle_display_io io={&calls,read32};struct waffle_display_completion_sample sample;
 assert(waffle_display_completion_capture(&io,&sample) && calls==16 && sample.frame_before==17 && sample.frame_after==17);
 assert(sample.irq_top==0x1014 && sample.irq_top_enable==0x1010 && sample.irq_ctl==0x100c && sample.irq_ctl_enable==0x1008 && sample.irq_tear==0x36804 && sample.irq_tear_enable==0x36800 && sample.ctl_active==0x160f4);
 assert(sample.flush==0x16018 && sample.scheduler==0x16064 && sample.auto_status==0x362c0);
 assert(sample.write_line==0x362b0 && sample.read_line==0x362ac && sample.address0==0x5014 && sample.address1==0x7014);
 for(fail=1;fail<=16;fail++){calls=0;assert(!waffle_display_completion_capture(&io,&sample) && calls==fail);}
 fail=0;calls=0;advance=1;assert(waffle_display_completion_capture(&io,&sample) && sample.frame_before!=sample.frame_after);
 assert(!waffle_display_completion_capture(&io,NULL));
}
