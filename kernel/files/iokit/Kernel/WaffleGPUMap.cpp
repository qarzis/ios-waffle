#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <kern/task.h>
#include <vm/pmap.h>
#include "../../bsd/sys/waffle_gpu_map.h"
extern "C" uint64_t kvtophys(vm_offset_t);
bool waffle_gpu_map_create(uintptr_t memory,bool readonly,uint64_t *address,uintptr_t *token)
{
 if(!memory || !address || !token || *token || (memory&16383))return false;
 *address=0;
 uint64_t pa=kvtophys(memory);
 if(!pa || (pa&16383) || pa>=(1ULL<<36) || kvtophys(memory+16383)!=pa+16383 || current_task()==kernel_task)return false;
 IOMemoryDescriptor *descriptor=IOMemoryDescriptor::withPhysicalAddress(pa,16384,kIODirectionInOut);
 if(!descriptor)return false;
 IOMemoryMap *map=descriptor->createMappingInTask(current_task(),0,
     kIOMapAnywhere|kIOMapUnique|kIOMapWriteCombineCache|(readonly?kIOMapReadOnly:0),0,16384);
 descriptor->release();
 if(!map)return false;
 uint64_t va=map->getAddress();
 if(!va || (va&16383)){map->unmap();map->release();return false;}
 *address=va;*token=reinterpret_cast<uintptr_t>(map);return true;
}
bool waffle_gpu_map_revoke(uintptr_t *token)
{
 if(!token)return false;
 if(!*token)return true;
 IOMemoryMap *map=reinterpret_cast<IOMemoryMap *>(*token);
 if(map->unmap()!=kIOReturnSuccess)return false;
 map->release();*token=0;return true;
}
