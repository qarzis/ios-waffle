#include "mini.h"
#include "waffle_gpu_user.h"
static long ioctl_call(int fd,unsigned long command,void *data)
{
    return mini_syscall(SYS_ioctl,fd,command,(long)data,0,0,0);
}
static uint32_t source_pixel(unsigned fence,unsigned pixel)
{
    unsigned x=pixel%16,y=pixel/16;
    uint32_t rgb=((x*37+y*19+11)&255)|(((x*13+y*47+83)&255)<<8)|(((x/4+y/4)%2?255:25)<<16)|0xff000000u;
    const uint32_t masks[]={0x00010101u,0x002a173cu,0x0065ab19u};
    return rgb^masks[fence-1];
}
int main(int argc,char **argv,char **envp)
{
    (void)argc;(void)argv;(void)envp;
    int console=open("/dev/console",O_RDWR,0);
    if(console>=0){dup2(console,1);dup2(console,2);}
    printf("waffle-user: started pid=%d uid=%d\n",getpid(),getuid());
    int fd=open("/dev/waffle-gpu-copy",O_RDWR,0),ok=fd>=0,negative=0;
    struct waffle_gpu_user_copy request;
    if(fd<0){printf("waffle-user: open failed errno=%d\n",errno);goto finish;}
    int second=open("/dev/waffle-gpu-copy",O_RDWR,0);
    if(second<0 && errno==16)negative++;else{ok=0;if(second>=0)close(second);}
    memset(&request,0,sizeof(request));request.version=2;request.words=256;
    if(ioctl_call(fd,WAFFLE_GPU_USER_COPY,&request)==-1 && errno==22)negative++;else ok=0;
    request.version=1;request.words=255;
    if(ioctl_call(fd,WAFFLE_GPU_USER_COPY,&request)==-1 && errno==22)negative++;else ok=0;
    if(ioctl_call(fd,WAFFLE_GPU_USER_COPY,(void *)1)==-1 && errno==14)negative++;else ok=0;
    if(ioctl_call(fd,WAFFLE_GPU_USER_COPY^1u,&request)==-1 && errno==25)negative++;else ok=0;
    unsigned checks=0,wrong=0;
    for(unsigned fence=1;fence<=3 && ok;fence++){
        memset(&request,0,sizeof(request));request.version=1;request.words=256;
        for(unsigned i=0;i<256;i++){request.input[i]=source_pixel(fence,i);request.output[i]=0xbad00000u+i;}
        if(ioctl_call(fd,WAFFLE_GPU_USER_COPY,&request) || request.fence!=fence){ok=0;break;}
        for(unsigned i=0;i<256;i++){checks++;if(request.output[i]!=source_pixel(fence,i) || request.input[i]!=source_pixel(fence,i))wrong++;}
        printf("waffle-user: fence=%u checks=%u wrong=%u\n",fence,checks,wrong);
    }
    if(ok && checks==768 && !wrong && negative==5){
        struct waffle_gpu_user_report report={1,checks,wrong,3,negative};
        if(ioctl_call(fd,WAFFLE_GPU_USER_REPORT,&report))ok=0;
    }else ok=0;
    if(close(fd))ok=0;
finish:
    printf("waffle-user: passed=%d negative=%d; halting\n",ok,negative);
    reboot(0x08);
    for(;;);
}
