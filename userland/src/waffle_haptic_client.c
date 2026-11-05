/* Bounded interface test: system vibration request, then three PCM onsets.
 * The direct fallback is logged separately and cannot prove system routing. */
#include <AudioToolbox/AudioToolbox.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
int main(void)
{
 sleep(35);
 AudioServicesPlaySystemSound(kSystemSoundID_Vibrate);
 printf("waffle-haptic-client: system_vibrate_requested=1\n");fflush(stdout);
 sleep(5);
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
