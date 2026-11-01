"""Actual C++ mapping helper against IOKit object/physical mapping failure model."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=re.sub(r'^#include .*$','',(root/'kernel/files/iokit/Kernel/WaffleGPUMap.cpp').read_text(),flags=re.M)
h=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
using vm_offset_t=uintptr_t;
static unsigned mode,releases,unmaps,created;
static int kernel_task=7;
static int current_task(){return mode==5?7:9;}
static constexpr unsigned kIODirectionInOut=3,kIOMapAnywhere=1,kIOMapUnique=2,kIOMapWriteCombineCache=4,kIOMapReadOnly=8,kIOReturnSuccess=0;
extern "C" uint64_t kvtophys(uintptr_t a){if(mode==1)return 0;if(mode==2)return 1ULL<<36;if(mode==3 && (a&16383))return 0x2008000;return 0x2000000+(a&16383);}
class IOMemoryMap {
public:uint64_t getAddress(){return mode==7?1:0x100080000ULL;}
unsigned unmap(){unmaps++;return mode==8?1:0;}
void release(){releases++;}
};
static IOMemoryMap map;
class IOMemoryDescriptor {
public:static IOMemoryDescriptor *withPhysicalAddress(uint64_t pa,unsigned size,unsigned direction);
IOMemoryMap *createMappingInTask(int t,uint64_t at,unsigned options,unsigned offset,unsigned length){
 assert(t==9 && !at && (options&7)==7 && !offset && length==16384);created++;return mode==6?nullptr:&map;}
void release(){releases++;}
};
static IOMemoryDescriptor descriptor;
IOMemoryDescriptor *IOMemoryDescriptor::withPhysicalAddress(uint64_t pa,unsigned size,unsigned direction){assert(pa==0x2000000 && size==16384 && direction==3);return mode==4?nullptr:&descriptor;}
'''
t=r'''
int main(){
 for(mode=0;mode<=8;mode++){
  releases=unmaps=created=0;uint64_t va=99;uintptr_t token=0;
  bool ok=waffle_gpu_map_create(0x800000,false,&va,&token);
  assert(ok==(mode==0 || mode==8));
  if(ok){assert(va==0x100080000ULL && token);bool revoked=waffle_gpu_map_revoke(&token);assert(revoked==(mode==0));assert((token==0)==revoked);}
  else assert(!va && !token);
 }
 mode=0;uint64_t va=0;uintptr_t token=0;
 assert(!waffle_gpu_map_create(0x800001,false,&va,&token));
 assert(waffle_gpu_map_create(0x800000,true,&va,&token));
 assert(!waffle_gpu_map_create(0x800000,true,&va,&token));
 assert(waffle_gpu_map_revoke(&token));assert(waffle_gpu_map_revoke(&token));
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cc').write_text(h+s+t);subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.cc'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual C++ IOMemoryMap helper: PA/alignment/task/descriptor/map/address failures, readonly/unique WCOMB options, revoke failure retains token; host only')
