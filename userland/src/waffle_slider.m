#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <dispatch/dispatch.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>

#ifdef WAFFLE_SLIDER_CONTROL
extern void waffle_slider_apply(int);
#endif
static void report(NSString *text)
{
 int fd=open("/dev/console",O_WRONLY);
 if(fd>=0){dprintf(fd,"waffle-slider-user: %s\n",text.UTF8String);close(fd);}
}
__attribute__((constructor)) static void start(void)
{
 if(strcmp(getprogname(),"SpringBoard"))return;
 static dispatch_source_t timer;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_SEC),dispatch_get_main_queue(),^{
  #ifdef WAFFLE_SLIDER_CONTROL
  report(@"Hall position control started: top DND / middle vibrate-mode / bottom ring");
#else
  report(@"read-only Hall position monitor started; no Focus/ringer changes");
#endif
  timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,dispatch_get_main_queue());
  dispatch_source_set_timer(timer,DISPATCH_TIME_NOW,250*NSEC_PER_MSEC,25*NSEC_PER_MSEC);
  dispatch_source_set_event_handler(timer,^{
   static int last=-1,lastUp,lastDown;int value=0,up=0,down=0;size_t n=sizeof(value);
   if(sysctlbyname("kern.redwood.slider_position",&value,&n,NULL,0))return;
   BOOL changed=value!=last;n=sizeof(up);sysctlbyname("kern.redwood.slider_up",&up,&n,NULL,0);
   n=sizeof(down);sysctlbyname("kern.redwood.slider_down",&down,&n,NULL,0);
   if(!changed && abs(up-lastUp)<3 && abs(down-lastDown)<3)return;
   last=value;lastUp=up;lastDown=down;
   report([NSString stringWithFormat:@"position=%d up=%d down=%d",value,up,down]);
#ifdef WAFFLE_SLIDER_CONTROL
   if(changed)waffle_slider_apply(value);
#endif
  });
  dispatch_resume(timer);
 });
}
