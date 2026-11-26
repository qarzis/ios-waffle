#include <CoreFoundation/CoreFoundation.h>
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <objc/runtime.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static const char *const tweak_dirs[] = {
 "/var/jb/usr/lib/TweakInject",
 "/var/jb/Library/MobileSubstrate/DynamicLibraries",
};
static void
say(const char *format, ...)
{
 char line[512];
 va_list args;
 int n, fd;
 va_start(args, format);
 n = vsnprintf(line, sizeof(line), format, args);
 va_end(args);
 if (n <= 0) {
  return;
 }
 fd = open("/dev/console", O_WRONLY | O_NOCTTY);
 if (fd >= 0) {
  (void)write(fd, line, (size_t)(n < (int)sizeof(line) ? n : (int)sizeof(line) - 1));
  close(fd);
 }
}
static const char *
executable_name(void)
{
 static char path[1024];
 uint32_t size = sizeof(path);
 char *slash;
 if (_NSGetExecutablePath(path, &size) != 0) {
  return NULL;
 }
 slash = strrchr(path, '/');
 return slash != NULL ? slash + 1 : path;
}
static bool
bundle_identifier(char *out, size_t size)
{
 CFBundleRef bundle = CFBundleGetMainBundle();
 CFStringRef identifier;
 if (bundle == NULL) {
  return false;
 }
 identifier = CFBundleGetIdentifier(bundle);
 return identifier != NULL && CFStringGetCString(identifier, out, (CFIndex)size, kCFStringEncodingUTF8);
}
static bool
array_has(CFArrayRef array, const char *want)
{
 CFIndex count = array != NULL ? CFArrayGetCount(array) : 0;
 for (CFIndex i = 0; i < count; i++) {
  CFStringRef string = CFArrayGetValueAtIndex(array, i);
  char text[256];
  if (CFGetTypeID(string) == CFStringGetTypeID() &&
      CFStringGetCString(string, text, sizeof(text), kCFStringEncodingUTF8) && strcmp(text, want) == 0) {
   return true;
  }
 }
 return false;
}
static bool
array_has_class(CFArrayRef array)
{
 CFIndex count = array != NULL ? CFArrayGetCount(array) : 0;
 for (CFIndex i = 0; i < count; i++) {
  CFStringRef string = CFArrayGetValueAtIndex(array, i);
  char text[256];
  if (CFGetTypeID(string) == CFStringGetTypeID() &&
      CFStringGetCString(string, text, sizeof(text), kCFStringEncodingUTF8) && objc_getClass(text) != NULL) {
   return true;
  }
 }
 return false;
}
static CFArrayRef
filter_array(CFDictionaryRef filter, const char *key)
{
 CFStringRef name = CFStringCreateWithCString(NULL, key, kCFStringEncodingUTF8);
 CFArrayRef array = NULL;
 if (name != NULL) {
  CFTypeRef value = CFDictionaryGetValue(filter, name);
  if (value != NULL && CFGetTypeID(value) == CFArrayGetTypeID()) {
   array = value;
  }
  CFRelease(name);
 }
 return array;
}
static bool
wanted_here(const char *path, const char *name, const char *identifier)
{
 CFDictionaryRef plist, filter;
 CFArrayRef bundles, executables, classes;
 CFStringRef mode_key, filter_key;
 CFDataRef data;
 CFTypeRef mode;
 bool all, hits[3], wanted;
 int fd, used = 0;
 uint8_t buffer[65536];
 ssize_t n;
 fd = open(path, O_RDONLY);
 n = fd >= 0 ? read(fd, buffer, sizeof(buffer)) : -1;
 if (fd >= 0) {
  close(fd);
 }
 if (n <= 0) {
  return false;
 }
 data = CFDataCreate(NULL, buffer, (CFIndex)n);
 if (data == NULL) {
  return false;
 }
 plist = (CFDictionaryRef)CFPropertyListCreateWithData(NULL, data, kCFPropertyListImmutable, NULL, NULL);
 CFRelease(data);
 if (plist == NULL || CFGetTypeID(plist) != CFDictionaryGetTypeID()) {
  if (plist != NULL) {
   CFRelease(plist);
  }
  say("redwood: tweaks: %s is not a property list\n", path);
  return false;
 }
 filter_key = CFSTR("Filter");
 filter = CFDictionaryGetValue(plist, filter_key);
 if (filter == NULL || CFGetTypeID(filter) != CFDictionaryGetTypeID()) {
  CFRelease(plist);
  return true;
 }
 bundles = filter_array(filter, "Bundles");
 executables = filter_array(filter, "Executables");
 classes = filter_array(filter, "Classes");
 hits[0] = bundles != NULL && identifier != NULL && array_has(bundles, identifier);
 hits[1] = executables != NULL && name != NULL && array_has(executables, name);
 hits[2] = classes != NULL && array_has_class(classes);
 mode_key = CFSTR("Mode");
 mode = CFDictionaryGetValue(filter, mode_key);
 all = mode != NULL && CFGetTypeID(mode) == CFStringGetTypeID() &&
     CFStringCompare(mode, CFSTR("Any"), 0) == kCFCompareEqualTo;
 used = (bundles != NULL) + (executables != NULL) + (classes != NULL);
 if (used == 0) {
  wanted = true;
 } else if (all) {
  wanted = (bundles == NULL || hits[0]) && (executables == NULL || hits[1]) && (classes == NULL || hits[2]);
 } else {
  wanted = hits[0] || hits[1] || hits[2];
 }
 CFRelease(plist);
 return wanted;
}
static void
load_the_tweaks(void)
{
 char identifier[256];
 const char *name = executable_name();
 const char *who = bundle_identifier(identifier, sizeof(identifier)) ? identifier : NULL;
 int opened = 0, tried = 0;
 for (unsigned d = 0; d < sizeof(tweak_dirs) / sizeof(tweak_dirs[0]); d++) {
  const char *where = tweak_dirs[d];
  struct dirent *entry;
  struct stat st;
  DIR *dir;
  if (d > 0 && lstat(where, &st) == 0 && S_ISLNK(st.st_mode)) {
   continue;
  }
  dir = opendir(where);
  if (dir == NULL) {
   continue;
  }
  while ((entry = readdir(dir)) != NULL) {
   char plist[1024], dylib[1024];
   size_t length = strlen(entry->d_name);
   if (length < 7 || strcmp(entry->d_name + length - 6, ".plist") != 0) {
    continue;
   }
   snprintf(plist, sizeof(plist), "%s/%s", where, entry->d_name);
   snprintf(dylib, sizeof(dylib), "%s/%.*s.dylib", where, (int)(length - 6), entry->d_name);
   if (!wanted_here(plist, name, who)) {
    continue;
   }
   tried++;
   if (dlopen(dylib, RTLD_NOW | RTLD_GLOBAL) != NULL) {
    opened++;
    say("redwood: tweaks: %s\n", dylib);
   } else {
    say("redwood: tweaks: %s: %s\n", dylib, dlerror());
   }
  }
  closedir(dir);
 }
 if (tried > 0) {
  say("redwood: tweaks: %s (%s): %d of %d opened\n", name != NULL ? name : "?",
      who != NULL ? who : "no bundle", opened, tried);
 }
}
static const char *const waffle_ringtones[] = {
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Birdsong.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Bright-Eyed.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Droplets.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Early_Riser.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/First_Light.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Helios.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Orbit.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Springtide.m4r",
 "/System/Library/PrivateFrameworks/ToneLibrary.framework/AlarmWakeUpRingtones/Sunny.m4r",
};
static id (*orig_tone_path)(id, SEL, id);
static id (*orig_tone_path_valid)(id, SEL, id, BOOL *);
static BOOL (*orig_tone_valid)(id, SEL, id);
static id
waffle_fallback_ringtone(id tone_id)
{
 char idbuf[128] = "";
 uint32_t h = 2166136261u;
 if (tone_id != NULL && CFGetTypeID((CFTypeRef)tone_id) == CFStringGetTypeID()) {
  CFStringGetCString((CFStringRef)tone_id, idbuf, sizeof(idbuf), kCFStringEncodingUTF8);
  for (const char *p = idbuf; *p; p++) { h = (h ^ (uint8_t)*p) * 16777619u; }
 }
 const char *chosen = waffle_ringtones[h % (sizeof(waffle_ringtones) / sizeof(waffle_ringtones[0]))];
 static unsigned logged = 0;
 if (logged < 24) {
  logged++;
  say("redwood-tone: mapped '%s' -> %s\n", idbuf, chosen);
 }
 return (id)CFStringCreateWithCString(kCFAllocatorDefault, chosen, kCFStringEncodingUTF8);
}
static BOOL
waffle_path_readable(id path_obj)
{
 char pbuf[512];
 if (path_obj == NULL || CFGetTypeID((CFTypeRef)path_obj) != CFStringGetTypeID()) {
  return NO;
 }
 if (!CFStringGetCString((CFStringRef)path_obj, pbuf, sizeof(pbuf), kCFStringEncodingUTF8)) {
  return NO;
 }
 return access(pbuf, R_OK) == 0 ? YES : NO;
}
static id
waffle_tone_file_path(id self, SEL sel, id tone_id)
{
 id path = orig_tone_path ? orig_tone_path(self, sel, tone_id) : NULL;
 if (waffle_path_readable(path)) {
  return path;
 }
 return waffle_fallback_ringtone(tone_id);
}
static id
waffle_tone_file_path_valid(id self, SEL sel, id tone_id, BOOL *is_valid)
{
 id path = orig_tone_path_valid ? orig_tone_path_valid(self, sel, tone_id, is_valid) : NULL;
 if (waffle_path_readable(path)) {
  return path;
 }
 if (is_valid != NULL) {
  *is_valid = YES;
 }
 return waffle_fallback_ringtone(tone_id);
}
static BOOL
waffle_tone_is_valid(id self, SEL sel, id tone_id)
{
 if (orig_tone_valid && orig_tone_valid(self, sel, tone_id)) {
  return YES;
 }
 return tone_id != NULL ? YES : NO;
}
static void *
waffle_tone_thread(void *arg __unused)
{
 for (unsigned i = 0; i < 120; i++) {
  Class cls = objc_getClass("TLToneManager");
  if (cls != NULL) {
   unsigned hooked = 0;
   Method m1 = class_getInstanceMethod(cls, sel_registerName("filePathForToneIdentifier:"));
   if (m1 != NULL) {
    orig_tone_path = (id (*)(id, SEL, id))method_getImplementation(m1);
    method_setImplementation(m1, (IMP)waffle_tone_file_path);
    hooked++;
   }
   Method m2 = class_getInstanceMethod(cls, sel_registerName("_filePathForToneIdentifier:isValid:"));
   if (m2 != NULL) {
    orig_tone_path_valid = (id (*)(id, SEL, id, BOOL *))method_getImplementation(m2);
    method_setImplementation(m2, (IMP)waffle_tone_file_path_valid);
    hooked++;
   }
   Method m3 = class_getInstanceMethod(cls, sel_registerName("toneWithIdentifierIsValid:"));
   if (m3 != NULL) {
    orig_tone_valid = (BOOL (*)(id, SEL, id))method_getImplementation(m3);
    method_setImplementation(m3, (IMP)waffle_tone_is_valid);
    hooked++;
   }
   if (hooked) {
    say("redwood-tone: hooked TLToneManager in Preferences (%u methods)\n", hooked);
    return NULL;
   }
  }
  usleep(250000);
 }
 return NULL;
}
__attribute__((constructor))
static void
redwood_tweaks_init(void)
{
 static bool done;
 if (done) {
  return;
 }
 done = true;
 load_the_tweaks();
 const char *name = executable_name();
 if (name != NULL && strcmp(name, "Preferences") == 0) {
  pthread_t t;
  if (pthread_create(&t, NULL, waffle_tone_thread, NULL) == 0) {
   pthread_detach(t);
  }
 }
}
