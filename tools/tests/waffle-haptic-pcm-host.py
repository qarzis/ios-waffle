#!/usr/bin/env python3
"""Execute actual device PCM adapter: no PMIC operations on audio write path."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2];s=(r/'kernel/files/bsd/dev/macan_torch.c').read_text();a=s[s.index('static int\nwaffle_haptic_pcm_open'):s.index('static const struct cdevsw waffle_haptic_pcm_cdevsw')]
program=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <sys/types.h>
#include "waffle_haptic_events.h"
#define __unused __attribute__((unused))
typedef long user_ssize_t;
struct proc {int unused;};struct uio {const char *data;long count;};
static bool haptic_service_ready,leaving,locked;static struct waffle_haptic_events haptic_events;
static int haptic_event_lock;static unsigned copies,fail_at;static uint64_t now;
static void lck_mtx_lock(int *p){(void)p;assert(!locked);locked=true;}
static void lck_mtx_unlock(int *p){(void)p;assert(locked);locked=false;}
static uint64_t waffle_haptic_now_us(void *p){(void)p;return now;}
static long uio_resid(struct uio *u){return u->count;}
static int uiomove(char *out,int n,struct uio *u){assert(!locked&&n<=512);if(++copies==fail_at)return EFAULT;memcpy(out,u->data,n);u->count-=n;u->data+=n;return 0;}
'''+a+r'''
int main(void){int16_t sample[600]={0};sample[0]=-32768;struct proc p;
 assert(waffle_haptic_pcm_open(0,0,0,&p)==ENXIO);haptic_service_ready=true;assert(!waffle_haptic_pcm_open(0,0,0,&p));
 struct uio u={(const char *)sample,sizeof(sample)};assert(!waffle_haptic_pcm_write(0,&u,0)&&!u.count&&copies==3&&haptic_events.frames==600&&haptic_events.onsets==1&&haptic_events.pending&&!locked);
 u=(struct uio){(const char *)sample,3};copies=0;assert(waffle_haptic_pcm_write(0,&u,0)==EINVAL&&!copies);
 for(unsigned f=1;f<=3;f++){u=(struct uio){(const char *)sample,sizeof(sample)};copies=0;fail_at=f;assert(waffle_haptic_pcm_write(0,&u,0)==EFAULT&&!locked);}fail_at=0;
 leaving=true;assert(waffle_haptic_pcm_open(0,0,0,&p)==ENXIO);u=(struct uio){(const char *)sample,4};assert(waffle_haptic_pcm_write(0,&u,0)==ENXIO&&!locked);
 leaving=false;haptic_service_ready=false;u=(struct uio){(const char *)sample,4};assert(waffle_haptic_pcm_write(0,&u,0)==ENXIO&&!locked);
 puts("PASS actual PCM cdev: bounded512-byte copies outside queue lock, odd/error/shutdown/unready refusal, signed peak/onset queue; no motor/MMIO work in write callback.");}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(program);subprocess.run(['cc','-D_DEFAULT_SOURCE','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
