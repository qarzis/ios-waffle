/* Isolated RAM UI experiment. Preserve the normal init/launchd path. */
#include "mini.h"
int main(int argc,char **argv,char **envp)
{
 (void)argc;(void)argv;
 int console=open("/dev/console",O_RDWR,0);
 if(console>=0){dup2(console,0);dup2(console,1);dup2(console,2);}
 /* backboardd's stock launch job runs as mobile. This applies only to the
  * temporary devfs node in this RAM boot, with no group/world access. */
 int owner=mini_syscall(SYS_chown,(long)"/dev/waffle-gpu-drm",501,501,0,0,0);
 int mode=mini_syscall(SYS_chmod,(long)"/dev/waffle-gpu-drm",0600,0,0,0,0);
 printf("waffle-ui-init: GPU device owner=501 mode=600 chown=%d chmod=%d RAM_only=1\n",owner,mode);
 if(owner || mode){mini_syscall(SYS_reboot,8,0,0,0,0,0);for(;;){}}
 char *program[]={"/redwood/sbin/init.real",NULL};
 printf("waffle-ui-init: exec normal init and real launchd/UI\n");
 execve(program[0],program,envp);
 printf("waffle-ui-init: exec failed errno=%d\n",errno);
 mini_syscall(SYS_reboot,8,0,0,0,0,0);for(;;){}
}
