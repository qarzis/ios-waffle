/* Bounded process CPU accounting; no GL interception or GPU clock changes. */
#include <dispatch/dispatch.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>
static dispatch_source_t cpu_timer;
static mach_timebase_info_data_t cpu_timebase;
static uint64_t last_ticks, last_cpu;
static unsigned cpu_samples;
static int process_cpu(uint64_t *value)
{
 struct rusage usage;
 if (getrusage(RUSAGE_SELF, &usage) != 0) return -1;
 *value = ((uint64_t)usage.ru_utime.tv_sec + (uint64_t)usage.ru_stime.tv_sec) * 1000000 +
     (uint64_t)usage.ru_utime.tv_usec + (uint64_t)usage.ru_stime.tv_usec;
 return 0;
}
__attribute__((constructor)) static void start(void)
{
 if (strcmp(getprogname(), "backboardd")) return;
 if (mach_timebase_info(&cpu_timebase) != 0 || !cpu_timebase.denom || process_cpu(&last_cpu)) return;
 last_ticks = mach_absolute_time();
 cpu_timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0,
     dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_LOW, 0));
 if (!cpu_timer) return;
 dispatch_source_set_timer(cpu_timer, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC),
     NSEC_PER_SEC, 100 * NSEC_PER_MSEC);
 dispatch_source_set_event_handler(cpu_timer, ^{
  uint64_t ticks = mach_absolute_time(), cpu;
  if (process_cpu(&cpu) || ticks <= last_ticks || cpu < last_cpu) {
   dprintf(STDERR_FILENO, "waffle-process-cpu: pid=%d invalid_sample=1 stopped=1\n", getpid());
   dispatch_source_cancel(cpu_timer);return;
  }
  uint64_t wall = (ticks - last_ticks) * cpu_timebase.numer / cpu_timebase.denom / 1000;
  dprintf(STDERR_FILENO, "waffle-process-cpu: pid=%d sample=%u cpu_us=%llu wall_us=%llu all_threads=1 no_GPU_timing=1\n",
      getpid(), ++cpu_samples, (unsigned long long)(cpu - last_cpu), (unsigned long long)wall);
  last_ticks = ticks;last_cpu = cpu;
  if (cpu_samples >= 60) dispatch_source_cancel(cpu_timer);
 });
 dispatch_resume(cpu_timer);
}
