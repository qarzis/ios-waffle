"""Exercise actual cdev and static client source through a host syscall model."""
from pathlib import Path
import importlib.util,re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
def strip(s):return re.sub(r'^#include .*$','',s,flags=re.M)
source=strip((root/'kernel/files/bsd/dev/waffle_gpu_user.c').read_text())
client=strip((root/'userland/src/waffle_gpu_probe.c').read_text())
uapi=strip((root/'kernel/files/bsd/sys/waffle_gpu_user.h').read_text())
ioc=(root/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk/usr/include/sys/ioccom.h').read_text();ioc=ioc[ioc.index('#define IOCPARM_MASK'):ioc.rindex('#endif')]
h=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <setjmp.h>
#include "waffle_gpu_service.h"
#define __printflike(a,b) __attribute__((format(printf,a,b)))
#define LCK_GRP_DECLARE(name,label) unsigned name __attribute__((unused))
#define LCK_MTX_DECLARE(name,group) unsigned name
#define DEVFS_CHAR 1
#define UID_ROOT 0
#define GID_WHEEL 0
#define eno_rdwrt NULL
#define eno_stop NULL
#define eno_reset NULL
#define eno_select NULL
#define eno_mmap NULL
#define eno_strat NULL
#define makedev(a,b) ((dev_t)((a)*256+(b)))
struct proc {int pid;};
struct cdevsw {int (*d_open)(dev_t,int,int,struct proc *);int (*d_close)(dev_t,int,int,struct proc *);void *d_read,*d_write;int (*d_ioctl)(dev_t,unsigned long,char *,int,struct proc *);void *d_stop,*d_reset,*d_select,*d_mmap,*d_strategy;int d_type;};
struct waffle_gpu_context {unsigned fence;};
static struct waffle_gpu_context context;
static unsigned mode,begins,ends,copies,reported,nodes,removes;
static bool held;
static jmp_buf reset_trap,exit_trap;
static struct proc owner={1},foreign={2};
static void lck_mtx_lock(unsigned *p){(void)p;assert(!held);held=true;}
static void lck_mtx_unlock(unsigned *p){(void)p;assert(held);held=false;}
static int proc_pid(struct proc *p){assert(p);return p->pid;}
static int cdevsw_add(int major,const struct cdevsw *sw){assert(major==-1 && sw);return mode==4?-1:42;}
static void cdevsw_remove(int major,const struct cdevsw *sw){assert(major==42 && sw);removes++;}
static void *devfs_make_node(dev_t dev,int type,unsigned uid,unsigned gid,unsigned perm,const char *name){
 assert(dev==42*256 && type==1 && uid==0 && gid==0 && perm==0600 && !strcmp(name,"waffle-gpu-copy"));nodes++;return mode==5?NULL:(void *)1;
}
static void redwood_tl(const char *fmt,...){if(strstr(fmt,"USERDEV report"))reported++;}
static void loader_return(void){longjmp(reset_trap,1);}
struct waffle_gpu_context *waffle_gpu_context_begin(void){assert(held);begins++;context.fence=0;return mode==1?NULL:&context;}
bool waffle_gpu_context_copy(struct waffle_gpu_context *c,struct waffle_gpu_copy_job *job){
 assert(held && c==&context && job && job->words==256);copies++;
 if(mode==2)return false;
 for(unsigned i=0;i<256;i++)job->output[i]=job->input[i];job->fence=++context.fence;return true;
}
bool waffle_gpu_context_end(struct waffle_gpu_context **c){assert(held && c && *c==&context);ends++;if(mode==3)return false;*c=NULL;return true;}
'''
mini=r'''
#define SYS_ioctl 54
#define O_RDWR 2
#define open probe_open
#define close probe_close
#define dup2 probe_dup2
#define getpid probe_getpid
#define getuid probe_getuid
#define reboot probe_reboot
#define main client_main
static int probe_open(const char *path,int flags,int perm){
 (void)perm;assert(flags==2);if(!strcmp(path,"/dev/console"))return 0;
 assert(!strcmp(path,"/dev/waffle-gpu-copy"));int error=user_open(0,flags,0,&owner);if(error){errno=error;return -1;}return 3;
}
static int probe_close(int fd){assert(fd==3);int error=user_close(0,0,0,&owner);if(error){errno=error;return -1;}return 0;}
static int probe_dup2(int fd,int to){assert(fd==0 && (to==1||to==2));return to;}
static int probe_getpid(void){return 1;}
static int probe_getuid(void){return 0;}
static int probe_reboot(int how){assert(how==8);longjmp(exit_trap,1);}
static long mini_syscall(long number,long fd,long command,long data,long d,long e,long f){
 assert(number==54 && fd==3 && !d && !e && !f);if(data==1){errno=EFAULT;return -1;}
 int error=user_ioctl(0,(unsigned long)command,(char *)data,0,&owner);if(error){errno=error;return -1;}return 0;
}
'''
test=r'''
#undef main
int main(void){
 assert(IOCPARM_LEN(WAFFLE_GPU_USER_COPY)==2064 && IOCPARM_LEN(WAFFLE_GPU_USER_REPORT)==20);
 assert(IOCGROUP(WAFFLE_GPU_USER_COPY)=='W');
 assert(waffle_gpu_user_register() && nodes==1);
 mode=4;assert(!waffle_gpu_user_register());mode=5;assert(!waffle_gpu_user_register() && removes==1);mode=0;
 assert(!user_open(0,0,0,&owner) && begins==1);
 assert(user_open(0,0,0,&owner)==EBUSY && begins==1);
 struct waffle_gpu_user_copy q={.version=1,.words=256};
 assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&foreign)==EPERM && !copies);
 q.version=2;assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==EINVAL && !copies);
 q.version=1;q.words=255;assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==EINVAL && !copies);
 q.words=256;q.reserved=1;assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==EINVAL && !copies);
 q.reserved=0;q.fence=1;assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==EINVAL && !copies);q.fence=0;
 assert(user_ioctl(0,WAFFLE_GPU_USER_COPY^1,(char *)&q,0,&owner)==ENOTTY && !copies);
 struct waffle_gpu_user_report report={1,768,0,3,5};
 assert(user_ioctl(0,WAFFLE_GPU_USER_REPORT,(char *)&report,0,&owner)==EINVAL);
 for(unsigned fence=1;fence<=3;fence++){
  q.fence=0;for(unsigned i=0;i<256;i++)q.input[i]=fence*123+i;
  assert(!user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner) && q.fence==fence);
  for(unsigned i=0;i<256;i++)assert(q.output[i]==fence*123+i && q.input[i]==fence*123+i);
 }
 q.fence=0;assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==E2BIG && copies==3);
 report.negative_checks=4;assert(user_ioctl(0,WAFFLE_GPU_USER_REPORT,(char *)&report,0,&owner)==EINVAL);report.negative_checks=5;
 assert(!user_ioctl(0,WAFFLE_GPU_USER_REPORT,(char *)&report,0,&owner) && reported==1);
 assert(!user_close(0,0,0,&owner) && !user_context && ends==1);
 assert(!user_close(0,0,0,&owner) && ends==1);
 mode=1;assert(user_open(0,0,0,&owner)==ENXIO && !user_context);
 mode=0;assert(!user_open(0,0,0,&owner));mode=2;q.fence=0;unsigned before=q.output[0];
 assert(user_ioctl(0,WAFFLE_GPU_USER_COPY,(char *)&q,0,&owner)==EIO && q.fence==0 && q.output[0]==before);
 mode=3;if(!setjmp(reset_trap)){user_close(0,0,0,&owner);assert(0);}assert(user_context==&context && held);
 held=false;user_context=NULL;user_pid=user_fence=0;user_reported=false;mode=0;begins=ends=copies=reported=0;
 if(!setjmp(exit_trap))client_main(0,NULL,NULL);
 assert(begins==1 && copies==3 && ends==1 && reported==1 && !user_context && !held);
 return 0;
}
'''
# Compile actual client program together with cdev to exercise its refusal/report flow.
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+ioc+uapi+source+mini+client+test)
 subprocess.run(['cc','-std=c11','-D_DEFAULT_SOURCE','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=10)
 if result.returncode:raise RuntimeError(result.stdout+result.stderr)
# Acceptance uses actual already-saved GPU jobs, supplemented with user lifecycle markers.
spec=importlib.util.spec_from_file_location('r',root/'scripts/run_waffle_ios.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
text=(root/'work/waffle/runs/20261101T074105Z/kernel-final.log').read_text()
text='USERDEV registered abi=1 pixels=256 mode=0600; no GPU opened\n'+text
text=text.replace('waffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1','SERVICE begin root_live=1 serialized=1\nUSERDEV open pid=1 demand_context=1\nwaffle-gmu: COPY_SEQUENCE begin jobs=3 kernel_caller=1')
negative=['USERDEV busy_open refused=1 pid=1','USERDEV invalid_copy refused=1 pid=1 version=2 words=256','USERDEV invalid_copy refused=1 pid=1 version=1 words=255','USERDEV unknown_ioctl refused=1 pid=1']
text=text.replace('waffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256','\n'.join(negative)+'\nwaffle-gmu: COPY_JOB begin fence=1 seq=44 pixels=256')
for f in (1,2,3):text=text.replace(f'waffle-gmu: COPY_CALLER fence={f} checked=256 wrong=0',f'waffle-gmu: COPY_CALLER fence={f} checked=256 wrong=0\nUSERDEV returned pid=1 fence={f} words=256')
text=text.replace('waffle-gmu: SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session','USERDEV report pid=1 checks=768 wrong=0 fence=3 negative=5\nwaffle-gmu: SESSION result=1 submitted=3 completed=3 next_sequence=47 OOB=1; bounded kernel session')
text+='\nSERVICE end consumed=1 result=1\nUSERDEV close pid=1 passed=1 report=1 context_null=1\n'
assert r.validate_aop_owner_log(text,2,6)==r.extract_copy_jobs(text)[-1]
for marker in [*negative,'USERDEV report pid=1 checks=768 wrong=0 fence=3 negative=5','USERDEV close pid=1 passed=1 report=1 context_null=1']:
 try:r.validate_aop_owner_log(text.replace(marker,''),2,6)
 except RuntimeError:pass
 else:raise AssertionError('Missing user boundary proof accepted')
print('Actual cdev + actual static client source: Darwin IOC layout, owner/size/version/command/limit/refusal gates, 3 returns/report/close, busy retention and five client negative checks passed in host syscall model; real user copyin/copyout still requires hardware')
