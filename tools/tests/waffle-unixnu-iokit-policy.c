#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../loader/platform.h"
#include "../../loader/waffle.h"
int main(void){
 const char *chain="waffle_gpu=94 waffle_lpac_map=1 waffle_zap=1 waffle_writeback=1 waffle_ib=1 waffle_session=1 waffle_dynamic_bo=1 waffle_compute=2 waffle_image=13";
 char cmd[2048];
 snprintf(cmd,sizeof(cmd),"%s cpus=1 loader_return_after=90 waffle_unixnu_iokit=1",chain);
#ifdef WAFFLE_USERLAND
 assert(waffle_cmdline_allowed(cmd));
 snprintf(cmd,sizeof(cmd),"%s cpus=1 loader_return_after=91 waffle_unixnu_iokit=1",chain);assert(!waffle_cmdline_allowed(cmd));
 snprintf(cmd,sizeof(cmd),"%s cpus=2 loader_return_after=60 waffle_unixnu_iokit=1",chain);assert(!waffle_cmdline_allowed(cmd));
 snprintf(cmd,sizeof(cmd),"%s cpus=1 loader_return_after=60 waffle_unixnu_iokit=1 waffle_unixnu_iokit=1",chain);assert(!waffle_cmdline_allowed(cmd));
 snprintf(cmd,sizeof(cmd),"%s cpus=1 loader_return_after=60 waffle_unixnu_iokit=1 waffle_display_present=1",chain);assert(!waffle_cmdline_allowed(cmd));
 snprintf(cmd,sizeof(cmd),"%s cpus=1 loader_return_after=60 waffle_unixnu_iokit=2",chain);assert(!waffle_cmdline_allowed(cmd));
 assert(!waffle_cmdline_allowed("cpus=1 loader_return_after=60 waffle_unixnu_iokit=1"));
#else
 assert(!waffle_cmdline_allowed(cmd));
#endif
 return 0;
}
