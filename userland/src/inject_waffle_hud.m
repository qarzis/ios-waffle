/* Waffle portrait HUD placement. Public UIView setters on the observed
 * SBElasticVolumeSliderView only; its model geometry also moves hit testing. */
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#include <sys/sysctl.h>
#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void (*old_center)(id,SEL,CGPoint);
static void (*old_frame)(id,SEL,CGRect);
static void (*old_layout)(id,SEL);
static unsigned moves;

static BOOL target(UIView *view)
{
    UIWindow *window=view.window;
    return window && [NSStringFromClass(window.class) isEqualToString:@"SBHUDWindow"] &&
        fabs(window.bounds.size.width-375)<.5 && fabs(window.bounds.size.height-812)<.5;
}

static CGFloat relocate(CGFloat center)
{
    /* Observed center is invariant at124 during expansion and dismissal.
     * Already relocated centers remain unchanged: no accumulated offset. */
    return fabs(center-124)<=1 ? center+96 : center;
}

static void report(CGFloat before,CGFloat after)
{
    if (before==after || moves++>=12) return;
    int fd=open("/dev/console",O_WRONLY);
    if (fd>=0) { dprintf(fd,"waffle-hud-layout: model center %.2f -> %.2f portrait375x812\n",before,after);close(fd); }
}

static void set_center(UIView *view,SEL cmd,CGPoint center)
{
    if (target(view)) { CGFloat before=center.y;center.y=relocate(center.y);report(before,center.y); }
    old_center(view,cmd,center);
}

static void set_frame(UIView *view,SEL cmd,CGRect frame)
{
    if (target(view)) {
        CGFloat before=CGRectGetMidY(frame),after=relocate(before);
        frame.origin.y+=after-before;report(before,after);
    }
    old_frame(view,cmd,frame);
}

static void layout(UIView *view,SEL cmd)
{
    old_layout(view,cmd);
    if (target(view)) {
        CGPoint center=view.center;CGFloat before=center.y;
        center.y=relocate(center.y);
        if (center.y!=before) { report(before,center.y);old_center(view,@selector(setCenter:),center); }
    }
}

static IMP install(Class cls,SEL selector,IMP replacement)
{
    Method method=class_getInstanceMethod(cls,selector);
    IMP previous=method_getImplementation(method);
    const char *types=method_getTypeEncoding(method);
    if (!class_addMethod(cls,selector,replacement,types)) class_replaceMethod(cls,selector,replacement,types);
    return previous;
}

__attribute__((constructor)) static void start(void)
{
    char args[1024]={0};size_t length=sizeof(args)-1;
    if (strcmp(getprogname(),"SpringBoard") || sysctlbyname("kern.bootargs",args,&length,NULL,0) || !strstr(args,"waffle=1")) return;
    Class cls=NSClassFromString(@"SBElasticVolumeSliderView");
    Method center=class_getInstanceMethod(cls,@selector(setCenter:));
    Method frame=class_getInstanceMethod(cls,@selector(setFrame:));
    Method subviews=class_getInstanceMethod(cls,@selector(layoutSubviews));
    char ctype[128]={0},ftype[128]={0};
    if (!center || !frame || !subviews || method_getNumberOfArguments(center)!=3 ||
        method_getNumberOfArguments(frame)!=3 || method_getNumberOfArguments(subviews)!=2) return;
    method_getArgumentType(center,2,ctype,sizeof(ctype));method_getArgumentType(frame,2,ftype,sizeof(ftype));
    if (strcmp(ctype,@encode(CGPoint)) || strcmp(ftype,@encode(CGRect))) return;
    old_center=(void *)install(cls,@selector(setCenter:),(IMP)set_center);
    old_frame=(void *)install(cls,@selector(setFrame:),(IMP)set_frame);
    old_layout=(void *)install(cls,@selector(layoutSubviews),(IMP)layout);
    int fd=open("/dev/console",O_WRONLY);
    if (fd>=0) { dprintf(fd,"waffle-hud-layout: installed exact slider class; center124+96; model geometry\n");close(fd); }
}
