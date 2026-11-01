#include "mini.h"
#include "waffle_gpu_msm.h"
#include "waffle_gpu_data.h"
#ifdef WAFFLE_MSM_PROBE
int drmOpenWithType(const char *,const char *,int);
int drmIoctl(int,unsigned long,void *);
int drmCommandWrite(int,unsigned long,const void *,unsigned long);
int drmCommandWriteRead(int,unsigned long,void *,unsigned long);
static int open_gpu(void){return drmOpenWithType("waffle-msm-probe",0,2);}
static long call(int fd,unsigned long op,void *r){
 int result;
 if(op==WAFFLE_MSM_NEW || op==WAFFLE_MSM_INFO || op==WAFFLE_MSM_SUBMIT){
  result=drmCommandWriteRead(fd,(op&255)-0x40,r,IOCPARM_LEN(op));
 }else if(op==WAFFLE_MSM_WAIT){result=drmCommandWrite(fd,7,r,sizeof(struct waffle_msm_wait));}
 else return drmIoctl(fd,op,r);
 if(result<0){errno=-result;return -1;}return result;
}
#else
static int open_gpu(void){return open("/dev/waffle-gpu-msm",O_RDWR,0);}
static long call(int fd,unsigned long op,void *r){return mini_syscall(SYS_ioctl,fd,op,(long)r,0,0,0);}
#endif
#ifdef WAFFLE_MSM_MAP_PROBE
void *redwood_drm_map(int,uint32_t,uint64_t);
static int transfer(int fd,unsigned long op,unsigned handle,void *ptr,unsigned bytes){
 if(bytes!=16384)return -1;
 if(op==WAFFLE_MSM_UPLOAD){
  void *mapped=redwood_drm_map(fd,handle,bytes);if(mapped==(void *)-1)return -1;
  memcpy(mapped,ptr,bytes);return 0; /* Submit revokes before validation. */
 }
 struct waffle_msm_map r={.handle=handle,.bytes=bytes,.flags=1};
 if(call(fd,WAFFLE_MSM_MAP,&r))return -1;
 memcpy(ptr,(const void *)(uintptr_t)r.address,bytes);
 return call(fd,WAFFLE_MSM_UNMAP,&r);
}
#else
static int transfer(int fd,unsigned long op,unsigned handle,void *ptr,unsigned bytes){
 struct waffle_msm_transfer r={.pointer=(uint64_t)(uintptr_t)ptr,.handle=handle,.bytes=bytes};return call(fd,op,&r);
}
#endif
int main(int argc,char **argv,char **envp)
{
 (void)argc;(void)argv;(void)envp;
#ifdef WAFFLE_MSM_PROBE
 /* Marker qualifies actual shim use only together with the GPU result proof. */
#endif
 int console=open("/dev/console",O_RDWR,0);if(console>=0){dup2(console,1);dup2(console,2);}
#ifdef WAFFLE_MSM_PROBE
 printf("waffle-mesa-probe: transport=actual_drm_shim command_api=1 ioctl_api=1\n");
#endif
#ifdef WAFFLE_MSM_MAP_PROBE
 printf("waffle-mesa-probe: mapped_bo=1 upload_download_copy=0 handoff=unmap_before_submit\n");
#endif
 int fd=open_gpu(),ok=fd>=0;unsigned negative=0,checks=0,wrong=0;
 uint32_t command[4096],data[4096],input[256];uint64_t va[2]={0};
 if(!ok)goto finish;
 int second=open_gpu();if(second<0 && errno==16)negative++;else{ok=0;if(second>=0)close(second);}
 struct waffle_msm_gem_new bad={.size=4096};if(call(fd,WAFFLE_MSM_NEW,&bad)==-1 && errno==22)negative++;else ok=0;
 for(unsigned h=1;h<=2;h++){
  struct waffle_msm_gem_new r={.size=16384};if(call(fd,WAFFLE_MSM_NEW,&r) || r.handle!=h){ok=0;goto finish;}
  struct waffle_msm_gem_info info={.handle=h,.info=1};if(call(fd,WAFFLE_MSM_INFO,&info)){ok=0;goto finish;}va[h-1]=info.value;
 }
 if(va[0]!=0x1ff8000478000ULL || va[1]!=0x100000000ULL)ok=0;
 struct waffle_msm_gem_info unknown={.handle=3,.info=1};if(call(fd,WAFFLE_MSM_INFO,&unknown)==-1 && errno==22)negative++;else ok=0;
 struct waffle_msm_wait future={.fence=1};if(call(fd,WAFFLE_MSM_WAIT,&future)==-1 && errno==22)negative++;else ok=0;
 struct waffle_msm_transfer invalid={.pointer=1,.handle=1,.bytes=4};if(call(fd,WAFFLE_MSM_UPLOAD,&invalid)==-1 && errno==14)negative++;else ok=0;
 invalid.pointer=(uint64_t)(uintptr_t)data;invalid.offset=16380;invalid.bytes=8;
 if(call(fd,WAFFLE_MSM_UPLOAD,&invalid)==-1 && errno==22)negative++;else ok=0;
 for(unsigned fence=1;fence<=3 && ok;fence++){
  for(unsigned i=0;i<256;i++)input[i]=waffle_job_test_pixel(fence,i);
  for(unsigned i=0;i<4096;i++){command[i]=waffle_glsl_command_word(fence,i,va[1],false,false);data[i]=waffle_data_word(input,i,false);}
  struct waffle_msm_submit_bo bos[2]={{.flags=1,.handle=1,.presumed=va[0]},{.flags=3,.handle=2,.presumed=va[1]}};
  struct waffle_msm_submit_cmd cmd={.type=1,.submit_offset=1024,.size=WAFFLE_GLSL_WORDS*4};
  struct waffle_msm_submit r={.flags=0x10,.nr_bos=2,.nr_cmds=1,.bos=(uint64_t)(uintptr_t)bos,.cmds=(uint64_t)(uintptr_t)&cmd};
  if(fence==1){command[256]^=1;if(transfer(fd,WAFFLE_MSM_UPLOAD,1,command,sizeof(command)) || transfer(fd,WAFFLE_MSM_UPLOAD,2,data,sizeof(data))){ok=0;break;}
   if(call(fd,WAFFLE_MSM_SUBMIT,&r)==-1 && errno==22 && !r.fence)negative++;else ok=0;command[256]^=1;
  }
  if(transfer(fd,WAFFLE_MSM_UPLOAD,1,command,sizeof(command)) || transfer(fd,WAFFLE_MSM_UPLOAD,2,data,sizeof(data)) || call(fd,WAFFLE_MSM_SUBMIT,&r) || r.fence!=fence){ok=0;break;}
  struct waffle_msm_wait wait={.fence=fence};if(call(fd,WAFFLE_MSM_WAIT,&wait)){ok=0;break;}
  for(unsigned i=0;i<4096;i++)data[i]=0xbad00000u+i;
  if(transfer(fd,WAFFLE_MSM_DOWNLOAD,2,data,sizeof(data))){ok=0;break;}
  for(unsigned i=0;i<256;i++){checks++;if(data[i]!=input[i])wrong++;}
 }
 if(ok && checks==768 && !wrong && negative==7){struct waffle_msm_report r={1,checks,wrong,3,negative};if(call(fd,WAFFLE_MSM_REPORT,&r))ok=0;}else ok=0;
 for(unsigned h=1;h<=2;h++){struct waffle_msm_close r={.handle=h};if(call(fd,WAFFLE_MSM_CLOSE,&r))ok=0;}
finish:
 if(fd>=0 && close(fd))ok=0;
 printf("waffle-msm-user: result=%d checks=%u wrong=%u negative=%u\n",ok,checks,wrong,negative);
 mini_syscall(SYS_reboot,8,0,0,0,0,0);for(;;){}
}
