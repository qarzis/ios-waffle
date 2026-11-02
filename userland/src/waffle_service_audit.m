/* Read-only discovery of the actual iOS16 service interfaces before use. */
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void methods(int fd,Class cls,BOOL meta)
{
    unsigned count=0;
    Method *list=class_copyMethodList(meta ? object_getClass(cls) : cls,&count);
    unsigned printed=0;
    for (unsigned i=0;i<count && printed<64;i++) {
        const char *name=sel_getName(method_getName(list[i]));
        if (strstr(name,".cxx_") || strstr(name,"dealloc")) continue;
        dprintf(fd,"waffle-service: %c[%s %s] types=%s\n",meta?'+':'-',class_getName(cls),name,method_getTypeEncoding(list[i]));
        printed++;
    }
    free(list);
}

__attribute__((constructor)) static void start(void)
{
    if (strcmp(getprogname(),"SpringBoard")) return;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        int fd=open("/dev/console",O_WRONLY);
        if (fd<0) return;
        for (NSString *name in @[@"DoNotDisturb",@"PosterBoardServices",@"PosterKit",@"WallpaperKit"]) {
            NSString *path=[NSString stringWithFormat:@"/System/Library/PrivateFrameworks/%@.framework/%@",name,name];
            void *handle=dlopen(path.UTF8String,RTLD_LAZY|RTLD_LOCAL);
            dprintf(fd,"waffle-service: load %s result=%d read_only=1\n",name.UTF8String,handle!=NULL);
        }
        /* Names below were found in this exact shared cache's class symbols. */
        for (NSString *name in @[@"DNDModeAssertionService",@"DNDModeAssertionDetails",@"DNDModeAssertionLifetime",
                @"DNDModeAssertionUserRequestedLifetime",@"DNDModeSelectionService",@"DNDModeConfigurationService",
                @"SBRingerControl",@"SBVolumeControl",@"SBVolumeControlState",
                @"PRPosterConfiguration",@"PRPosterDescriptor",@"PRSPosterConfiguration",@"PRSPosterDescriptor",
                @"WKWallpaperBundle",@"WKWallpaperBundleCollection",@"WKWallpaperRepresentingCollection",
                @"WKWallpaperRepresentingCollectionsManager",@"PBFPosterConfigurationStoreCoordinator",@"PRSService"]) {
            Class cls=NSClassFromString(name);
            dprintf(fd,"waffle-service: class %s present=%d\n",name.UTF8String,cls!=Nil);
            if (cls) { methods(fd,cls,YES);methods(fd,cls,NO); }
        }
        int capacity=objc_getClassList(NULL,0);
        if (capacity>0 && capacity<100000) {
            Class __unsafe_unretained *classes=(Class __unsafe_unretained *)calloc((size_t)capacity,sizeof(Class));
            if (classes) {
                int count=objc_getClassList(classes,capacity);unsigned printed=0;
                for (int i=0;i<MIN(count,capacity) && printed<40;i++) {
                    const char *name=class_getName(classes[i]);
                    if (strncmp(name,"PRS",3) || strstr(name,"PosterConfiguration") || strstr(name,"PosterDescriptor")) continue;
                    dprintf(fd,"waffle-service: discovered class=%s\n",name);
                    methods(fd,classes[i],YES);methods(fd,classes[i],NO);printed++;
                }
                free(classes);
            }
        }
        close(fd);
    });
}
