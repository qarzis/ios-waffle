#!/usr/bin/env python3
"""Compare Linux graph serialization with explicit modern GC type selection."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def definition(text, name):
    return re.search(r'struct '+name+r'\s*\{.*?\}\s*__packed;', text, re.S)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--linux', type=Path, required=True)
    args = ap.parse_args()
    base = args.linux/'sound/soc/qcom/qdsp6'
    h = (base/'audioreach.h').read_text()
    c = (base/'audioreach.c').read_text()
    mgmt = (base/'q6apm.c').read_text()
    apr = (args.linux/'include/linux/soc/qcom/apr.h').read_text()
    binding = (args.linux/'include/dt-bindings/soc/qcom,gpr.h').read_text()
    types = ['apm_cmd_header','apm_module_param_data','apm_sub_graph_cfg','apm_prop_data',
        'apm_sg_prop_id_perf_mode','apm_sg_prop_id_direction','apm_sg_prop_id_scenario_id',
        'apm_container_cfg','apm_cont_prop_id_graph_pos','apm_cont_prop_id_stack_size',
        'apm_cont_prop_id_domain','apm_module_obj','apm_module_prop_id_port_info','apm_module_conn_obj']
    macros = '\n'.join(line for line in h.splitlines() if re.match(r'#define (?:APM|GPR|MODULE_ID)_\w+\s+(?:0x[0-9A-Fa-f]+|[0-9]+|sizeof\([^\n]+\))\s*$',line))
    prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "waffle_apm.h"
typedef uint32_t u32;
#define __packed __attribute__((packed))
#define ALIGN(n,a) (((n)+(a)-1)&~((a)-1))
#define struct_size(p,m,n) (sizeof(*(p))+sizeof((p)->m[0])*(n))
#define EXPORT_SYMBOL_GPL(x)
#define GFP_KERNEL 0
#define kzalloc(n,f) calloc(1,n)
#define kfree(p) free(p)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>(uintptr_t)-4096)
struct list_head { struct list_head *next,*prev; };
#define INIT_LIST_HEAD(p) do { (p)->next=(p);(p)->prev=(p); } while(0)
#define list_entry(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(p=list_entry((h)->next,__typeof__(*p),m); &(p)->m!=(h); p=list_entry((p)->m.next,__typeof__(*p),m))
static void list_add_tail(struct list_head *n,struct list_head *h) { n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n; }
struct q6apm { int unused; };
struct audioreach_graph_info { unsigned num_sub_graphs; struct list_head sg_list; uint32_t src_mod_inst_id,src_mod_op_port_id,dst_mod_inst_id,dst_mod_ip_port_id; };
struct audioreach_sub_graph { uint32_t sub_graph_id,perf_mode,direction,scenario_id; struct list_head node,container_list; };
struct audioreach_container { uint32_t container_id,capability_id,graph_pos,stack_size,proc_domain,num_modules; struct list_head node,modules_list; };
struct audioreach_module { uint32_t module_id,instance_id,max_ip_port,max_op_port,num_connections; uint32_t src_mod_op_port_id[8],dst_mod_inst_id[8],dst_mod_ip_port_id[8]; struct list_head node; };
struct audioreach_graph { struct audioreach_graph_info *info; struct q6apm *apm; };
'''
    prefix += binding + definition(apr,'gpr_hdr') + '\nstruct gpr_pkt { struct gpr_hdr hdr; uint32_t payload[]; };\n'
    prefix += '#define GPR_HDR_SIZE sizeof(struct gpr_hdr)\n#define GPR_PKT_VER 0\n#define GPR_PKT_HEADER_WORD_SIZE 6\n'
    prefix += '\n'.join(definition(h,t) for t in types) + '\n' + macros + '\n'
    prefix += '#define APM_CMD_HDR_SIZE sizeof(struct apm_cmd_header)\n#define APM_MODULE_PARAM_DATA_SIZE sizeof(struct apm_module_param_data)\n'
    prefix += c[c.index('/* SubGraph Config */'):c.index('} __packed;',c.index('struct apm_graph_open_params'))+len('} __packed;')]
    prefix += c[c.index('static void *__audioreach_alloc_pkt('):c.index('void *audioreach_alloc_pkt(')]
    prefix += c[c.index('void *audioreach_alloc_apm_cmd_pkt('):c.index('EXPORT_SYMBOL_GPL(audioreach_alloc_apm_cmd_pkt)')]
    prefix += c[c.index('static void apm_populate_container_config('):c.index('EXPORT_SYMBOL_GPL(audioreach_alloc_graph_pkt)')]
    prefix += r'''
static unsigned char reference_close[128];static size_t close_size;
static int q6apm_send_cmd_sync(struct q6apm *apm,struct gpr_pkt *pkt,uint32_t response) {
 (void)apm;(void)response;close_size=pkt->hdr.pkt_size;assert(close_size<=sizeof(reference_close));memcpy(reference_close,pkt,close_size);return 0;
}
'''
    prefix += mgmt[mgmt.index('/* Graph Management */'):mgmt.index('static struct q6apm *g_apm;')]
    prefix += mgmt[mgmt.index('static int audioreach_graph_mgmt_cmd('):mgmt.index('static void q6apm_put_audioreach_graph(')]
    test = r'''
int main(void) {
 struct audioreach_graph_info info={.num_sub_graphs=1};
 struct audioreach_sub_graph sg={.sub_graph_id=WAFFLE_APM_SUBGRAPH,.perf_mode=2,.direction=2,.scenario_id=1};
 struct audioreach_container cont={.container_id=WAFFLE_APM_CONTAINER,.capability_id=1,.graph_pos=1,.stack_size=UINT32_MAX,.proc_domain=2,.num_modules=2};
 struct audioreach_module wr={.module_id=MODULE_ID_WR_SHARED_MEM_EP,.instance_id=WAFFLE_APM_WRITE_EP,.max_op_port=1,.num_connections=1,.src_mod_op_port_id={1},.dst_mod_inst_id={WAFFLE_APM_READ_EP},.dst_mod_ip_port_id={2}};
 struct audioreach_module rd={.module_id=MODULE_ID_RD_SHARED_MEM_EP,.instance_id=WAFFLE_APM_READ_EP,.max_ip_port=1};
 INIT_LIST_HEAD(&info.sg_list);INIT_LIST_HEAD(&sg.container_list);INIT_LIST_HEAD(&cont.modules_list);
 list_add_tail(&sg.node,&info.sg_list);list_add_tail(&cont.node,&sg.container_list);list_add_tail(&wr.node,&cont.modules_list);list_add_tail(&rd.node,&cont.modules_list);
 struct gpr_pkt *reference=audioreach_alloc_graph_pkt(NULL,&info);assert(!IS_ERR(reference));
 uint32_t packet[128];memset(packet,0xa5,sizeof(packet));
 size_t size=waffle_apm_packet(packet,sizeof(packet),WAFFLE_APM_GRAPH_OPEN,0);
 assert(size==344 && reference->hdr.pkt_size==size);
 unsigned differences=0;
 for(unsigned i=0;i<size/4;i++)if(((uint32_t *)reference)[i]!=packet[i]){
  assert(i>=3 && packet[i-3]==0x08001011 && packet[i-2]==8 && packet[i-1]==1);
  assert(((uint32_t *)reference)[i]==1 && packet[i]==WAFFLE_APM_CONTAINER_TYPE_GC);differences++;
 }
 assert(differences==1);free(reference);
 cont.capability_id=WAFFLE_APM_CONTAINER_TYPE_GC;
 reference=audioreach_alloc_graph_pkt(NULL,&info);assert(!IS_ERR(reference));
 assert(!memcmp(reference,packet,size));free(reference);
 struct audioreach_graph graph={.info=&info};assert(!audioreach_graph_mgmt_cmd(&graph,APM_CMD_GRAPH_CLOSE));
 size=waffle_apm_packet(packet,sizeof(packet),WAFFLE_APM_GRAPH_CLOSE,0);
 assert(size==64 && close_size==size && !memcmp(reference_close,packet,size));
 memset(packet,0xa5,sizeof(packet));assert(!waffle_apm_packet(packet,343,WAFFLE_APM_GRAPH_OPEN,0));
 for(unsigned i=0;i<128;i++) assert(packet[i]==0xa5a5a5a5);
 assert(!waffle_apm_packet(packet,sizeof(packet),0x01001013,0));
 assert(waffle_apm_packet(packet,sizeof(packet),WAFFLE_APM_GRAPH_OPEN,17)==344 && packet[4]==17);
 puts("PASS: OPEN344 differs from legacy Linux by exactly one type word; byte-identical serializer with explicit modernGC input; CLOSE64 unchanged. No DMA addresses; capacity/opcode/token checked; native firmware unqualified.");
}
'''
    with tempfile.TemporaryDirectory(prefix='waffle-apm-host-') as temp:
        p=Path(temp)
        (p/'test.c').write_text(prefix+test)
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-sign-compare',
            '-fsanitize=address,undefined','-g','-I',str(ROOT/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
        subprocess.run([str(p/'test')],check=True)


if __name__=='__main__':
    main()
