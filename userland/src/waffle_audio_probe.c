#include "mini.h"

int main(int argc, char **argv, char **envp)
{
 (void)argc; (void)argv; (void)envp;
 int console = open("/dev/console", O_RDWR, 0);
 if (console >= 0) { dup2(console, 0); dup2(console, 1); dup2(console, 2); }
 printf("waffle-audio-probe: PID1 ready; firmware-only test, no PCM playback\n");
 uint64_t last = 0;
 for (;;) {
#ifdef WAFFLE_BATTERY_REPORT_TEST
  uint64_t updates = 0;
  size_t size = sizeof(updates);
  if (sysctlbyname("kern.redwood.battery_updates", &updates, &size, NULL, 0) == 0 && updates != last) {
   int soc = -1, temp = -273;
   size = sizeof(soc);sysctlbyname("kern.redwood.battery_soc", &soc, &size, NULL, 0);
   size = sizeof(temp);sysctlbyname("kern.redwood.battery_temperature_c", &temp, &size, NULL, 0);
   printf("waffle-battery-pid1: updates=%llu soc=%d temperature_c=%d read_only=1\n", (unsigned long long)updates, soc, temp);
   last = updates;
  }
#else
  (void)last;
#endif
  usleep(1000000);
 }
}
