#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include "waffle_surface_access.h"
static struct waffle_surface_access state;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static unsigned cpu_done,gpu_done;
static void *writer(void *arg){
 (void)arg;uint32_t client=0;
 for(unsigned i=0;i<1000;){
  pthread_mutex_lock(&mutex);bool ok=waffle_surface_cpu_write_begin(&state,&client);if(ok)assert(!state.gpu_readers);pthread_mutex_unlock(&mutex);
  if(!ok){sched_yield();continue;}
  sched_yield();pthread_mutex_lock(&mutex);assert(!state.gpu_readers && waffle_surface_cpu_write_end(&state,&client));cpu_done++;pthread_mutex_unlock(&mutex);i++;
 }
 return NULL;
}
static void *reader(void *arg){
 (void)arg;
 for(unsigned i=0;i<1000;){
  pthread_mutex_lock(&mutex);bool ok=waffle_surface_gpu_read_begin(&state);if(ok)assert(!state.cpu_writers);pthread_mutex_unlock(&mutex);
  if(!ok){sched_yield();continue;}
  sched_yield();pthread_mutex_lock(&mutex);assert(!state.cpu_writers && waffle_surface_gpu_read_end(&state));gpu_done++;pthread_mutex_unlock(&mutex);i++;
 }
 return NULL;
}
int main(void){
 uint32_t a=0,b=0;
 assert(waffle_surface_cpu_write_begin(&state,&a));assert(waffle_surface_cpu_write_begin(&state,&a));assert(waffle_surface_cpu_write_begin(&state,&b));
 assert(state.cpu_writers==3 && !waffle_surface_gpu_read_begin(&state));
 assert(waffle_surface_cpu_write_drop(&state,&a) && state.cpu_writers==1);assert(waffle_surface_cpu_write_end(&state,&b));
 assert(!waffle_surface_cpu_write_end(&state,&b));assert(waffle_surface_gpu_read_begin(&state));assert(!waffle_surface_cpu_write_begin(&state,&a));
 assert(waffle_surface_cpu_wait_begin(&state));assert(waffle_surface_gpu_read_end(&state));assert(!waffle_surface_gpu_read_begin(&state));
 assert(waffle_surface_cpu_wait_end(&state));assert(waffle_surface_gpu_read_begin(&state));assert(waffle_surface_gpu_read_end(&state));assert(!waffle_surface_gpu_read_end(&state));
 state.cpu_writers=UINT32_MAX;assert(!waffle_surface_cpu_write_begin(&state,&a));state=(struct waffle_surface_access){0};
 state.gpu_readers=UINT32_MAX;assert(!waffle_surface_gpu_read_begin(&state));state=(struct waffle_surface_access){0};
 state.waiting_writers=UINT32_MAX;assert(!waffle_surface_cpu_wait_begin(&state));state=(struct waffle_surface_access){0};
 a=1;assert(!waffle_surface_cpu_write_drop(&state,&a) && a==1 && !state.cpu_writers);a=0;
 pthread_t threads[4];assert(!pthread_create(&threads[0],NULL,writer,NULL));assert(!pthread_create(&threads[1],NULL,writer,NULL));assert(!pthread_create(&threads[2],NULL,reader,NULL));assert(!pthread_create(&threads[3],NULL,reader,NULL));
 for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
 assert(cpu_done==2000 && gpu_done==2000 && !state.cpu_writers && !state.gpu_readers && !state.waiting_writers);
}
