#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <dispatch/dispatch.h>
#include <fcntl.h>
#include <stdio.h>

@interface NSObject (WaffleSliderAPI)
+ (id)serviceForClientIdentifier:(id)identifier;
+ (id)defaultMode;
+ (id)lifetimeForUserRequest;
+ (id)userRequestedAssertionDetailsWithIdentifier:(id)identifier modeIdentifier:(id)mode lifetime:(id)lifetime;
- (id)activeModeAssertionWithError:(NSError **)error;
- (id)takeModeAssertionWithDetails:(id)details error:(NSError **)error;
- (id)invalidateActiveModeAssertionWithError:(NSError **)error;
- (id)details;
- (id)identifier;
- (id)modeIdentifier;
- (id)ringerControl;
- (BOOL)isRingerMuted;
- (void)setRingerMuted:(BOOL)muted;
- (void)activateRingerHUDFromMuteSwitch:(int)muted;
@end
static void logState(NSString *text)
{
 int fd=open("/dev/console",O_WRONLY);
 if(fd>=0){dprintf(fd,"waffle-slider-control: %s\n",text.UTF8String);close(fd);}
}
static BOOL abi(id object,const char *selector,const char *encoding)
{
 Method method=object?class_getInstanceMethod(object_getClass(object),sel_registerName(selector)):NULL;
 return method && !strcmp(method_getTypeEncoding(method),encoding);
}
static id getter(id object,const char *selector)
{
 return abi(object,selector,"@16@0:8")?((id(*)(id,SEL))objc_msgSend)(object,sel_registerName(selector)):nil;
}
static id focusBannerManager;
static unsigned focusBannerRevision;
static BOOL (*originalPostPresentable)(id,SEL,id,NSUInteger,id,NSError *__autoreleasing *);
static BOOL observedPostPresentable(id self,SEL selector,id presentable,NSUInteger options,id userInfo,NSError *__autoreleasing *error)
{
 NSError *__autoreleasing localError=nil;
 BOOL result;
 if(error)result=originalPostPresentable(self,selector,presentable,options,userInfo,error);
 else result=originalPostPresentable(self,selector,presentable,options,userInfo,&localError);
 if([presentable isKindOfClass:NSClassFromString(@"FCUIFocusEnablementIndicatorBannerPresentable")])
  logState([NSString stringWithFormat:@"native Focus post accepted=%d error=%@ requester=%@ options=%lu userInfo=%@",result,error?*error:localError,getter(presentable,"requesterIdentifier"),(unsigned long)options,userInfo]);
 return result;
}
static void observeFocusPoster(id poster)
{
 if(originalPostPresentable)return;
 SEL selector=sel_registerName("postPresentable:withOptions:userInfo:error:");
 Method method=class_getInstanceMethod(object_getClass(poster),selector);
 if(!method || strcmp(method_getTypeEncoding(method),"B48@0:8@16Q24@32o^@40"))return;
 originalPostPresentable=(void *)method_setImplementation(method,(IMP)observedPostPresentable);
}
static void (*originalFocusRevoke)(id,SEL,id);
static void observedFocusRevoke(id self,SEL selector,id reason)
{
 logState([NSString stringWithFormat:@"native Focus revoke reason=%@",reason]);
 originalFocusRevoke(self,selector,reason);
}
static void (*originalFocusAppear)(id,SEL,id);
static void observedFocusAppear(id self,SEL selector,id banner)
{
 logState(@"native Focus presentable did appear");
 originalFocusAppear(self,selector,banner);
}
static void observeFocusLifecycle(Class managerClass)
{
 Method revoke=class_getInstanceMethod(managerClass,sel_registerName("revokeWithReason:"));
 if(!originalFocusRevoke && revoke && !strcmp(method_getTypeEncoding(revoke),"v24@0:8@16"))
  originalFocusRevoke=(void *)method_setImplementation(revoke,(IMP)observedFocusRevoke);
 Class presentable=NSClassFromString(@"FCUIFocusEnablementIndicatorBannerPresentable");
 Method appear=class_getInstanceMethod(presentable,sel_registerName("presentableDidAppearAsBanner:"));
 if(!originalFocusAppear && appear && !strcmp(method_getTypeEncoding(appear),"v24@0:8@16"))
  originalFocusAppear=(void *)method_setImplementation(appear,(IMP)observedFocusAppear);
}
static void postFocusBanner(id application,id mode,BOOL enabled)
{
 if(!enabled)return;
 dlopen("/System/Library/PrivateFrameworks/Focus.framework/Focus",RTLD_LAZY|RTLD_LOCAL);
 dlopen("/System/Library/PrivateFrameworks/FocusUI.framework/FocusUI",RTLD_LAZY|RTLD_LOCAL);
 id activityManager=getter(NSClassFromString(@"FCActivityManager"),"sharedActivityManager");
 id activity=getter(activityManager,"defaultActivity");
 Class activityClass=NSClassFromString(@"_FCActivity");
 if(!activity && abi([activityClass alloc],"initWithMode:","@24@0:8@16"))
  activity=((id(*)(id,SEL,id))objc_msgSend)([activityClass alloc],sel_registerName("initWithMode:"),mode);
 id poster=getter(application,"bannerManager");
 Class cls=NSClassFromString(@"FCUIFocusEnablementIndicatorBannerManager");
 if(!activity || !abi(cls,"managerWithBannerPoster:","@24@0:8@16") ||
    !abi(poster,"postPresentable:withOptions:userInfo:error:","B48@0:8@16Q24@32o^@40")){
  logState(@"native Focus banner dependencies unavailable");return;
 }
 observeFocusPoster(poster);
 observeFocusLifecycle(cls);
 if(!focusBannerManager)focusBannerManager=((id(*)(id,SEL,id))objc_msgSend)(cls,sel_registerName("managerWithBannerPoster:"),poster);
 id manager=focusBannerManager;
 if(!abi(manager,"postActivity:enabled:","v28@0:8@16B24")){logState(@"native Focus banner ABI mismatch");return;}
 unsigned request=focusBannerRevision;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,500*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
  if(request!=focusBannerRevision){logState(@"Focus banner superseded before presentation");return;}
  id liveActivity=getter(activityManager,"activeActivity");
  logState([NSString stringWithFormat:@"native Focus UI activity=%@ expected_enabled=%d",getter(liveActivity,"activityIdentifier"),enabled]);
  ((void(*)(id,SEL,id,BOOL))objc_msgSend)(manager,sel_registerName("postActivity:enabled:"),activity,enabled);
  logState([NSString stringWithFormat:@"native_Focus_banner enabled=%d sequence=%u activity=%@",enabled,request,getter(activity,"activityIdentifier")]);
 });
}
void waffle_slider_apply(int position)
{
 if(position<1 || position>3)return;
 ++focusBannerRevision;
 @try {
  if(position!=1 && abi(focusBannerManager,"revokeWithReason:","v24@0:8@16"))
   ((void(*)(id,SEL,id))objc_msgSend)(focusBannerManager,sel_registerName("revokeWithReason:"),@"Alert Slider changed mode");
  dlopen("/System/Library/PrivateFrameworks/DoNotDisturb.framework/DoNotDisturb",RTLD_LAZY|RTLD_LOCAL);
  Class serviceClass=NSClassFromString(@"DNDModeAssertionService");
  Class detailsClass=NSClassFromString(@"DNDModeAssertionDetails");
  if(!abi(serviceClass,"serviceForClientIdentifier:","@24@0:8@16") ||
     !abi(detailsClass,"userRequestedAssertionDetailsWithIdentifier:modeIdentifier:lifetime:","@40@0:8@16@24@32")){
   logState(@"Focus class ABI mismatch; no state changes");return;
  }
  id application=getter(NSClassFromString(@"UIApplication"),"sharedApplication");
  id ringer=getter(application,"ringerControl");
  if(!abi(ringer,"setRingerMuted:","v20@0:8B16") || !abi(ringer,"isRingerMuted","B16@0:8")){
   logState(@"ringer ABI mismatch; no state changes");return;
  }
  if(position==2){
   CFPreferencesSetAppValue(CFSTR("silent-vibrate"),kCFBooleanTrue,CFSTR("com.apple.springboard"));
   CFPreferencesAppSynchronize(CFSTR("com.apple.springboard"));
  }
  [ringer setRingerMuted:position==2];
  if(position!=1 && abi(ringer,"activateRingerHUDFromMuteSwitch:","v20@0:8i16"))
   [ringer activateRingerHUDFromMuteSwitch:position==2?0:1];
  logState([NSString stringWithFormat:@"ringer position=%d muted=%d",position,[ringer isRingerMuted]]);
  if(position!=1){
   id hud=getter(ringer,"ringerHUDViewController");
   BOOL silent=NO;
   if(abi(hud,"isRingerSilent","B16@0:8"))silent=((BOOL(*)(id,SEL))objc_msgSend)(hud,sel_registerName("isRingerSilent"));
   BOOL vibrate=NO;Class prefs=NSClassFromString(@"SBSoundPreferences");
   if(abi(prefs,"vibrateWhenSilent","B16@0:8"))vibrate=((BOOL(*)(id,SEL))objc_msgSend)(prefs,sel_registerName("vibrateWhenSilent"));
   static unsigned changes;
   logState([NSString stringWithFormat:@"position=%d change=%u muted=%d native_vibrate_when_silent=%d native_HUD=1 HUD_isRingerSilent=%d",position,++changes,[ringer isRingerMuted],vibrate,silent]);
  }
  NSString *owner=@"org.waffle.alert-slider";
  id service=[serviceClass serviceForClientIdentifier:@"com.apple.springboard.donotdisturb.hid"];
  if(!abi(service,"activeModeAssertionWithError:","@24@0:8^@16") ||
     !abi(service,"takeModeAssertionWithDetails:error:","@32@0:8@16^@24") ||
     !abi(service,"invalidateActiveModeAssertionWithError:","@24@0:8^@16")){
   logState(@"Focus service ABI mismatch; no state changes");return;
  }
  NSError *error=nil;
  id active=[service activeModeAssertionWithError:&error];
  if(error){logState([NSString stringWithFormat:@"read Focus error=%@",error]);return;}
  id activeDetails=getter(active,"details");BOOL owned=[getter(activeDetails,"identifier") isEqual:owner];
  BOOL changedFocus=NO;
  id defaultMode=getter(NSClassFromString(@"DNDMode"),"defaultMode");
  if(position==1) {
   id mode=defaultMode;
   id modeID=getter(mode,"modeIdentifier");
   id lifetime=getter(NSClassFromString(@"DNDModeAssertionLifetime"),"lifetimeForUserRequest");
   if(![modeID isKindOfClass:NSString.class] || !lifetime){logState(@"default Focus mode/lifetime absent");return;}
   if(!owned || ![getter(activeDetails,"modeIdentifier") isEqual:modeID]){
    id details=[detailsClass userRequestedAssertionDetailsWithIdentifier:owner modeIdentifier:modeID lifetime:lifetime];
    id assertion=[service takeModeAssertionWithDetails:details error:&error];
    changedFocus=assertion!=nil && error==nil;
    if(!assertion || error){logState([NSString stringWithFormat:@"take DND error=%@",error]);return;}
   }
  } else if(owned) {
   [service invalidateActiveModeAssertionWithError:&error];
   if(error){logState([NSString stringWithFormat:@"release owned DND error=%@",error]);return;}
   changedFocus=YES;
  }
  error=nil;id after=[service activeModeAssertionWithError:&error];
  id afterDetails=getter(after,"details");
  BOOL confirmedOn=[getter(afterDetails,"identifier") isEqual:owner] &&
      [getter(afterDetails,"modeIdentifier") isEqual:getter(defaultMode,"modeIdentifier")];
  if(changedFocus && !error && position==1 && confirmedOn)
   postFocusBanner(application,defaultMode,YES);
  BOOL silentVibrate=NO;Class prefs=NSClassFromString(@"SBSoundPreferences");
  if(abi(prefs,"vibrateWhenSilent","B16@0:8"))silentVibrate=((BOOL(*)(id,SEL))objc_msgSend)(prefs,sel_registerName("vibrateWhenSilent"));
  logState([NSString stringWithFormat:@"position=%d muted=%d vibrate_when_silent=%d active_mode=%@ owner=%@ focus_read_error=%@ haptic_driver_unavailable=1",position,[ringer isRingerMuted],silentVibrate,getter(afterDetails,"modeIdentifier"),getter(afterDetails,"identifier"),error]);
 }@catch(NSException *exception){logState([NSString stringWithFormat:@"exception=%@",exception]);}
}
