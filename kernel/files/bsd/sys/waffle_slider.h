#ifndef _SYS_WAFFLE_SLIDER_H_
#define _SYS_WAFFLE_SLIDER_H_
#include <stdint.h>
static inline int waffle_hall_decode(uint8_t low,uint8_t high)
{
 int value=((high&0x40)<<2)|low;
 return high&0x80?value-512:value;
}
static inline int waffle_slider_classify(int up,int down)
{
 const int reference[3][2]={{126,43},{84,82},{46,119}};
 int winner=0;
 for(int i=0;i<3;i++) {
  int dx=up-reference[i][0],dy=down-reference[i][1];
  if(dx>=-16 && dx<=16 && dy>=-16 && dy<=16) {
   if(winner)return 0;
   winner=i+1;
  }
 }
 return winner;
}
#endif
