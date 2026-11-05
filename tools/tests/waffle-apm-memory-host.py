#!/usr/bin/env python3
"""Byte-compare memory commands against actual pinned Linux functions, no DSP/DMA."""
from pathlib import Path
import re, subprocess, tempfile
root=Path(__file__).resolve().parents[2]
linux=root/'work/waffle/audio/upstream/linux'
base=linux/'sound/soc/qcom/qdsp6'
h=(base/'audioreach.h').read_text();c=(base/'audioreach.c').read_text();q=(base/'q6apm.c').read_text()
def struct(text,name):return re.search(r'struct '+name+r'\s*\{.*?\}\s*__packed;',text,re.S)[0]
program=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "waffle_apm_memory.h"
#define __packed __attribute__((packed))
#define GPR_HDR_SIZE 24
#define GPR_PKT_VER 0
#define GPR_PKT_HEADER_WORD_SIZE 6
#define GPR_DOMAIN_ID_ADSP 2
#define GPR_DOMAIN_ID_APPS 3
#define APM_MODULE_INSTANCE_ID 1
#define APM_CMD_HDR_SIZE 16
#define GFP_KERNEL 0
#define kzalloc(n,f) calloc(1,n)
#define kfree free
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>(uintptr_t)-4096)
#define ALIGN(n,a) (((n)+(a)-1)&~((a)-1))
#define lower_32_bits(n) ((uint32_t)(n))
#define upper_32_bits(n) ((uint32_t)((uint64_t)(n)>>32))
#define SNDRV_PCM_STREAM_PLAYBACK 0
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
struct apm_cmd_header {uint32_t a,b,c,payload_size;};
'''
program+=struct((linux/'include/linux/soc/qcom/apr.h').read_text(),'gpr_hdr')
program+='\nstruct gpr_pkt {struct gpr_hdr hdr;uint32_t payload[];};\n'
program+='\n'.join(line for line in h.splitlines() if re.match(r'#define (APM_CMD_SHARED_MEM_|APM_CMD_RSP_SHARED_MEM_|APM_MEMORY_MAP_SHMEM8_4K_POOL)',line))+'\n'
for name in ['apm_cmd_shared_mem_map_regions','apm_shared_map_region_payload','apm_cmd_shared_mem_unmap_regions']:
 program+=struct(h,name)+'\n'
program+=r'''
struct audio_buffer {uint64_t phys;};
struct audioreach_graph_data {struct audio_buffer *buf;uint32_t mem_map_handle;};
struct test_port {uint32_t id;};
struct q6apm_graph {struct audioreach_graph_data rx_data,tx_data;struct test_port *port;int lock;};
static unsigned char captured[64];static size_t captured_size;
static int audioreach_graph_send_cmd_sync(struct q6apm_graph *g,struct gpr_pkt *p,uint32_t rsp){(void)g;(void)rsp;captured_size=p->hdr.pkt_size;assert(captured_size<=64);memcpy(captured,p,captured_size);return 0;}
static void audioreach_graph_free_buf(struct q6apm_graph *g){(void)g;}
'''
program+=c[c.index('static void *__audioreach_alloc_pkt('):c.index('void *audioreach_alloc_pkt(')]
program+=c[c.index('void *audioreach_alloc_apm_pkt('):c.index('EXPORT_SYMBOL_GPL(audioreach_alloc_apm_pkt)')]
program+='\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wsign-compare"\n'
program+=c[c.index('int audioreach_map_memory_regions('):c.index('EXPORT_SYMBOL_GPL(audioreach_map_memory_regions)')]
program+='\n#pragma GCC diagnostic pop\n'
program+=q[q.index('int q6apm_unmap_memory_regions('):q.index('EXPORT_SYMBOL_GPL(q6apm_unmap_memory_regions)')]
program+=r'''
int main(void){
 struct audio_buffer buffer;struct test_port port={1};struct q6apm_graph g={.tx_data={&buffer,0x12345678},.port=&port};
 uint32_t out[16],untouched[16];
 for(unsigned sid=0;sid<2;sid++)for(uint32_t bytes=4096;bytes<=65536;bytes*=2){
  uint32_t id=sid?0x1061:0x1001;buffer.phys=0x11000000ull|((uint64_t)(id&15)<<32);
  assert(audioreach_map_memory_regions(&g,1,bytes,1,1)==0);
  size_t n=waffle_apm_memory_map(out,sizeof(out),1,id,0x11000000,bytes);
  assert(n==44&&captured_size==n&&!memcmp(out,captured,n));
 }
 assert(q6apm_unmap_memory_regions(&g,1)==0);
 assert(waffle_apm_memory_unmap(out,sizeof(out),1,0x12345678)==28&&captured_size==28&&!memcmp(out,captured,28));
 memset(out,0xa5,sizeof(out));memcpy(untouched,out,sizeof(out));
 assert(!waffle_apm_memory_map(NULL,64,1,0x1001,0x11000000,4096));
 assert(!waffle_apm_memory_map(out,43,1,0x1001,0x11000000,4096));
 assert(!waffle_apm_memory_map(out,64,0,0x1001,0x11000000,4096));
 assert(!waffle_apm_memory_map(out,64,1,0x1801,0x11000000,4096));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x9de80000,4096));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x0ffff000,4096));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x1ffff000,8192));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x10000001,4096));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x11000000,0));
 assert(!waffle_apm_memory_map(out,64,1,0x1001,0x11000000,4095));
 assert(!waffle_apm_memory_unmap(out,27,1,1));assert(!waffle_apm_memory_unmap(out,64,1,0));
 assert(!memcmp(out,untouched,sizeof(out)));
 puts("PASS actual Linux MAP44/UNMAP28 byte equality for native tagged IOVA/ten sizes; donor SID/raw PA/unaligned/overflow/zero/capacity rejected unchanged. Host serialization only, no SMMU/DSP/DMA.");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(program)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
