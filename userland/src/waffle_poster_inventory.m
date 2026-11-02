/* Bounded inventory using methods observed in the exact iOS16 runtime. */
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static id object0(id receiver,const char *name)
{
    SEL sel=sel_registerName(name);
    Method m=receiver?class_getInstanceMethod(object_getClass(receiver),sel):NULL;
    char type[32]={0};
    if (!m || method_getNumberOfArguments(m)!=2) return nil;
    method_getReturnType(m,type,sizeof(type));
    return type[0]=='@'?((id(*)(id,SEL))objc_msgSend)(receiver,sel):nil;
}
static NSInteger count0(id receiver,const char *name)
{
    SEL sel=sel_registerName(name);
    Method m=receiver?class_getInstanceMethod(object_getClass(receiver),sel):NULL;
    char type[32]={0};
    if (!m || method_getNumberOfArguments(m)!=2) return -1;
    method_getReturnType(m,type,sizeof(type));
    return !strcmp(type,@encode(NSInteger))?((NSInteger(*)(id,SEL))objc_msgSend)(receiver,sel):-1;
}
static id indexed(id receiver,const char *name,NSInteger index)
{
    SEL sel=sel_registerName(name);
    Method m=receiver?class_getInstanceMethod(object_getClass(receiver),sel):NULL;
    char result[32]={0},argument[32]={0};
    if (!m || method_getNumberOfArguments(m)!=3) return nil;
    method_getReturnType(m,result,sizeof(result));method_getArgumentType(m,2,argument,sizeof(argument));
    return result[0]=='@' && !strcmp(argument,@encode(NSInteger))?
        ((id(*)(id,SEL,NSInteger))objc_msgSend)(receiver,sel,index):nil;
}
static const char *describe(id value)
{
    return value?[[value description] UTF8String]:"nil";
}

__attribute__((constructor)) static void start(void)
{
    if (strcmp(getprogname(),"SpringBoard") && strcmp(getprogname(),"CollectionsPoster")) return;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        int fd=open("/dev/console",O_WRONLY);if(fd<0)return;
        @try {
            dlopen("/System/Library/PrivateFrameworks/WallpaperKit.framework/WallpaperKit",RTLD_LAZY|RTLD_LOCAL);
            id manager=object0(NSClassFromString(@"WKWallpaperRepresentingCollectionsManager"),"defaultManager");
            NSInteger count=count0(manager,"numberOfWallpaperCollections");
            dprintf(fd,"waffle-poster-inventory: manager=%s collections=%ld read_only=1 process=%s\n",manager?object_getClassName(manager):"nil",(long)count,getprogname());
            for (NSInteger i=0;i<count && i<16;i++) {
                id collection=indexed(manager,"wallpaperCollectionAtIndex:",i);
                NSInteger papers=count0(collection,"numberOfWallpapers");
                dprintf(fd,"waffle-poster-inventory: collection%ld name=%s id=%s wallpapers=%ld\n",(long)i,
                        describe(object0(collection,"displayName")),describe(object0(collection,"identifier")),(long)papers);
                for (NSInteger j=0;j<papers && j<16;j++) {
                    id bundle=indexed(collection,"wallpaperBundleAtIndex:",j);
                    dprintf(fd,"waffle-poster-inventory: collection%ld paper%ld class=%s id=%ld name=%s logicalClass=%s\n",
                            (long)i,(long)j,bundle?object_getClassName(bundle):"nil",(long)count0(bundle,"identifier"),
                            describe(object0(bundle,"name")),describe(object0(bundle,"logicalScreenClass")));
                }
            }
        } @catch(NSException *exception) {
            dprintf(fd,"waffle-poster-inventory: exception=%s reason=%s\n",exception.name.UTF8String,exception.reason.UTF8String);
        }
        close(fd);
    });
}
