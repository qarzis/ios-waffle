/* Bounded PCM-onset -> qualified tap queue. No waveform fidelity or long
 * vibration claim. Caller serializes access; no PMIC operations here. */
#ifndef WAFFLE_HAPTIC_EVENTS_H
#define WAFFLE_HAPTIC_EVENTS_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
struct waffle_haptic_events {
 bool active,pending,fired;
 uint64_t frames,onsets,last_active,pending_at,last_fire;
};
static inline void waffle_haptic_events_feed(struct waffle_haptic_events *s,
 const int16_t *samples,size_t frames,uint64_t now)
{
 if(!s || !samples || !frames)return;
 uint32_t peak=0;
 for(size_t i=0;i<frames;i++) {
  uint32_t v=samples[i]<0?(uint32_t)-(int32_t)samples[i]:(uint32_t)samples[i];
  if(v>peak)peak=v;
 }
 s->frames+=frames;
 if(peak<=256){s->active=false;return;}
 if(!s->active || now-s->last_active>=30000) {
  s->pending=true;s->pending_at=now;s->onsets++;
 }
 s->active=true;s->last_active=now;
}
static inline bool waffle_haptic_events_take(struct waffle_haptic_events *s,uint64_t now)
{
 if(!s || !s->pending)return false;
 if(now-s->pending_at>100000){s->pending=false;return false;}
 if(s->fired && now-s->last_fire<80000)return false;
 s->pending=false;s->fired=true;s->last_fire=now;return true;
}
#endif
