#include <assert.h>
#include "../../kernel/files/bsd/sys/waffle_slider.h"
int main(void)
{
 for(int n=-512;n<=511;n++) {
  unsigned raw=(unsigned)n&1023;
  unsigned low=raw&255,high=((raw>>8)&1)<<6|(n<0?128:0);
  assert(waffle_hall_decode(low,high)==n);
 }
 assert(waffle_slider_classify(121,45)==1);
 assert(waffle_slider_classify(81,83)==2);
 assert(waffle_slider_classify(50,115)==3);
 assert(waffle_slider_classify(0,0)==0);
 assert(waffle_slider_classify(-512,511)==0);
 assert(waffle_slider_classify(63,104)==0);
 return 0;
}
