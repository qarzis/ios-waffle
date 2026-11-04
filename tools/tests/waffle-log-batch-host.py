#!/usr/bin/env python3
"""Compare actual logger against pre-batch implementation including ring wrap."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
def function(source, signature):
    start=source.index(signature);at=source.index('{',start);end=at+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

source=(root/'kernel/files/osfmk/arm64/loader_return.c').read_text()
# Retain the scalar implementation as an independent behavior oracle.
# The fixture below uses the former insertion algorithm, not the new writer.
reference=r'''
void loader_log_putc(char c) {
 if(c=='\r')return;
 unsigned char *at=nullptr;
 if(loader_log_linear || loader_log_len<LOADER_LOG_HEAD){
  if(loader_log_len<LOADER_LOG_SIZE){at=&loader_log[loader_log_len];loader_log[loader_log_len++]=c;}
 }else{
  at=&loader_log[LOADER_LOG_HEAD+loader_log_ring_at];*at=c;
  if(++loader_log_ring_at==LOADER_LOG_RING){loader_log_ring_at=0;loader_log_wrapped=true;}
  if(!loader_log_wrapped)loader_log_len=LOADER_LOG_HEAD+loader_log_ring_at;
 }
 if(at && (c=='\n' || ((uintptr_t)at&63)==63))clean(at);
 locks++;
}
void loader_log_line(const char *s){for(;*s;s++)loader_log_putc(*s);}
'''
new='\n'.join(function(source,sig) for sig in ['static void\nloader_log_write','void\nloader_log_putc','void\nloader_log_line('])
new=new.replace('__asm__ volatile ("dc cvac, %0" : : "r" (at) : "memory");','clean(at);')
common=r'''
constexpr size_t LOADER_LOG_HEAD=256,LOADER_LOG_RING=1024,LOADER_LOG_SIZE=1280;
alignas(64) static char loader_log[LOADER_LOG_SIZE];
static size_t loader_log_len,loader_log_ring_at;
static bool loader_log_linear,loader_log_wrapped;
static uint32_t loader_log_lock;
static unsigned locks,cleans;
static std::vector<size_t> cleaned;
static void clean(const void *p){cleans++;cleaned.push_back((const char*)p-loader_log);}
static uint64_t __builtin_arm_rsr64(const char*){return 0x1234;}
static void __builtin_arm_wsr(const char*,unsigned){}
static void __builtin_arm_wsr64(const char*,uint64_t v){assert(v==0x1234);}
static bool cmp(uint32_t *p){assert(!*p);*p=1;locks++;return true;}
'''
code=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#define DAIFSC_IRQF 2
#define DAIFSC_FIQF 1
#define os_atomic_cmpxchg(p,a,b,c) cmp(p)
#define os_atomic_store(p,a,b) (*(p)=a)
namespace before {
'''+common+reference.replace('unsigned char *at=nullptr;','char *at=nullptr;')+'}\nnamespace after {\n'+common+new+r'''
}
static void equal(){
 assert(!memcmp(before::loader_log,after::loader_log,before::LOADER_LOG_SIZE));
 assert(before::loader_log_len==after::loader_log_len);
 assert(before::loader_log_ring_at==after::loader_log_ring_at);
 assert(before::loader_log_wrapped==after::loader_log_wrapped);
 assert(before::cleaned==after::cleaned);
 assert(!after::loader_log_lock);
}
int main(){
 std::string text;
 for(unsigned i=0;i<4096;i++)text+=(i%31==0?'\r':i%47==0?'\n':'A'+i%26);
 before::loader_log_line(text.c_str());after::loader_log_line(text.c_str());equal();
 assert(after::locks==64 && before::locks>3900);
 for(unsigned i=0;i<10000;i++){
  std::string s=text.substr(i%1024,i%513);
  before::loader_log_line(s.c_str());after::loader_log_line(s.c_str());equal();
 }
 for(unsigned i=0;i<5000;i++){
  before::loader_log_putc(char(i%255));after::loader_log_putc(char(i%255));equal();
 }
 before::loader_log_linear=after::loader_log_linear=true;
 before::loader_log_len=after::loader_log_len=0;
 before::cleaned.clear();after::cleaned.clear();
 before::loader_log_line(text.c_str());after::loader_log_line(text.c_str());equal();
}
'''
with tempfile.TemporaryDirectory() as t:
    p=Path(t);(p/'test.cpp').write_text(code)
    subprocess.run(['c++','-std=c++17','-O1','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS actual batched logger: scalar byte/cache-clean equivalence, head/ring wrap, CR/newline, empty/long text, linear truncation and putc;4096 bytes use64 locks instead of>3900; DAIF/cache hardware mocked')
