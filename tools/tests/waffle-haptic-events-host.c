#include <assert.h>
#include <stdio.h>
#include "waffle_haptic_events.h"
int main(void){struct waffle_haptic_events s={0};int16_t quiet[]={0,256,-256},tap[]={0,32767,-32768};
 waffle_haptic_events_feed(&s,quiet,3,0);assert(!s.pending&&s.frames==3);
 waffle_haptic_events_feed(&s,tap,3,1);assert(s.onsets==1&&waffle_haptic_events_take(&s,1));
 for(uint64_t n=2;n<100000;n+=1000){waffle_haptic_events_feed(&s,tap,3,n);assert(!waffle_haptic_events_take(&s,n));}/* long signal cannot hold motor or retrigger */
 waffle_haptic_events_feed(&s,quiet,3,100001);waffle_haptic_events_feed(&s,tap,3,100002);assert(waffle_haptic_events_take(&s,100002));
 for(unsigned i=1;i<=10;i++){waffle_haptic_events_feed(&s,quiet,3,100002+i);waffle_haptic_events_feed(&s,tap,3,100003+i);assert(!waffle_haptic_events_take(&s,100003+i));}assert(s.pending);assert(waffle_haptic_events_take(&s,180002)&&!s.pending);/* bounded coalescing */
 waffle_haptic_events_feed(&s,quiet,3,200000);waffle_haptic_events_feed(&s,tap,3,200001);assert(!waffle_haptic_events_take(&s,300002)&&!s.pending);/* stale work discarded */
 waffle_haptic_events_feed(&s,tap,3,400000);assert(waffle_haptic_events_take(&s,400000));/* gap is a new onset */
 assert(!waffle_haptic_events_take(NULL,1));waffle_haptic_events_feed(NULL,tap,3,0);waffle_haptic_events_feed(&s,NULL,3,0);
 puts("PASS PCM tap queue: signed extrema, silence threshold, one onset per sustained signal,80ms cooldown, coalescing/stale discard, no hardware.");}
