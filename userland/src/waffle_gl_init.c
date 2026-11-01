#include "mini.h"
int main(int argc,char **argv,char **envp)
{
 (void)argc;(void)argv;(void)envp;
 int fd=open("/dev/console",O_RDWR,0);if(fd>=0){dup2(fd,0);dup2(fd,1);dup2(fd,2);}
 char *program[]={"/redwood/bin/waffle-gl-probe",NULL};
 char *environment[]={"WAFFLE_GPU_DRM=1","OSMESA_SOFTWARE=0","MESA_SHADER_CACHE_DISABLE=true","GALLIUM_THREAD=0","DYLD_USE_CLOSURES=0",NULL};
 printf("waffle-gl-init: exec actual Darwin Mesa probe pid=%d\n",getpid());
 execve(program[0],program,environment);
 printf("waffle-gl-init: exec failed errno=%d\n",errno);
 mini_syscall(SYS_reboot,8,0,0,0,0,0);for(;;){}
}
