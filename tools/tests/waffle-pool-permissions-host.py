from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[2]
s=(r/'kernel/files/bsd/dev/waffle_smmu.c').read_text();code=s[s.index('struct pool_permission_context'):s.index('enum ecats_access')]
h=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include "waffle_gpu_va.h"
typedef uintptr_t vm_offset_t;
#define PTE_ADDRESS 0x0000fffffffff000ULL
#define WAFFLE_HWSCHED_POOL_ADDRESS 0x61000000u
struct table_pool {unsigned count;uintptr_t memory[32];uint64_t phys[32];};
static uint64_t root[512],second[512],leaf[512];
static unsigned cleans,syncs,fail;
static void clean(uintptr_t p){assert(p);cleans++;}
static bool tlb_sync(uintptr_t cb){assert(cb==1);return ++syncs!=fail;}
static void log_line(const char *fmt,...){(void)fmt;}
'''
t=r'''
int main(void){
 struct table_pool p={.count=3,.memory={(uintptr_t)root,(uintptr_t)second,(uintptr_t)leaf},.phys={0x1000,0x2000,0x3000}};
 struct pool_permission_context c={&p,1};
 uint64_t va=waffle_gpu_compact_alias(WAFFLE_HWSCHED_POOL_ADDRESS),v=va-WAFFLE_GPU_GLOBAL_BASE;
 root[(v>>30)&511]=0x2003;second[(v>>21)&511]=0x3003;
 uint64_t *e=&leaf[(v>>12)&511];*e=0x80000403ULL;
 assert(pool_permissions(&c,va,4096,0x339));
 assert((*e&(3ULL<<6))==(3ULL<<6) && (*e&PTE_ADDRESS)==0x80000000 && cleans==2 && syncs==2);
 assert(pool_permissions(&c,va,4096,0x33f));
 assert(!(*e&(3ULL<<6)) && cleans==4 && syncs==4);
 unsigned n=syncs;assert(pool_permissions(&c,va,4096,0x33f)&&syncs==n);
 assert(!pool_permissions(&c,va+1,4096,0x339));
 assert(!pool_permissions(&c,va,4096,0x1339));
 assert(!pool_permissions(&c,va,4096,0x338));
 *e=0;assert(!pool_permissions(&c,va,4096,0x339));
 *e=0x80000403ULL;fail=syncs+1;
 assert(!pool_permissions(&c,va,4096,0x339)&&!*e);
 assert(p.count==3);
 p.count=0;assert(!pool_permissions(&c,va,4096,0x339));
 assert(!pool_permissions(NULL,va,4096,0x339));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(h+code+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'kernel/files/bsd/sys'),str(p/'t.c'),'-o',str(p/'t')],check=True)
 subprocess.run([str(p/'t')],check=True)
print('Production allocation permissions: AP/PA, break/clean/TLBI, invalid inputs and failed invalidation passed')
