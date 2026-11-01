/* Host-only LD_PRELOAD request capture, used above Mesa's stock no-op shim. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <pthread.h>
#include <string.h>
#include "msm_drm.h"
static int (*next_ioctl)(int,unsigned long,...);
static void *(*next_mmap)(void *,size_t,int,int,int,off_t);
static FILE *logfile;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local unsigned inside;
struct buffer {int fd;uint32_t handle;uint64_t size,offset,iova;void *mapping;};
static struct buffer bos[8192];static unsigned num_bos,submits;
static struct buffer *lookup(int fd,uint32_t handle){for(unsigned i=num_bos;i;i--)if(bos[i-1].fd==fd && bos[i-1].handle==handle)return &bos[i-1];return NULL;}
static void init(void){if(!next_ioctl)next_ioctl=dlsym(RTLD_NEXT,"ioctl");if(!next_mmap)next_mmap=dlsym(RTLD_NEXT,"mmap");if(!logfile){const char *p=getenv("WAFFLE_MSM_TRACE");if(p)logfile=fopen(p,"w");}}
int ioctl(int fd,unsigned long request,...){
 va_list ap;va_start(ap,request);void *arg=va_arg(ap,void *);va_end(ap);
 if(inside){if(!next_ioctl)next_ioctl=dlsym(RTLD_NEXT,"ioctl");return next_ioctl(fd,request,arg);}
 inside++;pthread_mutex_lock(&lock);init();
 int ret=next_ioctl(fd,request,arg);unsigned nr=_IOC_NR(request);
 if(logfile && _IOC_TYPE(request)=='d'){
  fprintf(logfile,"{\"op\":\"ioctl\",\"fd\":%d,\"nr\":%u,\"ret\":%d",fd,nr,ret);
  if(nr==DRM_COMMAND_BASE+DRM_MSM_GET_PARAM){struct drm_msm_param *p=arg;fprintf(logfile,",\"param\":%u,\"value\":%llu",p->param,(unsigned long long)p->value);}
  if(nr==DRM_COMMAND_BASE+DRM_MSM_GEM_NEW){struct drm_msm_gem_new *p=arg;fprintf(logfile,",\"handle\":%u,\"size\":%llu,\"flags\":%u",p->handle,(unsigned long long)p->size,p->flags);if(!ret && num_bos<8192)bos[num_bos++]=(struct buffer){.fd=fd,.handle=p->handle,.size=p->size};}
  if(nr==DRM_COMMAND_BASE+DRM_MSM_GEM_INFO){struct drm_msm_gem_info *p=arg;struct buffer *b=lookup(fd,p->handle);fprintf(logfile,",\"handle\":%u,\"info\":%u,\"value\":%llu",p->handle,p->info,(unsigned long long)p->value);if(!ret && b){if(p->info==MSM_INFO_GET_OFFSET)b->offset=p->value;if(p->info==MSM_INFO_GET_IOVA)b->iova=p->value;}}
  if(nr==DRM_COMMAND_BASE+DRM_MSM_GEM_SUBMIT){
   struct drm_msm_gem_submit *p=arg;struct drm_msm_gem_submit_bo *bs=(void *)(uintptr_t)p->bos;struct drm_msm_gem_submit_cmd *cs=(void *)(uintptr_t)p->cmds;
   fprintf(logfile,",\"submit\":%u,\"flags\":%u,\"nr_bos\":%u,\"nr_cmds\":%u,\"queue\":%u,\"buffers\":[",++submits,p->flags,p->nr_bos,p->nr_cmds,p->queueid);
   for(unsigned i=0;i<p->nr_bos;i++)fprintf(logfile,"%s{\"handle\":%u,\"flags\":%u,\"iova\":%llu}",i?",":"",bs[i].handle,bs[i].flags,(unsigned long long)bs[i].presumed);
   fprintf(logfile,"],\"commands\":[");
   for(unsigned i=0;i<p->nr_cmds;i++){
    struct buffer *b=cs[i].submit_idx<p->nr_bos?lookup(fd,bs[cs[i].submit_idx].handle):NULL;
    fprintf(logfile,"%s{\"type\":%u,\"bo_index\":%u,\"offset\":%u,\"size\":%u,\"relocs\":%u,\"mapped\":%s}",i?",":"",cs[i].type,cs[i].submit_idx,cs[i].submit_offset,cs[i].size,cs[i].nr_relocs,b&&b->mapping?"true":"false");
    if(b && b->mapping && cs[i].submit_offset<=b->size && cs[i].size<=b->size-cs[i].submit_offset){char path[4096];snprintf(path,sizeof(path),"%s-submit-%u-cmd-%u.bin",getenv("WAFFLE_MSM_TRACE"),submits,i);FILE *f=fopen(path,"wb");if(f){fwrite((char *)b->mapping+cs[i].submit_offset,1,cs[i].size,f);fclose(f);}}
   }
   fprintf(logfile,"]");
  }
  fprintf(logfile,"}\n");fflush(logfile);
 }
 pthread_mutex_unlock(&lock);inside--;return ret;
}
void *mmap(void *addr,size_t length,int prot,int flags,int fd,off_t offset){
 if(inside){if(!next_mmap)next_mmap=dlsym(RTLD_NEXT,"mmap");return next_mmap(addr,length,prot,flags,fd,offset);}
 inside++;pthread_mutex_lock(&lock);init();void *p=next_mmap(addr,length,prot,flags,fd,offset);
 if(p!=MAP_FAILED)for(unsigned i=num_bos;i;i--)if(bos[i-1].fd==fd && bos[i-1].offset==(uint64_t)offset && length<=bos[i-1].size){bos[i-1].mapping=p;if(logfile){fprintf(logfile,"{\"op\":\"map\",\"handle\":%u,\"size\":%zu}\n",bos[i-1].handle,length);fflush(logfile);}break;}
 pthread_mutex_unlock(&lock);inside--;return p;
}
void *mmap64(void *,size_t,int,int,int,off64_t) __attribute__((alias("mmap")));
