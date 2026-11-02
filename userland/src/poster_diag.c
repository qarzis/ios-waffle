/* Bounded, read-only sampling of wallpaper processes during RAM bring-up. */
#include <mach/mach.h>
#include <mach/arm/thread_status.h>
#include <mach-o/dyld_images.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdbool.h>
#include <notify.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
/* libproc's private header is absent from the public iOS SDK. */
extern int proc_listallpids(void *, int);
extern int proc_name(int, void *, uint32_t);

static int read_remote(task_t task, uint64_t address, void *out, size_t size)
{
 vm_size_t got = 0;
 return address && vm_read_overwrite(task, address, size,
     (vm_address_t)out, &got) == KERN_SUCCESS && got == size;
}
static void sample(pid_t pid, const char *name)
{
 task_t task = MACH_PORT_NULL;
 kern_return_t kr = task_for_pid(mach_task_self(), pid, &task);
 if (kr != KERN_SUCCESS) {
  printf("poster-diag: %s[%d] task_for_pid=%d\n", name, pid, kr);
  return;
 }
 struct task_dyld_info ti;
 mach_msg_type_number_t tc = TASK_DYLD_INFO_COUNT;
 struct dyld_all_image_infos images = {0};
 uint64_t slide = 0;
 if (task_info(task, TASK_DYLD_INFO, (task_info_t)&ti, &tc) == KERN_SUCCESS &&
     read_remote(task, ti.all_image_info_addr, &images, sizeof(images)))
  slide = images.sharedCacheSlide;
 thread_act_array_t threads = NULL;
 mach_msg_type_number_t count = 0;
 kr = task_threads(task, &threads, &count);
 printf("poster-diag: %s[%d] threads=%u kr=%d slide=%llx dyld=%p\n",
     name, pid, count, kr, slide, images.dyldImageLoadAddress);
 if (kr != KERN_SUCCESS) goto done;
 for (unsigned i = 0; i < count && i < 24; ++i) {
  arm_thread_state64_t state;
  mach_msg_type_number_t sc = ARM_THREAD_STATE64_COUNT;
  struct thread_basic_info bi = {0};
  mach_msg_type_number_t bc = THREAD_BASIC_INFO_COUNT;
  (void)thread_info(threads[i], THREAD_BASIC_INFO, (thread_info_t)&bi, &bc);
  kr = thread_get_state(threads[i], ARM_THREAD_STATE64, (thread_state_t)&state, &sc);
  if (kr != KERN_SUCCESS) {
   printf("poster-diag: thread%u run=%d suspend=%d no-state=%d\n", i, bi.run_state, bi.suspend_count, kr);
   continue;
  }
  uint64_t fp = arm_thread_state64_get_fp(state);
  printf("poster-diag: thread%u run=%d suspend=%d pc=%llx lr=%llx stack",
      i, bi.run_state, bi.suspend_count,
      (uint64_t)arm_thread_state64_get_pc(state) - slide,
      (uint64_t)arm_thread_state64_get_lr(state) - slide);
  for (unsigned j = 0; j < 12; ++j) {
   uint64_t frame[2];
   if ((fp & 15) || !read_remote(task, fp, frame, sizeof(frame))) break;
   printf(" %llx", frame[1] - slide);
   if (frame[0] <= fp || frame[0] - fp > 0x100000) break;
   fp = frame[0];
  }
  putchar('\n');
 }
 for (unsigned i = 0; i < count; ++i) mach_port_deallocate(mach_task_self(), threads[i]);
 vm_deallocate(mach_task_self(), (vm_address_t)threads, count * sizeof(*threads));
done:
 mach_port_deallocate(mach_task_self(), task);
}
int main(int argc,char **argv)
{
 bool focus_only=argc==2 && strcmp(argv[1],"--focus")==0;
 bool layers_only=argc==2 && strcmp(argv[1],"--layers")==0;
 if (argc!=1 && !layers_only && !focus_only) return 2;
 int fd = open("/dev/console", O_WRONLY);
 if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
 setvbuf(stdout, NULL, _IOLBF, 0);
 /* No task/thread suspension, memory writes or changes to scheduling. */
 if(focus_only)sleep(30);
 for (unsigned tick = 0; tick < (focus_only?3u:layers_only?120u:60u); ++tick) {
  if (layers_only) {
   if (tick==15 || tick==45 || tick==90)
    printf("poster-diag: scene/layer snapshot at %us notification=%u\n",tick*2,
        notify_post("com.redwood.poster.layers"));
   sleep(2);
   continue;
  }
  pid_t pids[1024];
  int n = proc_listallpids(pids, sizeof(pids));
  if (n > 1024) n = 1024;
  printf("poster-diag: sample %u processes=%d\n", tick, n);
  for (int i = 0; i < n; ++i) {
   char name[128] = {0};
   if (proc_name(pids[i], name, sizeof(name)) > 0 && (focus_only?strcmp(name,"donotdisturbd")==0:strstr(name,"Poster")!=NULL))
    sample(pids[i], name);
  }
  sleep(focus_only?15:2);
 }
 return 0;
}
