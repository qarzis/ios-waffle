#!/usr/bin/env python3
"""Execute actual loader product-node construction, with real identity bytes."""
from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parents[2];s=(r/'loader/loader.c').read_text();block=s[s.index(' dt_begin(&w, "product");'):s.index(' dt_begin(&w, "options");')]
program=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "waffle.h"
#include "identity.h"
struct writer {unsigned depth,haptic,properties;};
static void dt_begin(struct writer *w,const char *name){w->depth++;if(!strcmp(name,"haptics")){assert(w->depth==2);w->haptic++;}else assert(!strcmp(name,"product"));}
static void dt_end(struct writer *w){assert(w->depth);w->depth--;}
static void dt_identity(struct writer *w,const struct identity_prop *p,uint32_t count,const unsigned char *data){if(w->depth==2){assert(count==2);for(unsigned i=0;i<count;i++){assert(p[i].length==4);uint32_t v;memcpy(&v,data+p[i].offset,4);assert(v==1);assert(!strcmp(p[i].name,i?"supports-3rd-party-haptics":"closed-loop"));w->properties++;}}}
static void test(const char *line,unsigned expected){struct writer w={0};struct {const char *cmdline;}pi={line};
'''+block+r'''
assert(!w.depth&&w.haptic==expected&&w.properties==expected*2);}
int main(void){
#if defined(WAFFLE_USERLAND) && defined(WAFFLE_HAPTIC_PULSE_TEST) && defined(XNU_PLATFORM_WAFFLE)
unsigned expected=1;
#else
unsigned expected=0;
#endif
test("bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2",expected);
test("bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1 waffle_haptic_test=1",0);
test("bootcpu=7 cpus=1 loader_return_after=60 waffle_torch=1",0);
test("cpus=2 loader_return_after=60 waffle_torch=1 waffle_haptic_test=2",0);
(void)pi;
puts("PASS actual product tree block: exact haptic identity bytes/nesting, dedicated service only; defaults/read-only/one-shot/invalid requests omit node.");}
'''
program=program.replace('(void)pi;','')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(program)
 for name,flags in [('user',['-DXNU_PLATFORM_WAFFLE=1','-DWAFFLE_USERLAND=1']),('pulse',['-DXNU_PLATFORM_WAFFLE=1','-DWAFFLE_USERLAND=1','-DWAFFLE_HAPTIC_PULSE_TEST=1'])]:
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-const-variable','-I',str(r/'loader'),*flags,str(p/'test.c'),'-o',str(p/name)],check=True);subprocess.run([str(p/name)],check=True)
