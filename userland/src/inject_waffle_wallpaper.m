/* Expose the bundled iOS16 wallpaper on Waffle's 375x812@2x canvas.
 * The original artwork already uses 375x812 logical CA layer bounds. */
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>

static BOOL (*old_bundle)(id,SEL,NSURL *);
static BOOL (*old_collection)(id,SEL,NSURL *);
static unsigned messages;
static NSString *const collectionPath=@"/Library/Wallpaper/Collections/iOS_16~iphone.wallpaperCollection";
static NSString *const bundleName=@"7400.WWDC_2022-375w-812h@3x~iphone.wallpaper";

static BOOL supportedCanvas(void)
{
    UIScreen *screen=UIScreen.mainScreen;
    return screen.bounds.size.width==375 && screen.bounds.size.height==812 && screen.scale==2;
}

static BOOL artworkPresent(void)
{
    NSString *path=[[collectionPath stringByAppendingPathComponent:@"Wallpapers"] stringByAppendingPathComponent:bundleName];
    NSDictionary *metadata=[NSDictionary dictionaryWithContentsOfFile:[path stringByAppendingPathComponent:@"Wallpaper.plist"]];
    if ([metadata[@"identifier"] integerValue]!=7400 || ![metadata[@"logicalScreenClass"] isEqual:@"375w-812h@3x~iphone"]) return NO;
    NSDictionary *files=metadata[@"assets"][@"lockAndHome"][@"default"];
    for (NSString *key in @[@"foregroundAnimationFileName",@"backgroundAnimationFileName",@"floatingAnimationFileNameKey"]) {
        NSString *name=files[key];
        if (![name isKindOfClass:NSString.class] || ![NSFileManager.defaultManager fileExistsAtPath:[path stringByAppendingPathComponent:name]]) return NO;
    }
    return YES;
}

static void report(const char *kind,BOOL original,BOOL accepted)
{
    if (messages++>=24) return;
    int fd=open("/dev/console",O_WRONLY);
    if(fd>=0){dprintf(fd,"waffle-wallpaper: iOS16 %s native=%d accepted=%d logical375x812 artwork3x canvas2x\n",kind,original,accepted);close(fd);}
}

static BOOL bundle(id self,SEL cmd,NSURL *url)
{
    BOOL result=old_bundle(self,cmd,url);
    NSString *target=[[collectionPath stringByAppendingPathComponent:@"Wallpapers"] stringByAppendingPathComponent:bundleName];
    if ([url.path isEqualToString:target] && supportedCanvas()) {
        BOOL accepted=result || artworkPresent();report("bundle",result,accepted);return accepted;
    }
    return result;
}
static BOOL collection(id self,SEL cmd,NSURL *url)
{
    BOOL result=old_collection(self,cmd,url);
    if ([url.path isEqualToString:collectionPath] && supportedCanvas()) {
        BOOL accepted=result || artworkPresent();report("collection",result,accepted);return accepted;
    }
    return result;
}

static IMP install(NSString *className,const char *selector,IMP implementation)
{
    Class cls=NSClassFromString(className);SEL sel=sel_registerName(selector);
    Method method=class_getClassMethod(cls,sel);char result[16]={0},argument[16]={0};
    if(!method || method_getNumberOfArguments(method)!=3)return NULL;
    method_getReturnType(method,result,sizeof(result));method_getArgumentType(method,2,argument,sizeof(argument));
    if(strcmp(result,@encode(BOOL)) || argument[0]!='@')return NULL;
    return method_setImplementation(method,implementation);
}

static void autoLog(NSString *message)
{
    int fd=open("/dev/console",O_WRONLY);
    if(fd>=0){dprintf(fd,"waffle-wallpaper-auto: %s\n",message.UTF8String);close(fd);}
}

@interface NSObject (WafflePosterService)
- (void)fetchPosterDescriptorsForExtension:(id)extension completion:(void (^)(id,id))completion;
- (void)fetchPosterConfigurationsForExtension:(id)extension completion:(void (^)(id,id))completion;
- (void)createPosterConfigurationForProviderIdentifier:(id)provider posterDescriptorIdentifier:(id)descriptor completion:(void (^)(id,id))completion;
- (void)updateToSelectedConfigurationMatchingUUID:(id)uuid completion:(void (^)(id))completion;
- (id)identifier;
- (id)serverUUID;
- (id)loadUserInfoWithError:(NSError **)error;
@end

static BOOL hasEncoding(Class cls,const char *name,const char *encoding)
{
    Method method=class_getInstanceMethod(cls,sel_registerName(name));
    return method && !strcmp(method_getTypeEncoding(method),encoding);
}
static NSDictionary *posterInfo(id poster)
{
    if(!hasEncoding(object_getClass(poster),"loadUserInfoWithError:","@24@0:8o^@16"))return nil;
    NSError *error=nil;id info=[poster loadUserInfoWithError:&error];
    return !error && [info isKindOfClass:NSDictionary.class]?info:nil;
}
static BOOL targetInfo(NSDictionary *info)
{
    return [[info[@"wallpaperRepresentingIdentifier"] description] isEqualToString:@"7400"] &&
           [info[@"wallpaperRepresentingFileName"] isEqualToString:bundleName];
}

