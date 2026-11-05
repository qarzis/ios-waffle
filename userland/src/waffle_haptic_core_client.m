/* Bounded interface test: system vibration request, then three PCM onsets.
 * The direct fallback is logged separately and cannot prove system routing. */
#include <AudioToolbox/AudioToolbox.h>
#import <Foundation/Foundation.h>
#import <CoreHaptics/CoreHaptics.h>
#include <CoreFoundation/CoreFoundation.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static bool completed;
static void finished(SystemSoundID sound,void *context)
{
 (void)context;completed=true;
 printf("waffle-haptic-client: system_completed=%u\n",(unsigned)sound);fflush(stdout);
 CFRunLoopStop(CFRunLoopGetCurrent());
}
static void core_haptic_probe(void)
{
 @autoreleasepool {
  printf("waffle-haptic-client: CoreHaptics_begin=1\n");fflush(stdout);
  BOOL supports=[CHHapticEngine capabilitiesForHardware].supportsHaptics;
  printf("waffle-haptic-client: CoreHaptics_supports=%u\n",supports);fflush(stdout);
  NSError *error=nil;
  CHHapticEngine *engine=[[CHHapticEngine alloc] initAndReturnError:&error];
  if(!engine){printf("waffle-haptic-client: CoreHaptics_init_error=%ld\n",(long)error.code);return;}
  if(![engine startAndReturnError:&error]){printf("waffle-haptic-client: CoreHaptics_start_error=%ld\n",(long)error.code);return;}
  CHHapticEventParameter *intensity=[[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticIntensity value:0.5];
  CHHapticEvent *event=[[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticTransient parameters:@[intensity] relativeTime:0];
  CHHapticPattern *pattern=[[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
  id<CHHapticPatternPlayer> player=pattern?[engine createPlayerWithPattern:pattern error:&error]:nil;
  BOOL played=player && [player startAtTime:CHHapticTimeImmediate error:&error];
  printf("waffle-haptic-client: CoreHaptics_play=%u error=%ld\n",played,(long)error.code);fflush(stdout);
  CFRunLoopRunInMode(kCFRunLoopDefaultMode,2,false);
  [engine stopWithCompletionHandler:nil];
 }
}
int main(int argc,char **argv)
{
 printf("waffle-haptic-client: main_entered=1\n");fflush(stdout);
 bool direct_only=argc>1 && !strcmp(argv[1],"--direct-only");
 sleep(direct_only?47:35);
 if(!direct_only) {
 core_haptic_probe();
 const SystemSoundID sounds[]={kSystemSoundID_Vibrate};
 for(unsigned i=0;i<sizeof(sounds)/sizeof(sounds[0]);i++) {
  completed=false;
  printf("waffle-haptic-client: completion_register_begin=%u\n",(unsigned)sounds[i]);fflush(stdout);
  OSStatus status=AudioServicesAddSystemSoundCompletion(sounds[i],CFRunLoopGetCurrent(),kCFRunLoopCommonModes,finished,NULL);
  printf("waffle-haptic-client: system_begin=%u completion_registration=%d\n",(unsigned)sounds[i],(int)status);fflush(stdout);
  AudioServicesPlaySystemSound(sounds[i]);
  CFRunLoopRunInMode(kCFRunLoopDefaultMode,5,false);
  printf("waffle-haptic-client: system_end=%u completed=%u\n",(unsigned)sounds[i],completed);fflush(stdout);
  AudioServicesRemoveSystemSoundCompletion(sounds[i]);
  sleep(1);
 }
  return 0;
 }
 int fd=open("/dev/redwood-haptic",O_WRONLY|O_NONBLOCK);
 if(fd<0){printf("waffle-haptic-client: open_error=%d\n",errno);return 1;}
 int16_t tap[256],silence[256]={0};
 for(unsigned i=0;i<256;i++)tap[i]=(i&1)?4096:-4096;
 printf("waffle-haptic-client: direct_begin=1\n");fflush(stdout);
 unsigned taps=0,errors=0;
 for(unsigned i=0;i<3;i++){
  if(write(fd,tap,sizeof(tap))==sizeof(tap))taps++;else errors++;
  if(write(fd,silence,sizeof(silence))!=sizeof(silence))errors++;
  usleep(250000);
 }
 close(fd);printf("waffle-haptic-client: direct_taps=%u errors=%u\n",taps,errors);return errors?1:0;
}
