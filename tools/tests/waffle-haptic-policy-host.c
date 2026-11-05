#include <assert.h>
#include <stdio.h>
#include "../../loader/waffle.h"
int main(void){
 const char *good="-v bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1";
#if defined(WAFFLE_USERLAND) && defined(WAFFLE_HAPTIC_PULSE_TEST)
 assert(waffle_cmdline_allowed(good));
 const char *ui="bootcpu=7 cpus=1 loader_return_after=120 waffle_torch=3 waffle_haptic_test=2 waffle_vsync=1 waffle_display_present=1 waffle_gpu=94 waffle_lpac_map=1 waffle_zap=1 waffle_writeback=1 waffle_ib=1 waffle_session=1 waffle_dynamic_bo=1 waffle_compute=2 waffle_image=13";
 assert(waffle_cmdline_allowed(ui)&&waffle_haptic_service_requested(ui));
 assert(!waffle_haptic_service_requested(good));
 assert(waffle_haptic_service_requested("bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2"));
 assert(waffle_cmdline_allowed("bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2"));
#else
 assert(!waffle_cmdline_allowed(good));
 assert(!waffle_haptic_service_requested("cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2"));
#endif
 const char *bad[]={"waffle_haptic_test=1","cpus=1 waffle_torch=1 waffle_haptic_test=1","cpus=2 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1","cpus=1 loader_return_after=60 waffle_torch=2 waffle_haptic_test=1","cpus=1 loader_return_after=60 waffle_torch=3 waffle_haptic_test=1","cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=3","cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1 waffle_haptic_test=1","cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1 adsp=8","cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1 waffle_gpu=94","cpus=1 loader_return_after=91 waffle_torch=1 waffle_haptic_test=1","cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1 waffle_vsync=1"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(!waffle_cmdline_allowed(bad[i]));
 assert(!waffle_haptic_service_requested("cpus=2 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2"));
 assert(!waffle_haptic_service_requested("cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=20"));
 assert(!waffle_haptic_service_requested("cpus=1 loader_return_after=60 waffle_torch=1"));
 puts("PASS native haptic loader policy: dedicated build only, CPU1, bounded return, read-only flash; duplicate/mixed/audio/GPU/long requests refused.");}
