#include "mini.h"
int main(int argc,char **argv,char **envp){
 (void)argc;(void)argv;(void)envp;
 int fd=open("/dev/console",O_RDWR,0);if(fd>=0){dup2(fd,0);dup2(fd,1);dup2(fd,2);}
 char *program[]={"/redwood/bin/waffle-unixnu-runtime-probe",NULL};
 char *environment[]={"DYLD_USE_CLOSURES=0","DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld",NULL};
 printf("waffle-unixnu-init: exec runtime probe pid=%d\n",getpid());execve(program[0],program,environment);
 printf("waffle-unixnu-init: exec_failed errno=%d\n",errno);mini_syscall(SYS_reboot,8,0,0,0,0,0);for(;;){}
}
