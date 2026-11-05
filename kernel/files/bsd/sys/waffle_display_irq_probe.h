#ifndef WAFFLE_DISPLAY_IRQ_PROBE_H
#define WAFFLE_DISPLAY_IRQ_PROBE_H
#include "waffle_display_completion.h"
#include "waffle_display_flip.h"
/* Diagnostic only: observe a fresh masked PP0 flag under the unchanged guard.
 * PP0 clear=top(0x1000)+INTR_CLEAR(0x18), mask=BIT8, pinned sde_hwio.h.
 * Only native single-link PP0 mux encodings 0 and 0xf0000 are admitted. No IRQ mask/mode/address write. */
struct waffle_display_irq_probe_io {struct waffle_display_io read;bool (*write32)(void *,uint32_t,uint32_t);};
struct waffle_display_irq_probe_state {uint32_t sequence,baseline,target;bool baseline_valid,committed,attempted,armed,fresh;};
struct waffle_display_irq_probe_result {uint32_t action,status_after,mux,version;bool wrote;};
static inline void waffle_display_irq_probe_begin(struct waffle_display_irq_probe_state *s,uint32_t sequence,const struct waffle_display_completion_sample *v)
{
 *s=(struct waffle_display_irq_probe_state){0};s->sequence=sequence;s->baseline=v->frame_before;s->baseline_valid=v->frame_before==v->frame_after;
}
static inline void waffle_display_irq_probe_commit(struct waffle_display_irq_probe_state *s,uint32_t sequence,const struct waffle_display_completion_sample *v)
{
 if(s->sequence!=sequence || !s->baseline_valid || v->frame_before!=v->frame_after || v->address0!=v->address1 ||
    (v->address0!=WAFFLE_DISPLAY_FRONT && v->address0!=WAFFLE_DISPLAY_TEST))return;
 s->target=v->address0;s->committed=true;
}
static inline struct waffle_display_irq_probe_result waffle_display_irq_probe_step(const struct waffle_display_irq_probe_io *io,
 struct waffle_display_irq_probe_state *s,uint32_t sequence,const struct waffle_display_completion_sample *v)
{
 struct waffle_display_irq_probe_result r={0};
 if(!io || !s || !v || !s->committed || s->sequence!=sequence || v->frame_before!=v->frame_after ||
    v->address0!=s->target || v->address1!=s->target || v->flush || v->ctl_active!=2)return r;
 uint32_t delta=v->frame_before-s->baseline;
 if(!delta || delta>=0x80000000u)return r;
 if(s->armed && !s->fresh && !v->irq_top_enable && (v->irq_top&0x100u)){
  s->fresh=true;r.action=2;r.status_after=v->irq_top;return r;
 }
 if(s->attempted || delta!=1 || !v->auto_status || v->ctl_active!=2)return r;
 s->attempted=true;
 if(v->irq_top_enable || !(v->irq_top&0x100u)){r.action=3;return r;}
 uint32_t enable,frame,busy,flush,a,b;
 if(!waffle_display_read(&io->read,0,&r.version) || !waffle_display_read(&io->read,0x3625c,&r.mux) ||
    !waffle_display_read(&io->read,0x1010,&enable) || !waffle_display_read(&io->read,0x362c0,&busy) ||
    !waffle_display_read(&io->read,0x16018,&flush) || !waffle_display_read(&io->read,0x5014,&a) ||
    !waffle_display_read(&io->read,0x7014,&b) || !waffle_display_read(&io->read,0x360a4,&frame)){r.action=4;return r;}
 if(r.version!=0xa0000000u || (r.mux && r.mux!=0xf0000u) || enable || !busy || flush || a!=s->target || b!=s->target || frame!=v->frame_before){r.action=3;return r;}
 if(!io->write32 || !io->write32(io->read.context,0x1018,0x100)){r.action=4;return r;}
 r.wrote=true;
 if(!waffle_display_read(&io->read,0x1014,&r.status_after) || (r.status_after&0x100u)){r.action=4;return r;}
 s->armed=true;r.action=1;return r;
}
#endif
