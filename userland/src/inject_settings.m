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

static UIImage *(*original_image_for_key)(id, SEL, id);
static void settings_log(const char *text)
{
 int fd = open("/dev/console", O_WRONLY);
 if (fd >= 0) { write(fd, text, strlen(text)); close(fd); }
}
static UIImage *image_for_key(id self, SEL cmd, id key)
{
 UIImage *image = original_image_for_key(self, cmd, key);
 if (image || ![key isKindOfClass:[NSString class]] || ![key isEqualToString:@"Wallet"]) return image;
 /* The stock cache has no 1x Wallet rendition. Use its bundled 2x icon;
  * UIImage preserves that asset's scale and UIKit downsamples it normally. */
 static dispatch_once_t once;
 static UIImage *wallet;
 dispatch_once(&once, ^{
  wallet = [[UIImage imageWithContentsOfFile:@"/Applications/Passbook.app/AppIcon-Small@2x.png"] retain];
  settings_log(wallet ? "waffle-settings: Wallet uses bundled 2x icon at display scale 1\n" :
      "waffle-settings: bundled Wallet icon unavailable\n");
 });
 return wallet;
}
void redwood_settings_init(void)
{
 char arguments[1024] = ""; size_t size = sizeof(arguments) - 1;
 if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) != 0 ||
     !strstr(arguments, "waffle=1") || !strstr(arguments, "fbscale=1")) return;
 Class cls = objc_getClass("PKIconImageCache");
 if (!cls) {
  (void)dlopen("/System/Library/PrivateFrameworks/PassKitUI.framework/PassKitUI", RTLD_NOW);
  cls = objc_getClass("PKIconImageCache");
 }
 Method method = cls ? class_getInstanceMethod(cls, sel_registerName("imageForKey:")) : NULL;
 char *result = method ? method_copyReturnType(method) : NULL;
 BOOL compatible = method && result && result[0] == '@' && method_getNumberOfArguments(method) == 3;
 free(result);
 if (!compatible) {
  settings_log("waffle-settings: expected icon cache method unavailable; left alone\n");
  return;
 }
 original_image_for_key = (void *)method_setImplementation(method, (IMP)image_for_key);
 settings_log("waffle-settings: 1x Wallet icon fallback installed\n");
}
