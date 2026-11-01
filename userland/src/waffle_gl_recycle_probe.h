#ifndef WAFFLE_GL_RECYCLE_PROBE_H
#define WAFFLE_GL_RECYCLE_PROBE_H
/* Isolated diagnostic only. Caller duplicates the existing Mesa device FD;
 * this must not open a second context or replace Mesa's descriptor. */
#include <errno.h>
#include <sys/ioctl.h>
#include "waffle_gpu_msm.h"
#include "waffle_gpu_writeback.h"
static uint32_t waffle_gl_recycle_queue,waffle_gl_recycle_stale_queue;
#ifdef WAFFLE_GL_QUEUE_RECYCLE
static bool waffle_gl_queue_probe_begin(int fd)
{
 printf("waffle-gl-queue: begin cycles=100 existing_Mesa_context=1\n");
 for(unsigned i=0;i<100;i++){
  struct waffle_msm_queue q={0};
  if(ioctl(fd,WAFFLE_MSM_QUEUE_NEW,&q))return false;
  if(!i)waffle_gl_recycle_stale_queue=q.id;
  if(i==99){waffle_gl_recycle_queue=q.id;return q.id>32;}
  if(ioctl(fd,WAFFLE_MSM_QUEUE_CLOSE,&q.id))return false;
 }
 return false;
}
static bool waffle_gl_queue_probe_end(int fd)
{
 uint32_t id=waffle_gl_recycle_queue;
 if(!id || ioctl(fd,WAFFLE_MSM_QUEUE_CLOSE,&id))return false;
 printf("waffle-gl-queue: result=1 cycles=100 queue=%u stale=%u stale_submit_refused=1\n",id,waffle_gl_recycle_stale_queue);
 waffle_gl_recycle_queue=waffle_gl_recycle_stale_queue=0;
 return true;
}
#endif
static bool waffle_gl_recycle_buffers(int fd,unsigned cycles)
{
 unsigned completed=0,checked=0,wrong=0;uint32_t previous=0,fence=0;
 struct waffle_msm_gem_new bo={0};struct waffle_msm_map map={0};
 const char *stage="count";
 printf("waffle-gl-recycle: begin cycles=%u existing_Mesa_context=1\n",cycles);
 if(cycles!=9000)goto failed;
 for(unsigned i=0;i<cycles;i++){
  stage="new";bo=(struct waffle_msm_gem_new){.size=16384,.flags=0x20000};
  if(ioctl(fd,WAFFLE_MSM_NEW,&bo))goto failed;
  stage="info";struct waffle_msm_gem_info info={.handle=bo.handle,.info=1};
  if(ioctl(fd,WAFFLE_MSM_INFO,&info) || !info.value || (info.value&16383))goto failed;
  if(i==1){
   stage="stale_info";struct waffle_msm_gem_info stale={.handle=previous,.info=1};
   errno=0;if(ioctl(fd,WAFFLE_MSM_INFO,&stale)!=-1 || errno!=EINVAL)goto failed;
  }
  if(i+1==cycles){
   stage="map";map=(struct waffle_msm_map){.handle=bo.handle,.bytes=16384};
   if(ioctl(fd,WAFFLE_MSM_MAP,&map) || !map.address)goto failed;
   volatile uint32_t *memory=(volatile uint32_t *)(uintptr_t)map.address;
   uint32_t packet[9];
   stage="packet";if(waffle_writeback_packet(packet,9,1,info.value+4096)!=9)goto failed;
   for(unsigned j=0;j<8;j++)memory[j]=packet[j+1];
   memory[1023]=memory[1028]=0xc0decafe;
   for(unsigned j=0;j<4;j++)memory[1024+j]=0xdeadbeef;
   struct waffle_msm_submit_bo ref={.handle=bo.handle,.flags=3,.presumed=info.value};
   struct waffle_msm_submit_cmd command={.type=1,.size=32};
   struct waffle_msm_submit submit={.flags=0x10,.nr_bos=1,.nr_cmds=1,
    .bos=(uintptr_t)&ref,.cmds=(uintptr_t)&command,.queueid=waffle_gl_recycle_queue};
   if(waffle_gl_recycle_stale_queue){
    stage="stale_queue";submit.queueid=waffle_gl_recycle_stale_queue;errno=0;
    if(ioctl(fd,WAFFLE_MSM_SUBMIT,&submit)!=-1 || errno!=EINVAL)goto failed;
    submit.queueid=waffle_gl_recycle_queue;
   }
   stage="submit";if(ioctl(fd,WAFFLE_MSM_SUBMIT,&submit) || !submit.fence)goto failed;
   fence=submit.fence;struct waffle_msm_wait wait={.fence=fence,.queueid=waffle_gl_recycle_queue};
   stage="wait";if(ioctl(fd,WAFFLE_MSM_WAIT,&wait))goto failed;
   for(unsigned j=0;j<4;j++){checked++;wrong+=memory[1024+j]!=waffle_writeback_values[j];}
   wrong+=memory[1023]!=0xc0decafe;wrong+=memory[1028]!=0xc0decafe;
   stage="GPU_values";if(wrong)goto failed;
   stage="unmap";if(ioctl(fd,WAFFLE_MSM_UNMAP,&map))goto failed;
   map.address=0;
  }
  stage="close";struct waffle_msm_close close={.handle=bo.handle};
  if(ioctl(fd,WAFFLE_MSM_CLOSE,&close))goto failed;
  previous=bo.handle;bo.handle=0;completed++;
  /* Keep evidence observable in the finite console without a new GPU policy. */
  if(!(completed%64))usleep(10000);
 }
 printf("waffle-gl-recycle: result=1 cycles=%u checked=%u wrong=%u fence=%u existing_Mesa_context=1\n",completed,checked,wrong,fence);
 return true;
failed:
 printf("waffle-gl-recycle: result=0 stage=%s cycles=%u checked=%u wrong=%u errno=%d\n",stage,completed,checked,wrong,errno);
 if(map.address)(void)ioctl(fd,WAFFLE_MSM_UNMAP,&map);
 if(bo.handle){struct waffle_msm_close close={.handle=bo.handle};(void)ioctl(fd,WAFFLE_MSM_CLOSE,&close);}
 return false;
}
#endif