static void selectPoster(id service,id configuration)
{
    if(!hasEncoding(object_getClass(configuration),"serverUUID","@16@0:8")){
        autoLog(@"configuration lacks verified serverUUID; stopped");return;
    }
    id uuid=[configuration serverUUID];
    if(![uuid isKindOfClass:NSUUID.class]){autoLog(@"invalid configuration UUID; stopped");return;}
    [service updateToSelectedConfigurationMatchingUUID:uuid completion:^(id error){
        autoLog([NSString stringWithFormat:@"select uuid=%@ error=%@",uuid,error]);
    }];
}
static void installDefaultPoster(void)
{
    @try {
        dlopen("/System/Library/PrivateFrameworks/PosterBoardServices.framework/PosterBoardServices",RTLD_LAZY|RTLD_LOCAL);
        Class cls=NSClassFromString(@"PRSService");
        if(!hasEncoding(cls,"fetchPosterDescriptorsForExtension:completion:","v32@0:8@16@?24") ||
           !hasEncoding(cls,"fetchPosterConfigurationsForExtension:completion:","v32@0:8@16@?24") ||
           !hasEncoding(cls,"createPosterConfigurationForProviderIdentifier:posterDescriptorIdentifier:completion:","v40@0:8@16@24@?32") ||
           !hasEncoding(cls,"updateToSelectedConfigurationMatchingUUID:completion:","v32@0:8@16@?24")){
            autoLog(@"service ABI mismatch; stopped");return;
        }
        id service=[[cls alloc] init];NSString *provider=@"com.apple.WallpaperKit.CollectionsPoster";
        [service fetchPosterConfigurationsForExtension:provider completion:^(id configurations,id error){
            @try {
                if(error || ![configurations isKindOfClass:NSArray.class]){
                    autoLog([NSString stringWithFormat:@"fetch configurations error=%@ class=%@",error,[configurations class]]);return;
                }
                for(id configuration in [(NSArray *)configurations subarrayWithRange:NSMakeRange(0,MIN([configurations count],32))]){
                    NSDictionary *info=posterInfo(configuration);
                    if(targetInfo(info)) {autoLog(@"reusing existing iOS16 configuration");selectPoster(service,configuration);return;}
                }
                [service fetchPosterDescriptorsForExtension:provider completion:^(id descriptors,id fetchError){
                    @try {
                        if(fetchError || ![descriptors isKindOfClass:NSArray.class]){
                            autoLog([NSString stringWithFormat:@"fetch descriptors error=%@ class=%@",fetchError,[descriptors class]]);return;
                        }
                        autoLog([NSString stringWithFormat:@"descriptors=%lu",(unsigned long)[descriptors count]]);
                        for(id descriptor in [(NSArray *)descriptors subarrayWithRange:NSMakeRange(0,MIN([descriptors count],32))]){
                            if(!hasEncoding(object_getClass(descriptor),"identifier","@16@0:8"))continue;
                            id identifier=[descriptor identifier];NSDictionary *info=posterInfo(descriptor);NSString *description=info.description;
                            autoLog([NSString stringWithFormat:@"descriptor=%@ info=%@",identifier,[description substringToIndex:MIN(description.length,1400)]]);
                            if(![identifier isKindOfClass:NSString.class])continue;
                            if(![identifier isEqualToString:@"7400"] || !targetInfo(info))continue;
                            [service createPosterConfigurationForProviderIdentifier:provider posterDescriptorIdentifier:identifier completion:^(id configuration,id createError){
                                @try {
                                    autoLog([NSString stringWithFormat:@"create descriptor=%@ class=%@ error=%@",identifier,[configuration class],createError]);
                                    if(configuration && !createError)selectPoster(service,configuration);
                                }@catch(NSException *e){autoLog([NSString stringWithFormat:@"create callback exception=%@",e]);}
                            }];
                            return;
                        }
                        autoLog(@"exact iOS16 collection descriptor absent; no configuration created");
                    }@catch(NSException *e){autoLog([NSString stringWithFormat:@"descriptor callback exception=%@",e]);}
                }];
            }@catch(NSException *e){autoLog([NSString stringWithFormat:@"configuration callback exception=%@",e]);}
        }];
    }@catch(NSException *e){autoLog([NSString stringWithFormat:@"service exception=%@",e]);}
}

__attribute__((constructor)) static void start(void)
{
    const char *name=getprogname();char arguments[1024]={0};size_t size=sizeof(arguments)-1;
    if((strcmp(name,"SpringBoard") && strcmp(name,"PosterBoard") && strcmp(name,"CollectionsPoster")) ||
       sysctlbyname("kern.bootargs",arguments,&size,NULL,0) || !strstr(arguments,"waffle=1"))return;
    if(!dlopen("/System/Library/PrivateFrameworks/WallpaperKit.framework/WallpaperKit",RTLD_LAZY|RTLD_LOCAL))return;
    if(!strcmp(name,"SpringBoard"))
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,40*NSEC_PER_SEC),dispatch_get_main_queue(),^{installDefaultPoster();});
    old_bundle=(void *)install(@"WKWallpaperBundle","shouldLoadWallpaperBundleAtURL:",(IMP)bundle);
    old_collection=(void *)install(@"WKWallpaperRepresentingCollection","shouldLoadWallpaperCollectionAtURL:",(IMP)collection);
    int fd=open("/dev/console",O_WRONLY);
    if(fd>=0){dprintf(fd,"waffle-wallpaper: scoped iOS16 availability installed process=%s bundle=%d collection=%d\n",name,old_bundle!=NULL,old_collection!=NULL);close(fd);}
}
