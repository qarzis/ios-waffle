/* Read-only, bounded SpringBoard geometry audit for the RAM UI test. */
#import <UIKit/UIKit.h>
#import <CoreFoundation/CoreFoundation.h>
#include <dispatch/dispatch.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern CFTypeRef MGCopyAnswer(CFStringRef key);
static int console = -1;
static unsigned visited;
static dispatch_source_t timer;

static void views(UIView *view, UIWindow *window, unsigned depth)
{
    if (++visited > 512 || depth > 24) return;
    NSString *name = NSStringFromClass(view.class);
    if ([name containsString:@"Volume"] || [name containsString:@"HUD"]) {
        CGRect r = [view convertRect:view.bounds toView:window];
        dprintf(console,"waffle-hud: view=%s window=%s rect=%.2f,%.2f,%.2f,%.2f hidden=%d alpha=%.2f\n",
                name.UTF8String,NSStringFromClass(window.class).UTF8String,
                r.origin.x,r.origin.y,r.size.width,r.size.height,view.hidden,view.alpha);
        if ([name isEqualToString:@"SBElasticVolumeSliderView"]) {
            CGPoint point=CGPointMake(CGRectGetMidX(r),CGRectGetMidY(r));
            UIView *hit=[window hitTest:point withEvent:nil];
            dprintf(console,"waffle-hud: slider center hit=%s descendant=%d model_y=%.2f\n",
                    hit ? NSStringFromClass(hit.class).UTF8String : "nil",
                    hit ? [hit isDescendantOfView:view] : 0,point.y);
        }
    }
    for (UIView *child in view.subviews) views(child,window,depth+1);
}

__attribute__((constructor)) static void start(void)
{
    if (strcmp(getprogname(),"SpringBoard")) return;
    console=open("/dev/console",O_WRONLY);
    if (console<0) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        UIScreen *screen=UIScreen.mainScreen;
        dprintf(console,"waffle-hud: screen=%.0fx%.0f scale=%.0f native=%.0fx%.0f read_only=1\n",
                screen.bounds.size.width,screen.bounds.size.height,screen.scale,
                screen.nativeBounds.size.width,screen.nativeBounds.size.height);
        for (NSString *key in @[@"main-screen-scale",@"main-screen-width",@"main-screen-height",@"volume-up-button-location",@"volume-down-button-location"]) {
            CFTypeRef answer=MGCopyAnswer((__bridge CFStringRef)key);
            if (answer) {
                dprintf(console,"waffle-hud: MG %s = %s\n",key.UTF8String,[(__bridge id)answer description].UTF8String);
                CFRelease(answer);
            }
        }
        timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,dispatch_get_main_queue());
        dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,15*NSEC_PER_SEC),NSEC_PER_SEC/2,NSEC_PER_MSEC*50);
        __block unsigned ticks=0;
        dispatch_source_set_event_handler(timer, ^{
            @autoreleasepool {
                if (++ticks>330) { dispatch_source_cancel(timer); return; }
                visited=0;
                for (UIWindow *window in UIApplication.sharedApplication.windows) {
                    if (!window.hidden && window.alpha>0) views(window,window,0);
                }
            }
        });
        dispatch_resume(timer);
    });
}
