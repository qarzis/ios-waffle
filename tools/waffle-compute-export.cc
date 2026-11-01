#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "computerator/main.h"
#include "computerator/ir3_asm.h"
#ifdef WAFFLE_GLSL_EXPORT
#define FD_BO_NO_HARDPIN 1
#include "fd6_hw.h"
#include "common/fd6_pack.h"
extern "C" ir3_shader_variant *waffle_glsl_variant(char *);
#endif

static constexpr uint64_t gpu_base=0x1ff8000478000ULL;
alignas(64) static uint8_t arena[16384];
static uint32_t commands[4096];
static fd_ringbuffer ring;
struct recorded_bo {fd_bo bo; unsigned offset; char name[64]; bool attached;};
static recorded_bo bos[4];
static unsigned count;

static recorded_bo *record(fd_bo *bo)
{
    for(unsigned i=0;i<count;i++)if(bo==&bos[i].bo)return &bos[i];
    std::abort();
}
extern "C" fd_bo *__wrap__fd_bo_new(fd_device *dev,uint32_t size,uint32_t flags)
{
    assert(!dev && count<4);
    const unsigned offsets[]={0x2000,0x1000,size>=1024?0x3000u:0x100u,0x1100};
    static const unsigned capacities[]={0x1000,0x100,0x800,0x100};
    assert(size && size<=capacities[count]);
    auto *r=&bos[count];r->offset=offsets[count];
    r->bo.size=size;r->bo.alloc_flags=flags;r->bo.refcnt=1;
    r->bo.handle=++count;r->bo.iova=gpu_base+r->offset;r->bo.map=arena+r->offset;
    std::memset(r->bo.map,0,size);
    return &r->bo;
}
extern "C" void __wrap__fd_bo_set_name(fd_bo *bo,const char *fmt,va_list ap)
{
    std::vsnprintf(record(bo)->name,sizeof(bos[0].name),fmt,ap);
}
extern "C" void *__wrap_fd_bo_map(fd_bo *bo){return record(bo)->bo.map;}
extern "C" void __wrap_fd_bo_upload(fd_bo *bo,void *src,unsigned offset,unsigned size)
{
    assert(src && offset<=bo->size && size<=bo->size-offset);
    std::memcpy((uint8_t *)record(bo)->bo.map+offset,src,size);
}
extern "C" void __wrap_fd_bo_mark_for_dump(fd_bo *bo){(void)record(bo);}
extern "C" void __wrap_fd_bo_del(fd_bo *bo){(void)record(bo);}
extern "C" uint32_t __wrap_fd_bo_size(fd_bo *bo){return record(bo)->bo.size;}
static void attach(fd_ringbuffer *r,fd_bo *bo){assert(r==&ring);record(bo)->attached=true;}
static void check_attached(fd_ringbuffer *r,fd_bo *bo){assert(r==&ring && record(bo)->attached);}
static void unexpected_grow(fd_ringbuffer *,uint32_t){std::abort();}
static bool check_size(fd_ringbuffer *r){return r==&ring && r->cur<=r->end;}
extern "C" fd_ringbuffer *__wrap_fd_submit_new_ringbuffer(fd_submit *submit,uint32_t size,fd_ringbuffer_flags flags)
{
    assert(submit==(fd_submit *)1 && !size && !ring.start);
    assert(flags==(FD_RINGBUFFER_PRIMARY|FD_RINGBUFFER_GROWABLE));
    static const fd_ringbuffer_funcs funcs={.grow=unexpected_grow,.attach_bo=attach,.assert_attached=check_attached,.check_size=check_size};
    ring.start=ring.cur=commands;ring.end=commands+4096;ring.size=sizeof(commands);
    ring.refcnt=1;ring.flags=flags;ring.funcs=&funcs;
    return &ring;
}
static void save(const char *path,const void *bytes,size_t length)
{
    FILE *f=std::fopen(path,"wb");assert(f);
    assert(std::fwrite(bytes,1,length,f)==length);assert(!std::fclose(f));
}
int main(int argc,char **argv)
{
    if(argc!=5 && argc!=6){std::fprintf(stderr,"usage: %s shader.asm payload.bin command.bin manifest.json [input16.ppm]\n",argv[0]);return 2;}
    for(unsigned i=0;i<4096;i++)((uint32_t *)arena)[i]=0xc0dec000u^i;
    const fd_dev_id id={.gpu_id=750,.chip_id=0x43051401};
    backend *b=a6xx_init<A7XX>(nullptr,&id);assert(b);
#ifdef WAFFLE_GLSL_EXPORT
    ir3_shader_variant *v=waffle_glsl_variant(argv[1]);assert(v);
    auto *compiled=(ir3_kernel *)std::calloc(1,sizeof(ir3_kernel));assert(compiled);
    compiled->v=v;compiled->bin=v->bin;compiled->backend=b;
    compiled->info.numwg=compiled->info.wgid=INVALID_REG;
    compiled->base.num_bufs=1;compiled->base.buf_sizes[0]=512;
    for(unsigned i=0;i<3;i++)compiled->base.local_size[i]=v->local_size[i];
    for(unsigned i=0;i<MAX_BUFS;i++)compiled->base.buf_addr_regs[i]=INVALID_REG;
    compiled->base.buf_types[0]=KERNEL_BUF_UAV;
    v->bo=fd_bo_new(nullptr,v->info.size,FD_BO_NOMAP,"CL");
    fd_bo_upload(v->bo,v->bin,0,v->info.size);
    kernel *k=&compiled->base;
#else
    FILE *input=std::fopen(argv[1],"r");assert(input);
    kernel *k=b->assemble(b,input);std::fclose(input);
#endif
    assert(k && count==2);
    assert(k->num_bufs==1 && (k->buf_sizes[0]==8 || k->buf_sizes[0]==256 || k->buf_sizes[0]==512));
    assert(k->local_size[0]==(k->buf_sizes[0]==512?256:k->buf_sizes[0]) && k->local_size[1]==1 && k->local_size[2]==1);
    auto *ir=to_ir3_kernel(k);assert(!ir->v->pvtmem_size && !ir->v->shared_size);
    k->bufs[0]=fd_bo_new(nullptr,k->buf_sizes[0]*4,0,"output");
    for(unsigned i=0;i<k->buf_sizes[0];i++)((uint32_t *)k->bufs[0]->map)[i]=0xdead0000u+i;
    if(k->buf_sizes[0]==512) {
        assert(argc==6);
        FILE *image=std::fopen(argv[5],"rb");assert(image);
        char header[13];assert(std::fread(header,1,13,image)==13);
        assert(!std::memcmp(header,"P6\n16 16\n255\n",13));
        for(unsigned i=0;i<256;i++){
            uint8_t rgb[3];assert(std::fread(rgb,1,3,image)==3);
            ((uint32_t *)k->bufs[0]->map)[256+i]=0xff000000u|rgb[0]|(rgb[1]<<8)|(rgb[2]<<16);
        }
        assert(std::fgetc(image)==EOF);std::fclose(image);
    } else assert(argc==5);
    uint32_t grid[3]={1,1,1};b->emit_grid(k,grid,(fd_submit *)1);
#ifdef WAFFLE_GLSL_EXPORT
    /* Exact A7xx compute bindless state from fd6_image.cc. Computerator's
     * bindful UAV upload alone cannot satisfy Gallium-lowered GLSL SSBOs. */
    unsigned exec=0,total=ring.cur-ring.start;
    while(exec<total && ((commands[exec]>>16)&0x7f)!=51)exec+=1+(commands[exec]&0x3fff);
    assert(exec<total);uint32_t tail[4096];unsigned tail_words=total-exec;
    std::memcpy(tail,commands+exec,tail_words*4);ring.cur=commands+exec;
    {
        fd_cs cs(&ring);
        fd_crb crb(cs,3);
        crb.add(SP_UPDATE_CNTL(A7XX,.cs_bindless=0xff));
        crb.add(SP_CS_BINDLESS_BASE_DESCRIPTOR(A7XX,0,.desc_size=BINDLESS_DESCRIPTOR_64B,.bo=&bos[3].bo));
    }
    assert(ring.cur+tail_words<=ring.end);std::memcpy(ring.cur,tail,tail_words*4);ring.cur+=tail_words;
#endif
    size_t words=ring.cur-ring.start;assert(count==4 && words && words*4<=0xc00);
    std::memcpy(arena+0x400,commands,words*4);
    save(argv[2],arena,sizeof(arena));save(argv[3],commands,words*4);
    FILE *m=std::fopen(argv[4],"w");assert(m);
    std::fprintf(m,"{\n  \"chip_id\": \"0x43051401\", \"generation\": 7,\n  \"gpu_base\": \"0x%llx\", \"command_offset\": 1024, \"command_dwords\": %zu,\n  \"bo_records\": [\n",(unsigned long long)gpu_base,words);
    for(unsigned i=0;i<count;i++){
        assert(bos[i].attached);
        std::fprintf(m,"    {\"name\": \"%s\", \"offset\": %u, \"bytes\": %u, \"iova\": \"0x%llx\"}%s\n",bos[i].name,bos[i].offset,bos[i].bo.size,(unsigned long long)bos[i].bo.iova,i+1<count?",":"");
    }
    std::fprintf(m,"  ],\n  \"device_opened\": false, \"gpu_executed\": false\n}\n");
    assert(!std::fclose(m));return 0;
}
