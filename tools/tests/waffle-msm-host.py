"""Actual MSM boundary and actual Darwin probe; GPU modeled separately in session tests."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
def strip(s):return re.sub(r'^#include .*$','',s,flags=re.M)
parts={'__file__':str(root/'tools/tests/waffle-user-host.py')};old=(root/'tools/tests/waffle-user-host.py').read_text();exec(old[:old.index('with tempfile.TemporaryDirectory()')],parts)
h='#define _DEFAULT_SOURCE\n'+parts['h'][:parts['h'].index('static int proc_pid')]
h+=r'''
static uint32_t arenas[2][4096];
static unsigned map_count,unmap_count;
static bool PE_parse_boot_argn(const char *n,void *v,unsigned z){assert(!strcmp(n,"waffle_image") && z==4);*(unsigned *)v=11;return true;}
static bool waffle_gpu_map_create(uintptr_t memory,bool ro,uint64_t *va,uintptr_t *token){(void)ro;assert(held && memory && !*token);*va=memory;*token=memory;map_count++;return true;}
static bool waffle_gpu_map_revoke(uintptr_t *token){assert(held && token);if(*token)unmap_count++;*token=0;return true;}

static int proc_pid(struct proc *p){return p->pid;}
static int cdevsw_add(int major,const struct cdevsw *sw){assert(major==-1 && sw);return mode==4?-1:42;}
static void cdevsw_remove(int major,const struct cdevsw *sw){assert(major==42 && sw);removes++;}
static void *devfs_make_node(dev_t d,int t,unsigned u,unsigned g,unsigned perm,const char *name){assert(d==42*256 && t==1 && !u && !g && perm==0600 && !strcmp(name,"waffle-gpu-msm"));nodes++;return mode==5?NULL:(void *)1;}
static void redwood_tl(const char *fmt,...){if(strstr(fmt,"MSM report"))reported++;}
static void loader_return(void){longjmp(reset_trap,1);}
static int copyin(uint64_t address,void *out,unsigned bytes){if(address<4096)return 14;memcpy(out,(void *)(uintptr_t)address,bytes);return 0;}
static int copyout(const void *in,uint64_t address,unsigned bytes){if(address<4096)return 14;memcpy((void *)(uintptr_t)address,in,bytes);return 0;}
struct waffle_gpu_context *waffle_gpu_context_begin(void){assert(held);begins++;context.fence=0;return mode==1?NULL:&context;}
bool waffle_gpu_context_buffers(struct waffle_gpu_context *c,struct waffle_gpu_buffer b[2]){
 assert(held && c==&context);b[0]=(struct waffle_gpu_buffer){0x1ff8000478000ULL,(uintptr_t)arenas[0],16384,false};b[1]=(struct waffle_gpu_buffer){0x100000000ULL,(uintptr_t)arenas[1],16384,false};return mode!=6;
}
bool waffle_gpu_context_copy(struct waffle_gpu_context *c,struct waffle_gpu_copy_job *job){
 assert(held && c==&context && job->uploaded && job->words==256);copies++;if(mode==2)return false;
 for(unsigned i=0;i<256;i++){assert(arenas[1][256+i]==job->input[i]);arenas[1][i]=job->output[i]=job->input[i];}
 job->fence=++context.fence;arenas[0][2048]=job->fence;return true;
}
bool waffle_gpu_context_end(struct waffle_gpu_context **c){assert(held && c && *c==&context);ends++;if(mode==3)return false;*c=NULL;return true;}
'''
mini='#define SYS_reboot 55\n'+parts['mini'].replace('user_open','msm_open').replace('user_close','msm_close').replace('user_ioctl','msm_ioctl').replace('waffle-gpu-copy','waffle-gpu-msm')
mini=mini.replace('assert(number==54 && fd==3 && !d && !e && !f);','if(number==55){assert(fd==8);longjmp(exit_trap,1);}assert(number==54 && fd==3 && !d && !e && !f);')
test=r'''
#undef main
int main(void){
 assert(IOCPARM_LEN(WAFFLE_MSM_SUBMIT)==72 && IOCPARM_LEN(WAFFLE_MSM_NEW)==16 && IOCPARM_LEN(WAFFLE_MSM_INFO)==24);
 assert(waffle_gpu_msm_register());mode=4;assert(!waffle_gpu_msm_register());mode=5;assert(!waffle_gpu_msm_register() && removes==1);mode=0;
 if(!setjmp(exit_trap))client_main(0,NULL,NULL);
 assert(copies==3 && reported==1 && context.fence==3 && !msm_context && !held);
 mode=1;assert(msm_open(0,0,0,&owner)==ENXIO);mode=6;assert(msm_open(0,0,0,&owner)==EIO && !msm_context);mode=0;
 assert(!msm_open(0,0,0,&owner));struct waffle_msm_gem_new r={.size=16384};
 assert(msm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&foreign)==EPERM);
 assert(!msm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner));r.handle=0;assert(!msm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner));r.handle=0;assert(msm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner)==EINVAL);
 struct waffle_msm_transfer bad={.pointer=1,.handle=2,.bytes=4};assert(msm_ioctl(0,WAFFLE_MSM_DOWNLOAD,(char *)&bad,0,&owner)==EFAULT);
 assert(!msm_close(0,0,0,&owner));return 0;
}
'''
source=strip((root/'kernel/files/bsd/dev/waffle_gpu_msm.c').read_text()).replace('__asm__ volatile("dsb sy":::"memory");','');client=strip((root/'userland/src/waffle_msm_probe.c').read_text());uapi=strip((root/'kernel/files/bsd/sys/waffle_gpu_msm.h').read_text())
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+'\n'+parts['ioc']+'\n'+uapi+'\n#include "waffle_gpu_data.h"\n'+source+mini+client+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Compare actual layouts against pinned Mesa UAPI, not invented declarations.
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'abi.c').write_text('#include <stdint.h>\n#include <stddef.h>\n#include "msm_drm.h"\n'+uapi+'\n'+''.join(f'_Static_assert(sizeof(struct waffle_msm_{a})==sizeof(struct drm_msm_{b}),"{a}");\n' for a,b in [('gem_new','gem_new'),('gem_info','gem_info'),('submit','gem_submit'),('submit_bo','gem_submit_bo'),('submit_cmd','gem_submit_cmd'),('wait','wait_fence')])+'int main(void){return 0;}\n')
 subprocess.run(['cc','-std=c11','-I',str(root/'xnu-deps/build/mesa/mesa-26.3.0-rc1/include/drm-uapi'),str(p/'abi.c'),'-o',str(p/'abi')],check=True)
 subprocess.run([str(p/'abi')],check=True)
print('Actual MSM cdev + actual client: two BO handles, uploads/user commands/3 fences/768 poisoned-output checks/7 negative tests; Mesa UAPI layout identity; host only')
