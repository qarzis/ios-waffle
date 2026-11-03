/* Read-only display-service inventory. Never opens a user client or sets a property. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <stdio.h>
#include <unistd.h>

static void inventory(const char *label, CFMutableDictionaryRef match)
{
 io_iterator_t iterator = IO_OBJECT_NULL;
 kern_return_t kr = match ? IOServiceGetMatchingServices(kIOMainPortDefault, match, &iterator) : KERN_FAILURE;
 unsigned count = 0;
 printf("waffle-brightness: match=%s status=%x\n", label, kr);
 if (kr != KERN_SUCCESS) return;
 io_service_t service;
 while (count < 16 && (service = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
  io_name_t name = {0}, cls = {0};
  uint64_t entry = 0;
  IORegistryEntryGetName(service, name);
  IOObjectGetClass(service, cls);
  IORegistryEntryGetRegistryEntryID(service, &entry);
  printf("waffle-brightness: service match=%s index=%u id=%llu name=%s class=%s\n",
      label, count++, (unsigned long long)entry, name, cls);
  const CFStringRef keys[] = {CFSTR("backlight-control"), CFSTR("IOClass"), CFSTR("IOProviderClass"),
      CFSTR("IOMFBDisplayType"), CFSTR("IOMFBDisplaySize"), CFSTR("IOMFBDisplayRefresh"),
      CFSTR("built-in"), CFSTR("brightness"), CFSTR("backlight"), CFSTR("IOUserClientClass")};
  for (unsigned i = 0; i < sizeof(keys)/sizeof(keys[0]); ++i) {
   char key[96] = {0}, text[384] = {0};
   CFStringGetCString(keys[i], key, sizeof(key), kCFStringEncodingUTF8);
   CFTypeRef value = IORegistryEntryCreateCFProperty(service, keys[i], kCFAllocatorDefault, 0);
   if (!value) {printf("waffle-brightness: property id=%llu key=%s absent=1\n", (unsigned long long)entry, key);continue;}
   CFStringRef description = CFCopyDescription(value);
   if (!description || !CFStringGetCString(description, text, sizeof(text), kCFStringEncodingUTF8))
    snprintf(text, sizeof(text), "<value exceeds log bound>");
   for (char *p = text; *p; ++p) if (*p == '\n' || *p == '\r') *p = ' ';
   printf("waffle-brightness: property id=%llu key=%s type=%lu value=%s\n",
       (unsigned long long)entry, key, (unsigned long)CFGetTypeID(value), text);
   if (description) CFRelease(description);
   CFRelease(value);
  }
  IOObjectRelease(service);
 }
 IOObjectRelease(iterator);
 printf("waffle-brightness: done match=%s count=%u limit=16 read_only=1\n", label, count);
}
int main(void)
{
 setbuf(stdout, NULL);
 sleep(35);
 printf("waffle-brightness: begin read_only=1 no_userclient=1 no_property_writes=1\n");
 const void *key = CFSTR("backlight-control"), *value = kCFBooleanTrue;
 CFDictionaryRef properties = CFDictionaryCreate(kCFAllocatorDefault, &key, &value, 1,
      &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
 CFMutableDictionaryRef match = CFDictionaryCreateMutable(kCFAllocatorDefault, 1,
      &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
 if (properties && match) CFDictionarySetValue(match, CFSTR("IOPropertyMatch"), properties);
 if (properties) CFRelease(properties);
 if (!properties) {if (match) CFRelease(match);match=NULL;}
 inventory("backlight-control=true", match);
 inventory("IOMobileFramebuffer", IOServiceMatching("IOMobileFramebuffer"));
 inventory("AppleCLCD", IOServiceMatching("AppleCLCD"));
 printf("waffle-brightness: complete read_only=1\n");
 return 0;
}
