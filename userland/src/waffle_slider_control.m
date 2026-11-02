#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <dlfcn.h>
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
void waffle_slider_apply(int position)
{
 if(position<1 || position>3)return;
 @try {
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
  NSString *owner=@"org.waffle.alert-slider";
  id service=[serviceClass serviceForClientIdentifier:owner];
  if(!abi(service,"activeModeAssertionWithError:","@24@0:8^@16") ||
     !abi(service,"takeModeAssertionWithDetails:error:","@32@0:8@16^@24") ||
     !abi(service,"invalidateActiveModeAssertionWithError:","@24@0:8^@16")){
   logState(@"Focus service ABI mismatch; no state changes");return;
  }
  NSError *error=nil;
  id active=[service activeModeAssertionWithError:&error];
  if(error){logState([NSString stringWithFormat:@"read Focus error=%@",error]);return;}
  id activeDetails=getter(active,"details");BOOL owned=[getter(activeDetails,"identifier") isEqual:owner];
  if(position==1) {
   id mode=getter(NSClassFromString(@"DNDMode"),"defaultMode");
   id modeID=getter(mode,"modeIdentifier");
   id lifetime=getter(NSClassFromString(@"DNDModeAssertionLifetime"),"lifetimeForUserRequest");
   if(![modeID isKindOfClass:NSString.class] || !lifetime){logState(@"default Focus mode/lifetime absent");return;}
   if(!owned || ![getter(activeDetails,"modeIdentifier") isEqual:modeID]){
    id details=[detailsClass userRequestedAssertionDetailsWithIdentifier:owner modeIdentifier:modeID lifetime:lifetime];
    id assertion=[service takeModeAssertionWithDetails:details error:&error];
    if(!assertion || error){logState([NSString stringWithFormat:@"take DND error=%@",error]);return;}
   }
  } else if(owned) {
   [service invalidateActiveModeAssertionWithError:&error];
   if(error){logState([NSString stringWithFormat:@"release owned DND error=%@",error]);return;}
  }
  if(position==2){
   CFPreferencesSetAppValue(CFSTR("silent-vibrate"),kCFBooleanTrue,CFSTR("com.apple.springboard"));
   CFPreferencesAppSynchronize(CFSTR("com.apple.springboard"));
  }
  [ringer setRingerMuted:position==2];
  error=nil;id after=[service activeModeAssertionWithError:&error];
  id afterDetails=getter(after,"details");
  BOOL silentVibrate=NO;Class prefs=NSClassFromString(@"SBSoundPreferences");
  if(abi(prefs,"vibrateWhenSilent","B16@0:8"))silentVibrate=((BOOL(*)(id,SEL))objc_msgSend)(prefs,sel_registerName("vibrateWhenSilent"));
  logState([NSString stringWithFormat:@"position=%d muted=%d vibrate_when_silent=%d active_mode=%@ owner=%@ focus_read_error=%@ haptic_driver_unavailable=1",position,[ringer isRingerMuted],silentVibrate,getter(afterDetails,"modeIdentifier"),getter(afterDetails,"identifier"),error]);
 }@catch(NSException *exception){logState([NSString stringWithFormat:@"exception=%@",exception]);}
}
