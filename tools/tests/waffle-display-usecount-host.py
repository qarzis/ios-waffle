#!/usr/bin/env python3
"""Actual IOSurface holds: display use must survive until all readers retire."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root/'kernel/files/iokit/Kernel/MiniIOSurface.cpp').read_text()
header = (root/'kernel/files/iokit/Kernel/MiniIOSurface.h').read_text()

def function(name):
    match = re.search(r'(?:MiniIOSurface \*|void)\n'+name+r'\(', source)
    start = source.index('{', match.start())
    depth = 1
    end = start+1
    while depth:
        depth += (source[end] == '{')-(source[end] == '}')
        end += 1
    return source[match.start():end]+'\n'

shared = re.search(r'struct minisurf_shared \{.*?\n\};', header, re.S)[0]
code = function('MiniIOSurfaceCopy')+function('MiniIOSurfaceDrop')
if 'MiniIOSurfaceCopyForDisplay(' in source:
    code += function('MiniIOSurfaceCopyForDisplay')+function('MiniIOSurfaceDropForDisplay')
else:
    # Baseline uses the exact existing display's lifetime-only hold pair.
    code += '#define MiniIOSurfaceCopyForDisplay MiniIOSurfaceCopy\n#define MiniIOSurfaceDropForDisplay MiniIOSurfaceDrop\n'
harness = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
''' + shared + r'''
static_assert(offsetof(minisurf_shared,useCount)==24);
struct MiniIOSurface {
 uint32_t sid=1,holders=1,useCount[2]{},displayUses=0;
 minisurf_shared state{};
 minisurf_shared *shared(){return &state;}
};
static int lock;
static int *gSurfaceLock=&lock;
static bool locked;
#define MINISURF_TABLE_SIZE 8
static MiniIOSurface *gSurfaceTable[MINISURF_TABLE_SIZE];
static void IOLockLock(int *){assert(!locked);locked=true;}
static void IOLockUnlock(int *){assert(locked);locked=false;}
static void surfaceHold(MiniIOSurface *s){assert(locked);s->holders++;}
static void surfaceUnhold(MiniIOSurface *s){assert(locked && s->holders>1);s->holders--;}
static unsigned warnings;
static void IOLog(const char *,...){warnings++;}
''' + code + r'''
static bool nativeIsInUse(MiniIOSurface *s){return s->shared()->useCount!=0;}
int main(){
 MiniIOSurface s;gSurfaceTable[1]=&s;
 auto *ordinary=MiniIOSurfaceCopy(1);assert(ordinary==&s && !nativeIsInUse(&s));
 MiniIOSurfaceDrop(ordinary);assert(s.holders==1);
 assert(!MiniIOSurfaceCopyForDisplay(0) && !MiniIOSurfaceCopyForDisplay(8) && !MiniIOSurfaceCopyForDisplay(2));
 auto *a=MiniIOSurfaceCopyForDisplay(1);
 assert(a==&s && nativeIsInUse(&s) && s.displayUses==1 && s.holders==2);
 auto *b=MiniIOSurfaceCopyForDisplay(1);
 assert(b==&s && s.displayUses==2 && s.useCount[0]==2 && s.holders==3);
 // Independent client references can disappear without retiring display use.
 s.useCount[0]+=3;s.useCount[1]=4;s.shared()->useCount=(uint64_t(4)<<32)|s.useCount[0];
 s.useCount[0]-=3;s.useCount[1]=0;s.shared()->useCount=s.useCount[0];
 MiniIOSurfaceDropForDisplay(a);assert(nativeIsInUse(&s) && s.displayUses==1 && s.holders==2);
 MiniIOSurfaceDropForDisplay(b);assert(!nativeIsInUse(&s) && !s.displayUses && s.holders==1);
 MiniIOSurfaceDropForDisplay(b);assert(warnings==1 && s.holders==1 && !s.useCount[0]);
 s.useCount[0]=UINT32_MAX;s.shared()->useCount=UINT32_MAX;
 assert(!MiniIOSurfaceCopyForDisplay(1) && s.holders==1 && !s.displayUses && s.useCount[0]==UINT32_MAX);
 s.useCount[0]=0;s.shared()->useCount=0;
 for(unsigned i=0;i<100000;i++){
  a=MiniIOSurfaceCopyForDisplay(1);assert(nativeIsInUse(a));MiniIOSurfaceDropForDisplay(a);
  assert(!nativeIsInUse(&s) && s.holders==1 && !s.displayUses);
 }
 MiniIOSurfaceDropForDisplay(nullptr);assert(!locked);
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.cpp').write_text(harness)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-fsanitize=address,undefined',
                    str(path/'test.cpp'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
print('PASS actual IOSurface display lease: native shared usage24, nested readers, independent clients, overflow refusal and100000 balanced retirement cycles. Mock locks/object lifetime only; no hardware VSync claim.')
