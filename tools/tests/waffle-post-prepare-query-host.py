"""Exercise the production post-prepare query and all pre-publication failures."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'kernel/files/bsd/dev/waffle_gmu.c').read_text()
block = source[source.index('        if (probe==74 || probe==79 || probe==81 || probe==83 || probe==84 || probe==87 || probe==88 || probe==90 || probe==93) {'):source.index('        if (probe==67) {')]
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <setjmp.h>
typedef uintptr_t vm_offset_t;
struct live { int context; };
static jmp_buf abort_env;
static unsigned mode, prepared, diagnosed, sent, expected_sequence;
static uint32_t rd(vm_offset_t gpu,unsigned offset) {
 assert(gpu==1 && offset==0x808*4);return mode==1;
}
static bool gen7_live_prepare(void *context) {
 assert(context);++prepared;return mode!=2;
}
static void hfi_raw_diagnostic(vm_offset_t gmu,vm_offset_t alias,unsigned *budget) {
 assert(gmu==2 && alias==3 && *budget==16);++diagnosed;
}
static bool hfi_exchange_watch(vm_offset_t gmu,vm_offset_t alias,const uint32_t *p,
 unsigned words,const char *name,bool zero,void *plan) {
 assert(gmu==2 && alias==3 && words==3 && name && !zero && !plan);
 assert(p[0]==((expected_sequence<<20)|(3<<8)|12) && p[1]==122 && p[2]==0);
 ++sent;return mode!=3;
}
static void stop_unsafe(const char *reason) {assert(reason);longjmp(abort_env,1);}
static void say(const char *fmt,...) {(void)fmt;}
static void run_query(unsigned probe) {
 struct live storage={0},*live=&storage;
 vm_offset_t gpu=1,gmu=2,hfi_alias=3;void *plan=0;
'''
tests = r'''
}
int main(void) {
 const unsigned probes[]={74,79,81,83,84,87,88,90,93};
 for(unsigned i=0;i<9;i++) {
  unsigned probe=probes[i];
  expected_sequence=probe>=79?42:40;
  for(mode=0;mode<4;mode++) {
   prepared=diagnosed=sent=0;
   if(!setjmp(abort_env)) {run_query(probe);assert(mode==0);}
   else assert(mode!=0);
   assert(prepared==(mode!=1));
   assert(diagnosed==(mode!=1 && mode!=2));
   assert(sent==(mode!=1 && mode!=2));
  }
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + block + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g', str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Production QUERY74/79: exact request headers and every preflight/ACK failure passed')

# Execute the production selector as well: a missing93 entry in this ternary
# would silently choose the full CP RAW path before reaching the query block.
start=source.index('    int result=(probe==35')
end=source.index('    if ((probe==34',start)
dispatch=source[start:end]
dispatch_harness=r'''
#include <assert.h>
#include <stdint.h>
static unsigned selected,expected_sequence;
static int choose(unsigned kind,unsigned sequence) {
 assert(sequence==expected_sequence);selected=kind;return 0;
}
#define waffle_gen7_boot_thread_start(a,b,c,d,e,f,g,s) choose(1,s)
#define waffle_gen7_boot_prepare(a,b,c,d,e,f,g,s) choose(2,s)
#define waffle_gen7_boot_start(a,b,c,d,e,f,g,s) choose(3,s)
int main(void) {
 const unsigned cases[]={85,90,91,93,94};
 for(unsigned i=0;i<5;i++) {
  unsigned probe=cases[i];
  expected_sequence=(probe==85 || probe==91 || probe==94)?42:34;
'''
dispatch_tests=r'''
  assert(!result);
  assert(selected==(probe==85?1:(probe==91 || probe==94)?3:2));
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'dispatch.c').write_text(dispatch_harness+dispatch+dispatch_tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(path/'dispatch.c'),'-o',str(path/'dispatch')],check=True)
    subprocess.run([str(path/'dispatch')],check=True)
print('Production dispatch:93/90 prepare only,91/94 full CP,85 thread path verified')
