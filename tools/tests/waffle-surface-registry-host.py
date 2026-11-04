#!/usr/bin/env python3
"""Actual prepared-surface adoption and existing revoke-before-release contract."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[2]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "waffle_gpu_reclaim.h"
static struct waffle_gpu_memory entries[WAFFLE_GPU_BO_LIMIT],prepared;
static struct waffle_gpu_registry registry;
static unsigned mode,mapped,unmapped,holds,drops,cleans,tlbs,idles,phase;
static uint64_t leaf[16];
static bool idle(void *p){assert(p==&registry);idles++;return mode!=1 && !(mode==10 && phase && idles>1);}
static bool vacant(void *p,uint64_t a){assert(p==&registry && !(a&4095));return mode!=2;}
static bool map(void *p,uint64_t a,uint64_t pa,bool ro){
 assert(p==&registry && !ro && holds==1 && !drops && !prepared.object);
 struct waffle_gpu_memory *bo=&entries[0];assert(bo->object && bo->published && bo->storage==WAFFLE_GPU_STORAGE_SURFACE);
 assert(registry.count==1 && registry.used==32768 && registry.issued==1);
 unsigned slot=(a-WAFFLE_GPU_BO_VA_BASE)/4096;assert(slot<8 && pa==0x1000000+slot*8192 && !leaf[slot]);
 mapped++;if(mode==4 && mapped==2)return false;leaf[slot]=pa;return true;
}
static void clean(void *p){assert(p==&registry && !drops);cleans++;}
static bool tlb(void *p){assert(p==&registry && !drops);tlbs++;return mode!=5 && mode!=9;}
uint64_t waffle_gpu_memory_page(const struct waffle_gpu_memory *bo,uint32_t off){
 assert(bo->object==79 && bo->storage==WAFFLE_GPU_STORAGE_SURFACE && off<32768 && !(off&4095));
 if(mode==3 && off==4096)return 0;return 0x1000000+off*2;
}
bool waffle_gpu_memory_create(uint64_t bytes,uint32_t flags,struct waffle_gpu_memory *bo){(void)bytes;(void)flags;(void)bo;assert(0);return false;}
bool waffle_gpu_memory_destroy(struct waffle_gpu_memory *bo,bool detached){
 assert(bo->object==79 && holds==1 && !drops);
 assert(!bo->published || detached);holds--;drops++;memset(bo,0,sizeof(*bo));return true;
}
static bool owns(void *p,uint64_t a,uint64_t pa,bool ro){
 assert(p==&registry && !ro);unsigned slot=(a-WAFFLE_GPU_BO_VA_BASE)/4096;return slot<8 && leaf[slot]==pa && mode!=6;
}
static bool unmap(void *p,uint64_t a,uint64_t pa,bool ro){
 assert(p==&registry && !ro && registry.poisoned && holds==1 && !drops);
 unsigned slot=(a-WAFFLE_GPU_BO_VA_BASE)/4096;assert(slot<8 && leaf[slot]==pa);unmapped++;
 if(mode==8 && unmapped==2)return false;leaf[slot]=0;return true;
}
static const struct waffle_gpu_registry_ops ops={idle,vacant,map,clean,tlb,&registry};
static const struct waffle_gpu_reclaim_ops reclaim={&ops,owns,unmap};
static void reset(void){
 memset(entries,0,sizeof(entries));memset(leaf,0,sizeof(leaf));registry=(struct waffle_gpu_registry){.buffers=entries};
 prepared=(struct waffle_gpu_memory){.object=79,.memory=0x2000000,.bytes=32768,.allocation_bytes=32768,.flags=WAFFLE_GPU_BO_CACHED,.storage=WAFFLE_GPU_STORAGE_SURFACE};
 mode=mapped=unmapped=drops=cleans=tlbs=idles=phase=0;holds=1;
}
int main(void){
 for(unsigned n=0;n<=5;n++){
  reset();mode=n;struct waffle_gpu_memory before=prepared;
  struct waffle_gpu_memory *bo=waffle_gpu_registry_adopt(&registry,&ops,&prepared);
  assert((bo!=0)==(n==0));
  if(n==1 || n==2){assert(!memcmp(&before,&prepared,sizeof(before)) && !registry.count && !mapped && !registry.poisoned);assert(waffle_gpu_memory_destroy(&prepared,false));}
  else{
   assert(!prepared.object && registry.count==1 && registry.used==32768 && holds==1 && !drops);
   assert(registry.poisoned==(n!=0));
   assert(!waffle_gpu_registry_destroy(&registry,false) && holds==1 && !drops);
   assert(waffle_gpu_registry_destroy(&registry,true));
  }
  assert(!holds && drops==1);
 }
 for(unsigned n=0;n<11;n++){
  reset();switch(n){
   case 0:prepared.storage=WAFFLE_GPU_STORAGE_OWNED;break;case 1:prepared.flags=WAFFLE_GPU_BO_WC;break;
   case 2:prepared.published=true;break;case 3:prepared.gpu_va=WAFFLE_GPU_BO_VA_BASE;break;case 4:prepared.serial=1;break;
   case 5:prepared.allocation_bytes=16384;break;case 6:registry.used=WAFFLE_GPU_BO_HEAP_BYTES-16384;break;
   case 7:registry.count=WAFFLE_GPU_BO_LIMIT+1;break;case 8:registry.issued=UINT32_MAX;break;case 9:registry.poisoned=true;break;case 10:prepared.memory=0;break;
  }
  struct waffle_gpu_memory before=prepared;assert(!waffle_gpu_registry_adopt(&registry,&ops,&prepared));
  assert(!memcmp(&before,&prepared,sizeof(before)) && !mapped && !drops && holds==1);
 }
 reset();entries[0]=prepared;assert(!waffle_gpu_registry_adopt(&registry,&ops,&entries[0]) && entries[0].object && !mapped);
 for(unsigned n=0;n<6;n++){
  reset();struct waffle_gpu_memory *bo=waffle_gpu_registry_adopt(&registry,&ops,&prepared);assert(bo && mapped==8);
  mode=n?5+n:0;idles=0;phase=1;
  if(n==1){assert(!waffle_gpu_registry_reclaim(&registry,&reclaim,bo,true) && !unmapped && holds==1);}
  else if(n==2){assert(!waffle_gpu_registry_reclaim(&registry,&reclaim,bo,false) && !unmapped && holds==1);}
  else if(n){assert(!waffle_gpu_registry_reclaim(&registry,&reclaim,bo,true) && holds==1 && !drops && registry.poisoned);}
  else{assert(waffle_gpu_registry_reclaim(&registry,&reclaim,bo,true) && unmapped==8 && !holds && drops==1 && !registry.used);}
  if(holds)assert(waffle_gpu_registry_destroy(&registry,true) && drops==1 && !holds);
 }
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual surface registry adoption/reclaim: caller retains pre-move failures, move before first PTE, budget/VA/identity checks, partial-map/TLB failures retain backing until detach, revoke+TLB+post-idle before surface release; GPU/physical ownership modeled')
