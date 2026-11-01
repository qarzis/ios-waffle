"""Actual general cdev BO/submit API replay using measured13-BO GL request shape."""
from pathlib import Path
import subprocess,tempfile,re,json,struct
root=Path(__file__).resolve().parents[2]
parts={'__file__':str(root/'tools/tests/waffle-user-host.py')};s=(root/'tools/tests/waffle-user-host.py').read_text();exec(s[:s.index('with tempfile.TemporaryDirectory()')],parts)
def strip(s):return re.sub(r'^#include .*$','',s,flags=re.M)
h='#define _DEFAULT_SOURCE\n'+parts['h'][:parts['h'].index('static int proc_pid')]
h+=r'''
#include "waffle_gpu_registry.h"
#include "waffle_gpu_va.h"
static struct waffle_gpu_memory storage[32];static unsigned stored,mapped;
static int proc_pid(struct proc *p){return p->pid;}
static int cdevsw_add(int major,const struct cdevsw *sw){assert(major==-1 && sw);return 42;}
static void cdevsw_remove(int major,const struct cdevsw *sw){assert(major==42 && sw);}
static void *devfs_make_node(dev_t d,int t,unsigned u,unsigned g,unsigned perm,const char *n){assert(d==42*256 && t==1 && !u && !g && perm==0600 && !strcmp(n,"waffle-gpu-drm"));return (void *)1;}
static void redwood_tl(const char *fmt,...){(void)fmt;}
static void loader_return(void){assert(0);}
static int copyin(uint64_t a,void *out,unsigned bytes){if(a<4096)return 14;memcpy(out,(void *)(uintptr_t)a,bytes);return 0;}
static int copyout(const void *in,uint64_t a,unsigned bytes){if(a<4096)return 14;memcpy((void *)(uintptr_t)a,in,bytes);return 0;}
struct waffle_gpu_context *waffle_gpu_context_begin(void){assert(held);context.fence=0;return &context;}
struct waffle_gpu_memory *waffle_gpu_context_memory_new(struct waffle_gpu_context *c,uint64_t bytes,uint32_t flags){
 assert(held && c==&context && stored<32);struct waffle_gpu_memory *b=&storage[stored];
 b->object=++stored;b->bytes=bytes;b->allocation_bytes=(bytes+16383)&~16383;b->flags=flags;b->memory=(uintptr_t)calloc(1,b->allocation_bytes);assert(b->memory);b->published=true;
 b->gpu_va=0x100000000ULL;for(unsigned i=0;i+1<stored;i++)b->gpu_va+=storage[i].allocation_bytes;return b;
}
bool waffle_gpu_memory_map(const struct waffle_gpu_memory *b,bool ro,uint64_t *va,uintptr_t *token){(void)ro;assert(held && !*token && b->memory);*va=b->memory;*token=b->memory;mapped++;return true;}
bool waffle_gpu_map_revoke(uintptr_t *token){assert(held);if(*token){assert(mapped);mapped--;*token=0;}return true;}
bool waffle_gpu_context_submit(struct waffle_gpu_context *c,struct waffle_gpu_submit_job *job){assert(held && c==&context && job->count==1 && job->commands[0].bytes==1240);job->fence=++context.fence;copies++;return true;}
bool waffle_gpu_context_end(struct waffle_gpu_context **c){assert(held && *c==&context && !mapped);for(unsigned i=0;i<stored;i++)free((void *)storage[i].memory);stored=0;*c=NULL;return true;}
'''
rows=[json.loads(l) for l in (root/'work/waffle/gpu/forensic-audit/gl-context-r3/msm-requests.jsonl').read_text().splitlines()];sub=next(r for r in rows if r.get('nr')==0x46);requests=[]
for b in sub['buffers']:
 a=[r for r in rows if r.get('nr')==0x42 and r['handle']==b['handle'] and r['fd']==sub['fd']][-1];requests.append((a['size'],0x20000|(a['flags']&2)))
