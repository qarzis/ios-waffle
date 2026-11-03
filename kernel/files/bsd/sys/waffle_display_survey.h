#ifndef WAFFLE_DISPLAY_SURVEY_H
#define WAFFLE_DISPLAY_SURVEY_H
#include <stdint.h>
#include <stdbool.h>
/* Read-only layout from PJD110 live DT and pinned SM8650 sde_hw_* sources.
 * This is a register snapshot, not permission to program a scanout address. */
struct waffle_display_io {void *context; bool (*read32)(void *,uint32_t,uint32_t *);};
static const uint32_t waffle_display_intf_base[4]={0x35000,0x36000,0x37000,0x38000};
static const uint32_t waffle_display_ctl_base[6]={0x16000,0x17000,0x18000,0x19000,0x1a000,0x1b000};
static const uint32_t waffle_display_sspp_base[10]={0x5000,0x7000,0x9000,0xb000,0x25000,0x27000,0x29000,0x2b000,0x2d000,0x2f000};
struct waffle_display_intf {uint32_t timing,config,config2,count_en,frame,line,tear_en,tear_out,tear_line,ts_ctrl,ts_lo,ts_hi,rd_count,auto_refresh,status,mdp_frame;};
struct waffle_display_ctl {uint32_t top,status,intf_active,sspp_active;};
struct waffle_display_sspp {uint32_t size,xy,out_size,out_xy,address,stride,format,op_mode;};
struct waffle_display_snapshot {uint32_t version;struct waffle_display_intf intf[4];struct waffle_display_ctl ctl[6];struct waffle_display_sspp sspp[10];};
static inline bool waffle_display_read(const struct waffle_display_io *io,uint32_t off,uint32_t *v)
{return io && io->read32 && v && !(off&3) && off<=0x83ffc && io->read32(io->context,off,v);}
static inline bool waffle_display_capture(const struct waffle_display_io *io,struct waffle_display_snapshot *s,bool layout)
{
 if(!s || !waffle_display_read(io,0,&s->version) || !s->version || s->version==UINT32_MAX)return false;
 for(unsigned i=0;i<4;i++){
  uint32_t b=waffle_display_intf_base[i];struct waffle_display_intf *p=&s->intf[i];
#define WD_READ(o,f) do{if(!waffle_display_read(io,b+(o),&p->f))return false;}while(0)
  WD_READ(0x000,timing);WD_READ(0x004,config);WD_READ(0x060,config2);WD_READ(0x0a8,count_en);
  WD_READ(0x0ac,frame);WD_READ(0x0b0,line);WD_READ(0x284,tear_en);WD_READ(0x2ac,tear_out);WD_READ(0x2b0,tear_line);
  WD_READ(0x210,ts_ctrl);WD_READ(0x214,ts_lo);WD_READ(0x218,ts_hi);
  WD_READ(0x298,rd_count);WD_READ(0x2b4,auto_refresh);WD_READ(0x26c,status);WD_READ(0x0a4,mdp_frame);
#undef WD_READ
 }
 if(!layout)return true;
 for(unsigned i=0;i<6;i++){
  uint32_t b=waffle_display_ctl_base[i];struct waffle_display_ctl *p=&s->ctl[i];
#define WD_READ(o,f) do{if(!waffle_display_read(io,b+(o),&p->f))return false;}while(0)
  WD_READ(0x014,top);WD_READ(0x064,status);WD_READ(0x0f4,intf_active);WD_READ(0x0fc,sspp_active);
#undef WD_READ
 }
 for(unsigned i=0;i<10;i++){
  uint32_t b=waffle_display_sspp_base[i];struct waffle_display_sspp *p=&s->sspp[i];
#define WD_READ(o,f) do{if(!waffle_display_read(io,b+(o),&p->f))return false;}while(0)
  WD_READ(0x00,size);WD_READ(0x08,xy);WD_READ(0x0c,out_size);WD_READ(0x10,out_xy);WD_READ(0x14,address);WD_READ(0x24,stride);WD_READ(0x30,format);WD_READ(0x38,op_mode);
#undef WD_READ
 }
 return true;
}
#endif
