/* Opt-in RAM workload. ABI checked against this device's iOS16.5 cache. */
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>

@interface NSObject (WaffleApplicationLaunchProbe)
+ (id)defaultWorkspace;
- (BOOL)openApplicationWithBundleID:(NSString *)identifier;
@end

static void report(unsigned step, NSString *bundle, BOOL accepted, const char *state)
{
    int fd=open("/dev/console",O_WRONLY);
    if(fd>=0){
        dprintf(fd,"waffle-ui-animation: pid=%d step=%u bundle=%s accepted=%d state=%s\n",
                getpid(),step,bundle.UTF8String,accepted,state);
        close(fd);
    }
}

__attribute__((constructor)) static void start(void)
{
    char arguments[1024]={0};size_t size=sizeof(arguments)-1;
    if(strcmp(getprogname(),"SpringBoard") ||
       sysctlbyname("kern.bootargs",arguments,&size,NULL,0) || !strstr(arguments,"waffle=1"))return;
    const unsigned delays[]={65,90,115,140,165};
    NSArray<NSString *> *bundles=@[@"com.apple.Preferences",@"com.apple.mobilecal",
                                  @"com.apple.Preferences",@"com.apple.mobiletimer",@"com.apple.Preferences"];
    for(unsigned i=0;i<sizeof(delays)/sizeof(delays[0]);i++){
        unsigned step=i+1;NSString *bundle=bundles[i];
        /* This synchronous LaunchServices call can route back to SpringBoard.
         * Keep its main run loop available to service the open request. */
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)delays[i]*NSEC_PER_SEC),
                       dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
            @try {
                dlopen("/System/Library/Frameworks/CoreServices.framework/CoreServices",RTLD_LAZY|RTLD_LOCAL);
                Class cls=NSClassFromString(@"LSApplicationWorkspace");
                Method factory=class_getClassMethod(cls,@selector(defaultWorkspace));
                Method open_method=class_getInstanceMethod(cls,@selector(openApplicationWithBundleID:));
                if(!factory || !open_method || strcmp(method_getTypeEncoding(factory),"@16@0:8") ||
                   strcmp(method_getTypeEncoding(open_method),"B24@0:8@16")){
                    report(step,bundle,NO,"ABI_mismatch");return;
                }
                id workspace=[cls defaultWorkspace];
                report(step,bundle,NO,"request");
                struct timespec began={0},ended={0};
                clock_gettime(CLOCK_MONOTONIC,&began);
                BOOL accepted=[workspace openApplicationWithBundleID:bundle];
                clock_gettime(CLOCK_MONOTONIC,&ended);
                report(step,bundle,accepted,"returned");
                int fd=open("/dev/console",O_WRONLY);
                if(fd>=0){
                    int64_t elapsed=(ended.tv_sec-began.tv_sec)*1000000000LL+ended.tv_nsec-began.tv_nsec;
                    dprintf(fd,"waffle-ui-animation: pid=%d step=%u launch_elapsed_ms=%lld main_queue=0\n",
                            getpid(),step,(long long)(elapsed/1000000));close(fd);
                }
            }@catch(NSException *exception){
                (void)exception;report(step,bundle,NO,"exception");
            }
        });
    }
}