raw=(root/'work/waffle/gpu/forensic-audit/gl-context-r3/msm-requests.jsonl-submit-1-cmd-0.bin').read_bytes();words=struct.unpack('<310I',raw)
t='static const uint32_t actual_root[]={'+','.join(hex(w)+'u' for w in words)+'};\n'
t+=r'''
int main(void){
 assert(waffle_gpu_drm_register());assert(!drm_open(0,0,0,&owner));assert(drm_open(0,0,0,&owner)==EBUSY);
 struct waffle_msm_param param={.pipe=0x10,.param=3};assert(!drm_ioctl(0,WAFFLE_MSM_PARAM,(char *)&param,0,&owner) && param.value==0x43051401);
 param.param=6;assert(!drm_ioctl(0,WAFFLE_MSM_PARAM,(char *)&param,0,&owner) && param.value==0x01000000);
 param.param=5;assert(drm_ioctl(0,WAFFLE_MSM_PARAM,(char *)&param,0,&owner)==ENOTSUP);
 struct waffle_msm_gem_new cached={.size=4096,.flags=0x80000};assert(drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&cached,0,&owner)==EINVAL && !stored);
 struct waffle_msm_submit_bo bos[13];uint64_t addresses[13];void *pointers[13];
'''
for i,(size,flags) in enumerate(requests,1):
 t+=f'''{{struct waffle_msm_gem_new r={{.size={size}u,.flags={flags}u}};assert(!drm_ioctl(0,WAFFLE_MSM_NEW,(char *)&r,0,&owner) && r.handle=={i});struct waffle_msm_gem_info info={{.handle={i},.info=1}};assert(!drm_ioctl(0,WAFFLE_MSM_INFO,(char *)&info,0,&owner));addresses[{i-1}]=info.value;struct waffle_msm_map m={{.handle={i},.bytes={size}}};assert(!drm_ioctl(0,WAFFLE_MSM_MAP,(char *)&m,0,&owner));pointers[{i-1}]=(void *)(uintptr_t)m.address;bos[{i-1}]=(struct waffle_msm_submit_bo){{.handle={i},.flags=3}};}}\n'''
t+=r'''
 assert(mapped==13 && stored==13);for(unsigned i=1;i<13;i++)assert(addresses[i]>addresses[i-1]);
 memcpy(pointers[8],actual_root,sizeof(actual_root));
 struct waffle_msm_submit_cmd cmd={.type=1,.submit_idx=8,.size=sizeof(actual_root)};
 struct waffle_msm_submit request={.flags=0x10,.nr_bos=13,.nr_cmds=1,.bos=(uintptr_t)bos,.cmds=(uintptr_t)&cmd};
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&foreign)==EPERM && !copies);
 cmd.submit_idx=13;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && !copies);cmd.submit_idx=8;
 bos[1].handle=1;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && !copies);bos[1].handle=2;
 cmd.submit_offset=1;assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && !copies);cmd.submit_offset=0;
 struct waffle_msm_queue q={0};assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q,0,&owner) && q.id==1);request.queueid=1;
 struct waffle_msm_queue q2={0};assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_NEW,(char *)&q2,0,&owner) && q2.id==2);
 request.queueid=2;
 uint32_t closed=1;assert(!drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&closed,0,&owner));
 assert(drm_ioctl(0,WAFFLE_MSM_QUEUE_CLOSE,(char *)&closed,0,&owner)==EINVAL);
 assert(!drm_queue_valid(1) && drm_queue_valid(2) && !drm_queue_valid(33));
 cmd.nr_relocs=1;cmd.relocs=0xdeadbeef;
 assert(drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner)==EINVAL && !copies);
 cmd.nr_relocs=0; /* Actual Mesa softpin caller does not initialize relocs. */
 assert(!drm_ioctl(0,WAFFLE_MSM_SUBMIT,(char *)&request,0,&owner) && request.fence==1 && mapped==13);
 struct waffle_msm_wait wait={.fence=1,.queueid=2};assert(!drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&wait,0,&owner));wait.fence=2;assert(drm_ioctl(0,WAFFLE_MSM_WAIT,(char *)&wait,0,&owner)==EINVAL);
 for(unsigned i=1;i<=13;i++){struct waffle_msm_close r={.handle=i};assert(!drm_ioctl(0,WAFFLE_MSM_CLOSE,(char *)&r,0,&owner));}
 assert(!mapped && stored==13);assert(!drm_close(0,0,0,&owner) && !stored && !drm_context);return 0;
}
'''
source=strip((root/'kernel/files/bsd/dev/waffle_gpu_drm.c').read_text()).replace('__asm__ volatile("dsb sy":::"memory");','')
uapi=strip((root/'kernel/files/bsd/sys/waffle_gpu_msm.h').read_text())
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(h+parts['ioc']+uapi+source+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual general cdev:board-param values,13 real GL-sized BOs/persistent maps,root310words,bounds/duplicates/foreign PID/future fence refusals,queue and close retains backing until full context end; host only')
