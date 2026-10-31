#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <mach-o/dyld.h>
#include <sys/sysctl.h>
#include <fcntl.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
extern const void *_dyld_get_shared_cache_range(size_t *length);

static void poster_log(const char *format, ...)
{
 char text[512]; va_list ap;
 va_start(ap, format); int n = vsnprintf(text, sizeof(text), format, ap); va_end(ap);
 int fd = open("/dev/console", O_WRONLY);
 if (fd >= 0) { if (n > 0) write(fd, text, (size_t)n < sizeof(text) ? (size_t)n : sizeof(text) - 1); close(fd); }
}
static UIImage *software_image_for_view(id self, SEL cmd, UIView *view)
{
 (void)self; (void)cmd;
 if (![view isKindOfClass:[UIView class]]) return nil;
 CGRect bounds = view.bounds;
 CGFloat scale = view.layer.contentsScale;
 if (!isfinite(scale) || scale <= 0) scale = [UIScreen mainScreen].scale;
 double width = ceil(bounds.size.width * scale), height = ceil(bounds.size.height * scale);
 if (!isfinite(width) || !isfinite(height) || width <= 0 || height <= 0 ||
     width > 8192 || height > 8192 || width * height > 16777216) {
  poster_log("waffle-poster: invalid snapshot dimensions %.0fx%.0f\n", width, height);
  return nil;
 }
 UIGraphicsBeginImageContextWithOptions(bounds.size, NO, scale);
 CGContextRef context = UIGraphicsGetCurrentContext();
 UIImage *image = nil;
 if (context != NULL) {
  CGContextTranslateCTM(context, -bounds.origin.x, -bounds.origin.y);
  [view.layer renderInContext:context];
  image = UIGraphicsGetImageFromCurrentImageContext();
 }
 UIGraphicsEndImageContext();
 static unsigned samples;
 if (samples++ < 12 || image == nil)
  poster_log("waffle-poster: CPU snapshot %.0fx%.0f image=%s\n", width, height, image ? "made" : "nil");
 return image;
}
#ifdef WAFFLE_POSTER_DIAGNOSTICS
static id (*original_gallery_init)(id,SEL,id,id,id,id);
static void (*original_gallery_apply)(id,SEL,id);
static NSUInteger diagnostic_count(id object, const char *method)
{
 SEL selector=sel_registerName(method);
 return [object respondsToSelector:selector] ? ((NSUInteger (*)(id,SEL))objc_msgSend)(object,selector) : 0;
}
static id diagnostic_object(id object, const char *method)
{
 SEL selector=sel_registerName(method);
 return [object respondsToSelector:selector] ? ((id (*)(id,SEL))objc_msgSend)(object,selector) : nil;
}
static id diagnostic_gallery_init(id self,SEL cmd,id layout,id dynamic,id fixed,id extensions)
{
 id result=original_gallery_init(self,cmd,layout,dynamic,fixed,extensions);
 @try {
  id sections=diagnostic_object(layout,"sections");
  poster_log("waffle-poster-diag: configuration=%p layout=%p sections=%lu dynamicProviders=%lu staticProviders=%lu extensions=%lu\n",
      result,layout,(unsigned long)diagnostic_count(sections,"count"),
      (unsigned long)diagnostic_count(dynamic,"count"),(unsigned long)diagnostic_count(fixed,"count"),
      (unsigned long)diagnostic_count(extensions,"count"));
  if ([sections isKindOfClass:[NSArray class]]) {
   NSUInteger limit=MIN([(NSArray *)sections count],8);
   for (NSUInteger i=0;i<limit;i++) {
    id section=[(NSArray *)sections objectAtIndex:i];
    poster_log("waffle-poster-diag: layout section%lu class=%s items=%lu\n",(unsigned long)i,
        object_getClassName(section),(unsigned long)diagnostic_count(diagnostic_object(section,"items"),"count"));
   }
  }
 } @catch (NSException *exception) {
  poster_log("waffle-poster-diag: configuration observer exception=%s\n",exception.name.UTF8String);
 }
 return result;
}
static void diagnostic_gallery_apply(id self,SEL cmd,id provider)
{
 @try {
  poster_log("waffle-poster-diag: apply provider=%p class=%s sections=%lu\n",provider,
      object_getClassName(provider),(unsigned long)diagnostic_count(provider,"numberOfSections"));
 } @catch (NSException *exception) {
  poster_log("waffle-poster-diag: provider observer exception=%s\n",exception.name.UTF8String);
 }
 original_gallery_apply(self,cmd,provider);
}
static void gallery_diagnostics(uintptr_t slide)
{
 const char *init="initWithSuggestedLayout:dynamicDescriptorsByExtensionIdentifier:staticDescriptorsByExtensionIdentifier:extensionsByIdentifier:";
 Method method=class_getInstanceMethod(objc_getClass("PBFGalleryConfiguration"),sel_registerName(init));
 if (method && method_getNumberOfArguments(method)==6 &&
     (uintptr_t)method_getImplementation(method)==0x1c09f3b24UL+slide) {
  original_gallery_init=(void *)method_setImplementation(method,(IMP)diagnostic_gallery_init);
  poster_log("waffle-poster-diag: native gallery configuration observer installed\n");
 }
 method=class_getInstanceMethod(objc_getClass("_PBFGalleryCollectionViewController"),
     sel_registerName("_applySnapshotFromDataProvider:"));
 if (method && method_getNumberOfArguments(method)==3 &&
     (uintptr_t)method_getImplementation(method)==0x1c09d35a4UL+slide) {
  original_gallery_apply=(void *)method_setImplementation(method,(IMP)diagnostic_gallery_apply);
  poster_log("waffle-poster-diag: native gallery provider observer installed\n");
 }
}
#endif
void redwood_poster_init(void)
{
 char arguments[1024] = ""; size_t size = sizeof(arguments) - 1, cache_length = 0;
 if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) != 0 || !strstr(arguments, "waffle=1")) return;
 const void *cache = _dyld_get_shared_cache_range(&cache_length);
 if (!cache) return;
#ifdef WAFFLE_POSTER_DIAGNOSTICS
 gallery_diagnostics((uintptr_t)cache-0x180000000UL);
#endif
 uintptr_t expected = 0x1c0a0f8fcUL + (uintptr_t)cache - 0x180000000UL;
 int count = objc_getClassList(NULL, 0);
 if (count <= 0) return;
 Class *classes = calloc((size_t)count, sizeof(Class));
 if (!classes) return;
 int found = objc_getClassList(classes, count);
 if (found > count) found = count;
 SEL selector = sel_registerName("_imageForView:");
 for (int i = 0; i < found; ++i) {
  for (int meta = 0; meta < 2; ++meta) {
   Method method = meta ? class_getClassMethod(classes[i], selector) : class_getInstanceMethod(classes[i], selector);
   if (!method || (uintptr_t)method_getImplementation(method) != expected) continue;
   char *result = method_copyReturnType(method);
   char argument[16] = "";
   method_getArgumentType(method, 2, argument, sizeof(argument));
   BOOL compatible = result && result[0] == '@' && argument[0] == '@' && method_getNumberOfArguments(method) == 3;
   free(result);
   if (compatible) {
    method_setImplementation(method, (IMP)software_image_for_view);
    poster_log("waffle-poster: %c[%s _imageForView:] uses CPU snapshots (Metal unavailable)\n",
        meta ? '+' : '-', class_getName(classes[i]));
   } else poster_log("waffle-poster: snapshot method signature differs; left alone\n");
   free(classes);
   return;
  }
 }
 free(classes);
 poster_log("waffle-poster: expected snapshot method not found; left alone\n");
}
