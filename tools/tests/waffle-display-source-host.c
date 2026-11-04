#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "waffle_display_source.h"
int main(void){uint32_t pixels[36*32],seed=7;for(unsigned i=0;i<36*32;i++)pixels[i]=i;
 struct waffle_display_source_stamp a=waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,32,144),b;
 assert(a.valid&&a.seed==7);b=waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,32,144);assert(a.hash==b.hash);
 pixels[35]^=1;b=waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,32,144);assert(a.hash==b.hash); /* row padding */
 pixels[0]^=1;b=waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,32,144);assert(a.hash!=b.hash);
 seed++;b=waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,32,144);assert(a.seed!=b.seed);
 assert(!waffle_display_source_observe(&seed,pixels,0,32,32,144).valid);
 assert(!waffle_display_source_observe(&seed,pixels,sizeof(pixels),UINT32_MAX,32,144).valid);
 assert(!waffle_display_source_observe(&seed,pixels,sizeof(pixels),32,UINT32_MAX,144).valid);
 assert(!waffle_display_source_observe(&seed,(char *)pixels+1,sizeof(pixels)-1,32,32,144).valid);
 puts("PASS source observer: padded rows, seed/data changes, bounded16point reads, truncated/overflow/unaligned refusal; unchanged samples are not full-image evidence");}
