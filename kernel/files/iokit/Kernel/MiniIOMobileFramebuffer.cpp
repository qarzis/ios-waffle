#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <IOKit/IOKitKeys.h>
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSBoolean.h>
#include <kern/thread_call.h>
#include <kern/thread.h>
#include <kern/clock.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <sys/proc.h>
#include <vm/memory_types.h>
#include "../../bsd/sys/waffle_display_survey.h"
#include "../../bsd/sys/waffle_vsync_phase.h"
#include "../../bsd/sys/waffle_display_smmu.h"
#include "../../bsd/sys/waffle_display_flush.h"
#include "../../bsd/sys/waffle_display_flip.h"
#include "../../bsd/sys/waffle_display_present.h"
#include "../../bsd/sys/waffle_display_source.h"
extern "C" {
#include <console/video_console.h>
extern struct vc_info vinfo;
}
#include <IOKit/IOBufferMemoryDescriptor.h>
#include "MiniIOSurface.h"
extern "C" void redwood_tl(const char * format, ...) __printflike(1, 2);
extern "C" vm_offset_t ml_io_map_unmappable(vm_offset_t, vm_size_t, unsigned int);
extern "C" void ml_io_unmap(vm_offset_t, vm_size_t);
static TUNABLE(uint32_t, gWaffleDisplaySurvey, "waffle_vsync_audit", 0);
static TUNABLE(uint32_t, gWaffleDisplayFlush, "waffle_display_flush", 0);
static TUNABLE(uint32_t, gWaffleDisplayFlip, "waffle_display_flip", 0);
static TUNABLE(uint32_t, gWaffleDisplayPresent, "waffle_display_present", 0);
static bool waffleDisplayRead(void *context, uint32_t offset, uint32_t *value)
{
 if (offset > 0x83ffc || (offset & 3)) return false;
 *value = *(volatile uint32_t *)((uint8_t *)context + offset);
 return true;
}
static bool waffleDisplayFlushWrite(void *context, uint32_t offset, uint32_t value)
{
 if (gWaffleDisplayFlush != 1 || offset != 0x16018 || value != 3) return false;
 *(volatile uint32_t *)((uint8_t *)context + offset) = value;
 __asm__ volatile("dsb sy" ::: "memory");
 return true;
}
static void waffleDisplayFlushDelay(void *, unsigned ms) {IOSleep(ms);}
static void waffleDisplayFlushProbe(void *, wait_result_t)
{
 IOSleep(1500);
 vm_offset_t base = ml_io_map_unmappable(0xae00000, 0x84000, VM_WIMG_IO);
 if (!base) {redwood_tl("waffle-display-flush: passed=0 reason=map writes=0\n");thread_terminate(current_thread());return;}
 struct waffle_display_flush_io io = {{(void *)base, waffleDisplayRead}, waffleDisplayFlushWrite, waffleDisplayFlushDelay};
 struct waffle_display_flush_result r = {};
 bool ok = waffle_display_flush_unchanged(&io, &r);
 redwood_tl("waffle-display-flush: passed=%u stage=%u writes=%u mask=%x pending=%x pre_polls=%u polls=%u\n",
     ok, r.stage, r.writes, r.mask, r.pending, r.pre_polls, r.polls);
 redwood_tl("waffle-display-flush: frame_before=%u frame_after=%u address_writes=0 start_writes=0 irq_ack=0 mode_change=0\n",
     r.before_frame, r.after_frame);
 ml_io_unmap(base, 0x84000);
 thread_terminate(current_thread());
}
static bool waffleDisplaySMMURead(void *context, uint32_t offset, uint32_t *value)
{
 if (offset > 0xffffc || (offset & 3)) return false;
 *value = *(volatile uint32_t *)((uint8_t *)context + offset);
 return true;
}
static void waffleDisplaySMMUSurvey(void)
{
 vm_offset_t base = ml_io_map_unmappable(0x15000000, 0x100000, VM_WIMG_IO);
 if (!base) {redwood_tl("waffle-display-smmu: complete=0 reason=map no_writes=1\n");return;}
 struct waffle_display_smmu_io io = {(void *)base, waffleDisplaySMMURead};
 struct waffle_display_smmu_snapshot snapshot = {};
 bool ok = waffle_display_smmu_capture(&io, &snapshot);
 redwood_tl("waffle-display-smmu: complete=%u cr0=%x id0=%x id1=%x id2=%x groups=%u banks=%u page_shift=%u cb_base=%x no_writes=1\n",
     ok, snapshot.cr0, snapshot.id0, snapshot.id1, snapshot.id2, snapshot.groups, snapshot.banks, snapshot.page_shift, snapshot.cb_base);
 for (unsigned i = 0; i < 2; i++) {
  const struct waffle_display_smmu_route *r = &snapshot.stream[i];
  redwood_tl("waffle-display-smmu: sid=%x matches=%u index=%u smr=%x s2cr=%x cb=%u context_read=%u\n",
      r->sid, r->matches, r->index, r->smr, r->s2cr, r->cb, r->context_read);
  if (r->context_read) {
   redwood_tl("waffle-display-smmu: sid=%x cbar=%x sctlr=%x tcr=%x tcr2=%x fsr=%x\n",
       r->sid, r->cbar, r->sctlr, r->tcr, r->tcr2, r->fsr);
   redwood_tl("waffle-display-smmu: sid=%x ttbr0=%llx ttbr1=%llx\n", r->sid,
       (unsigned long long)r->ttbr0, (unsigned long long)r->ttbr1);
  }
 }
 ml_io_unmap(base, 0x100000);
}
struct WaffleDisplayFlipContext {vm_offset_t dpu, smmu, target;unsigned writes;void *owner;bool quiescing;};
static bool waffleDisplayFlipRead(void *p, uint32_t offset, uint32_t *value)
{return waffleDisplayRead((void *)((WaffleDisplayFlipContext *)p)->dpu, offset, value);}
static bool waffleDisplayFlipWrite(void *p, uint32_t offset, uint32_t value)
{
 WaffleDisplayFlipContext *c = (WaffleDisplayFlipContext *)p;
 if ((gWaffleDisplayFlip != 1 && gWaffleDisplayPresent != 1) || !((offset == 0x16018 && value == 3) ||
     ((offset == 0x5014 || offset == 0x7014) && (value == WAFFLE_DISPLAY_FRONT || value == WAFFLE_DISPLAY_TEST)))) return false;
 *(volatile uint32_t *)(c->dpu + offset) = value;
 __asm__ volatile("dsb sy" ::: "memory");c->writes++;
 return true;
}
static bool waffleDisplayFlipDomain(void *p)
{
 WaffleDisplayFlipContext *c = (WaffleDisplayFlipContext *)p;
 struct waffle_display_smmu_io io = {(void *)c->smmu, waffleDisplaySMMURead};
 struct waffle_display_smmu_snapshot snapshot = {};
 return waffle_display_smmu_capture(&io, &snapshot) && waffle_display_flip_domain_valid(&snapshot);
}
static bool waffleDisplayFlipPrepare(void *p, uint32_t address, uint32_t bytes)
{
 WaffleDisplayFlipContext *c = (WaffleDisplayFlipContext *)p;
 if (address != WAFFLE_DISPLAY_TEST || bytes != WAFFLE_DISPLAY_FRAME || c->target) return false;
 c->target = ml_io_map_unmappable(address, bytes, VM_WIMG_IO);
 if (!c->target) return false;
 redwood_tl("waffle-display-flip: preparing_reserved=%x bytes=%u original_untouched=1\n", address, bytes);
 volatile uint32_t *pixels = (volatile uint32_t *)c->target;
 for (uint32_t y = 0; y < 3168; y++) {
  for (uint32_t x = 0; x < 1440; x++) {
   uint32_t color = 0xff202020;
   if (x >= 400 && x < 1040 && y >= 1264 && y < 1904) {
    color = y < 1584 ? (x < 720 ? 0xff00ffff : 0xffff00ff) : (x < 720 ? 0xffffff00 : 0xff44aa44);
   }
   pixels[y * 1440 + x] = color;
  }
 }
 __asm__ volatile("dsb sy" ::: "memory");
 return true;
}
static void waffleDisplayFlipProbe(void *, wait_result_t)
{
 IOSleep(25000);
 WaffleDisplayFlipContext c = {};
 c.dpu = ml_io_map_unmappable(0xae00000, 0x84000, VM_WIMG_IO);
 c.smmu = ml_io_map_unmappable(0x15000000, 0x100000, VM_WIMG_IO);
 if (c.dpu && c.smmu) {
  struct waffle_display_flip_io io = {{{&c, waffleDisplayFlipRead}, waffleDisplayFlipWrite, waffleDisplayFlushDelay}, waffleDisplayFlipDomain, waffleDisplayFlipPrepare};
  struct waffle_display_flip_result r = {};
  bool ok = waffle_display_flip_test(&io, &r);
  redwood_tl("waffle-display-flip: passed=%u stage=%u prepared=%u flipped=%u restored=%u writes=%u hold_ms=5000\n",
      ok, r.stage, r.prepared, r.flipped, r.restored, c.writes);
  redwood_tl("waffle-display-flip: domain_flip=%u domain_restore=%u restore_attempted=%u flip_frame=%u restore_frame=%u\n",
      r.domain_after_flip, r.domain_after_restore, r.restore_attempted, r.flip_frame, r.restore_frame);
  if (c.target) ml_io_unmap(c.target, WAFFLE_DISPLAY_FRAME);
 } else redwood_tl("waffle-display-flip: passed=0 reason=map writes=0\n");
 if (c.smmu) ml_io_unmap(c.smmu, 0x100000);
 if (c.dpu) ml_io_unmap(c.dpu, 0x84000);
 thread_terminate(current_thread());
}
struct WaffleDisplayPresentState {
 WaffleDisplayFlipContext context;
 IOBufferMemoryDescriptor *working;
 uint8_t *front;
 struct waffle_display_present_io io;
 struct waffle_display_present_state state;
 uint64_t copyNanos;
 uint32_t sourceReads,sourceChanges,pixelChanges;
};
static WaffleDisplayPresentState *gWafflePresenter;
static void waffleDisplayPresentDelay(void *p, unsigned ms)
{
 WaffleDisplayFlipContext *c = (WaffleDisplayFlipContext *)p;
 if (c->quiescing) delay_for_interval(ms, NSEC_PER_MSEC);
 else IOSleep(ms);
}
static bool waffleDisplayPresentCopy(void *p, uint32_t address)
{
 WaffleDisplayFlipContext *c = (WaffleDisplayFlipContext *)p;
 WaffleDisplayPresentState *s = (WaffleDisplayPresentState *)c->owner;
 if (!s || c->quiescing || address == s->state.active ||
     (address != WAFFLE_DISPLAY_FRONT && address != WAFFLE_DISPLAY_TEST)) return false;
 uint8_t *to = address == WAFFLE_DISPLAY_FRONT ? s->front : (uint8_t *)c->target;
 uint64_t began = mach_absolute_time();
 memcpy(to, s->working->getBytesNoCopy(), WAFFLE_DISPLAY_FRAME);
 if (address == WAFFLE_DISPLAY_FRONT) {
  for (uintptr_t at = (uintptr_t)to; at < (uintptr_t)to + WAFFLE_DISPLAY_FRAME; at += 64)
   __asm__ volatile("dc cvac, %0" :: "r"(at) : "memory");
 }
 __asm__ volatile("dsb sy" ::: "memory");
 absolutetime_to_nanoseconds(mach_absolute_time() - began, &s->copyNanos);
 return true;
}
static WaffleDisplayPresentState *waffleDisplayPresentCreate(uint8_t *front)
{
 if (__atomic_load_n(&gWafflePresenter, __ATOMIC_ACQUIRE) || ((uintptr_t)front & 63)) return NULL;
 WaffleDisplayPresentState *s = (WaffleDisplayPresentState *)IOMallocZero(sizeof(*s));
 if (!s) return NULL;
 s->front = front;s->context.owner = s;
 s->context.dpu = ml_io_map_unmappable(0xae00000, 0x84000, VM_WIMG_IO);
 s->context.smmu = ml_io_map_unmappable(0x15000000, 0x100000, VM_WIMG_IO);
 /* Match the boot console's RAM framebuffer mapping (video_console.c).
  * Keep DPU/SMMU registers as device memory; only reserved pixel RAM uses WCOMB.
  */
 s->context.target = ml_io_map_unmappable(WAFFLE_DISPLAY_TEST, WAFFLE_DISPLAY_FRAME, VM_WIMG_WCOMB);
 s->working = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task, kIODirectionInOut, WAFFLE_DISPLAY_FRAME, PAGE_SIZE);
 s->io = {{{{&s->context, waffleDisplayFlipRead}, waffleDisplayFlipWrite, waffleDisplayPresentDelay}, waffleDisplayFlipDomain, NULL}, waffleDisplayPresentCopy};
 if (!s->context.dpu || !s->context.smmu || !s->context.target || !s->working ||
     !s->working->getBytesNoCopy() || !waffle_display_present_init(&s->io, &s->state)) {
  if (s->working) s->working->release();
  if (s->context.target) ml_io_unmap(s->context.target, WAFFLE_DISPLAY_FRAME);
  if (s->context.smmu) ml_io_unmap(s->context.smmu, 0x100000);
  if (s->context.dpu) ml_io_unmap(s->context.dpu, 0x84000);
  IOFree(s, sizeof(*s));return NULL;
 }
 memcpy(s->working->getBytesNoCopy(), front, WAFFLE_DISPLAY_FRAME);
 __atomic_store_n(&gWafflePresenter, s, __ATOMIC_RELEASE);
 redwood_tl("waffle-display-present: armed=1 working_bytes=%u front=%x back=%x\n", WAFFLE_DISPLAY_FRAME, WAFFLE_DISPLAY_FRONT, WAFFLE_DISPLAY_TEST);
 return s;
}
/* loader_return has already stopped the other CPUs. No allocation, sleeping
 * locks or scheduler-dependent waits are allowed on this path. */
extern "C" void waffle_display_quiesce(void)
{
 WaffleDisplayPresentState *s = __atomic_load_n(&gWafflePresenter, __ATOMIC_ACQUIRE);
 if (!s) return;
 s->context.quiescing = true;
 bool restored = waffle_display_present_restore(&s->io, &s->state);
 redwood_tl("waffle-display-present: quiesced=1 restored=%u completed=%u active=%x\n", restored, s->state.completed, s->state.active);
}
static void waffleDisplaySurvey(void *, wait_result_t)
{
 IOSleep(1000);
 vm_offset_t base = ml_io_map_unmappable(0xae00000, 0x84000, VM_WIMG_IO);
 if (!base) {redwood_tl("waffle-vsync: survey map_failed=1 no_writes=1\n");thread_terminate(current_thread());return;}
 struct waffle_display_io io = {(void *)base, waffleDisplayRead};
 struct waffle_display_snapshot snapshot = {};
 bool ok = waffle_display_capture(&io, &snapshot, true);
 redwood_tl("waffle-vsync: layout version=%x complete=%u no_writes=1\n", snapshot.version, ok);
 if (ok) {
  for (unsigned i = 0; i < 6; i++) {
   const struct waffle_display_ctl *p = &snapshot.ctl[i];
   redwood_tl("waffle-vsync: ctl=%u base=%x top=%x status=%x intf_active=%x fetch_active=%x\n",
       i, waffle_display_ctl_base[i], p->top, p->status, p->intf_active, p->sspp_active);
  }
  for (unsigned i = 0; i < 10; i++) {
   const struct waffle_display_sspp *p = &snapshot.sspp[i];
   redwood_tl("waffle-vsync: sspp=%u base=%x size=%x xy=%x out=%x out_xy=%x address=%x stride=%x format=%x op=%x\n",
       i, waffle_display_sspp_base[i], p->size, p->xy, p->out_size, p->out_xy, p->address, p->stride, p->format, p->op_mode);
  }
  const uint64_t first = mach_absolute_time();
  redwood_tl("waffle-vsync: clock cntfrq=%llu first_ticks=%llu samples=32 requested_gap_ms=2\n",
      (unsigned long long)__builtin_arm_rsr64("CNTFRQ_EL0"), (unsigned long long)first);
  for (unsigned i = 0; i < 4; i++) {
   const struct waffle_display_intf *p = &snapshot.intf[i];
   redwood_tl("waffle-vsync: intf_config=%u timing=%x config=%x config2=%x status=%x count_en=%x tear_en=%x auto=%x ts_ctrl=%x\n",
       i, p->timing, p->config, p->config2, p->status, p->count_en, p->tear_en, p->auto_refresh, p->ts_ctrl);
  }
  for (unsigned sample = 0; sample < 32 && ok; sample++) {
   uint64_t before = mach_absolute_time();
   ok = waffle_display_capture(&io, &snapshot, false);
   uint64_t after = mach_absolute_time(), elapsed_ns = 0, read_ns = 0;
   if (!ok) break;
   absolutetime_to_nanoseconds(after - first, &elapsed_ns);
   absolutetime_to_nanoseconds(after - before, &read_ns);
   redwood_tl("waffle-vsync: stamp=%u ticks=%llu elapsed_ns=%llu read_ns=%llu\n",
       sample, (unsigned long long)after, (unsigned long long)elapsed_ns, (unsigned long long)read_ns);
   for (unsigned i = 0; i < 4; i++) {
    const struct waffle_display_intf *p = &snapshot.intf[i];
    redwood_tl("waffle-vsync: sample=%u intf=%u frame=%u mdp_frame=%u line=%u rd_count=%x tear_out=%u tear_line=%u ts_lo=%x ts_hi=%x\n",
        sample, i, p->frame, p->mdp_frame, p->line, p->rd_count, p->tear_out, p->tear_line, p->ts_lo, p->ts_hi);
   }
   IOSleep(2);
  }
 }
 ml_io_unmap(base, 0x84000);
 waffleDisplaySMMUSurvey();
 redwood_tl("waffle-vsync: survey_complete=%u no_register_writes=1 no_irq_ack=1 no_timing_change=1\n", ok);
 thread_terminate(current_thread());
}
static TUNABLE(uint32_t, gWaffleHardwareVSync, "waffle_vsync", 0);
static inline uint32_t refreshHz(void);
static vm_offset_t gWaffleVSyncMap;
static uint64_t gWaffleVSyncPeriod;
static uint32_t gWaffleVSyncDivider;
static bool gWaffleVSyncReady;
static bool waffleVSyncReady(void) {return __atomic_load_n(&gWaffleVSyncReady, __ATOMIC_ACQUIRE);}
static void waffleVSyncQualify(void *, wait_result_t)
{
 vm_offset_t base = ml_io_map_unmappable(0xae00000, 0x84000, VM_WIMG_IO);
 if (!base) {redwood_tl("waffle-vsync: hardware_ready=0 reason=map\n");thread_terminate(current_thread());return;}
 struct waffle_display_io io = {(void *)base, waffleDisplayRead};
 struct waffle_display_snapshot snapshot = {};
 const uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
 bool valid = waffle_display_capture(&io, &snapshot, true) && frequency == 19200000 &&
     snapshot.version == 0xa0000000 && snapshot.ctl[0].intf_active == 2 &&
     snapshot.intf[1].tear_en == 9 && snapshot.intf[1].ts_ctrl == 0x21 &&
     snapshot.intf[1].auto_refresh == 0x80000001 &&
     snapshot.sspp[0].size == 0x0c6002d0 && snapshot.sspp[1].size == 0x0c6002d0 &&
     snapshot.sspp[0].stride == 5760 && snapshot.sspp[1].stride == 5760 &&
     snapshot.sspp[0].address != 0 && snapshot.sspp[0].address == snapshot.sspp[1].address;
 struct waffle_vsync_clock clock = {(void *)base, waffleDisplayRead};
 uint64_t first = 0, last = 0, period = 0;
 unsigned edges = 0;
 for (unsigned attempt = 0; valid && attempt < 250 && edges < 8; attempt++) {
  uint64_t stamp = 0;
  valid = waffle_vsync_timestamp(&clock, &stamp);
  uint64_t now = mach_absolute_time();
  valid = valid && stamp && stamp <= now && now - stamp < frequency / 20;
  if (!valid) break;
  if (!first) first = last = stamp;
  else if (stamp > last) {
   uint64_t delta = stamp - last;
   if (delta < frequency / 240 || delta > frequency / 30) {valid = false;break;}
   last = stamp;edges++;
  } else if (stamp < last) {valid = false;break;}
  IOSleep(1);
 }
 uint32_t divider = 0;
 if (valid && edges == 8) {
  period = (last - first) / edges;
  divider = waffle_vsync_divider(frequency, period, refreshHz());
 }
 if (valid && divider) {
  gWaffleVSyncMap = base;
  gWaffleVSyncPeriod = period;
  gWaffleVSyncDivider = divider;
  __atomic_store_n(&gWaffleVSyncReady, true, __ATOMIC_RELEASE);
  redwood_tl("waffle-vsync: hardware_ready=1 intf=1 source=panel_TE frequency=%llu period_ticks=%llu divider=%u requested_hz=%u edges=%u no_register_writes=1\n",
      (unsigned long long)frequency, (unsigned long long)period, divider, refreshHz(), edges);
 } else {
  ml_io_unmap(base, 0x84000);
  redwood_tl("waffle-vsync: hardware_ready=0 reason=qualification edges=%u valid=%u divider=%u software_fallback=1\n", edges, valid, divider);
 }
 thread_terminate(current_thread());
}
enum {
 kFBMethodGetLayerDefaultSurface = 3,
 kFBMethodSwapBegin = 4,
 kFBMethodSwapEnd = 5,
 kFBMethodSwapWait = 6,
 kFBMethodGetID = 7,
 kFBMethodGetDisplaySize = 8,
 kFBMethodRequestPowerChange = 12,
 kFBMethodSwapSignal = 20,
 kFBMethodGetDigitalOutState = 25,
 kFBMethodGetDotPitch = 28,
 kFBMethodGetDisplayArea = 29,
 kFBMethodSwapCancel = 52,
 kFBMethodGetColorRemapMode = 57,
 kFBMethodNotifications = 72,
 kFBMethodChangeFrameInfo = 73,
 kFBMethodSupportedFrameInfo = 74,
 kFBMethodGetCurrentAbsoluteTime = 77,
 kFBMethodGetBlock = 79,
 kFBMethodSwapCancelAll = 81,
 kFBMethodGetProtectionOptions = 82,
};
#define SWAP_SIZE 0x46c
#define SWAP_ID 0x50
#define SWAP_SURFACE(layer) (0x54 + 4 * (layer))
#define SWAP_SOURCE(layer) (0x64 + 16 * (layer))
#define SWAP_ENABLED(layer) (0xa4 + 4 * (layer))
#define SWAP_DEST(layer) (0xc4 + 16 * (layer))
#define SWAP_LAYERS_SET 0x104
#define SWAP_LAYERS_CLEARED 0x108
#define SWAP_LAYERS 4
#define kFBNotifyVSync 5
#define kFBNotifyTypes 8
#define kFBRefreshHz 60
#define FRAME_TIMES 64
#define FRAME_PAUSE 90
#define SWAP_GPU_MS 500
#define SWAP_HELD_MS 700
#define FOURCC(a,b,c,d) ((uint32_t)(a) << 24 | (uint32_t)(b) << 16 | (uint32_t)(c) << 8 | (uint32_t)(d))
static uint64_t gFBLogged[2];
static uint8_t gFBCalls[128];
#define kFBDefaultWidth 1125
#define kFBDefaultHeight 2436
#define kFBDotsPerInch 458
#define kFBMacanWidth 1290
#define kFBMacanHeight 2796
#define kFBMacanSubtype 2796
#define kFBMacanDotsPerInch 460
static TUNABLE(uint32_t, gFBWidth, "fbwidth", kFBDefaultWidth);
static TUNABLE(uint32_t, gFBHeight, "fbheight", kFBDefaultHeight);
#define kFBPointsWide 375
#define kFBPointsHigh 812
#define kFBDefaultScale 3
static TUNABLE(uint32_t, gFBScale, "fbscale", 0);
static TUNABLE(uint32_t, gFBTrace, "fbtrace", 3);
static TUNABLE(uint32_t, gRecSeconds, "rec_secs", 0);
static TUNABLE(uint32_t, gRecStart, "rec_start", 0);
static TUNABLE(uint32_t, gRecMegabytes, "rec_mb", 480);
static TUNABLE(uint32_t, gRecRing, "rec_ring", 0);
static TUNABLE(uint32_t, gRecStep, "rec_step", 3);
static TUNABLE(uint32_t, gDiff, "fb_diff", 0);
static TUNABLE(uint32_t, gFilter, "fb_filter", 1);
static TUNABLE(uint32_t, gRefreshHz, "fb_hz", kFBRefreshHz);
static TUNABLE(uint32_t, gOnTheBeat, "fb_beat", 1);
static TUNABLE(uint32_t, gThreads, "fb_threads", 3);
#define SWAP_QUEUE 2
static TUNABLE(uint32_t, gQueue, "fb_queue", 2);
static inline unsigned
swapQueue(void)
{
 return gQueue >= 1 && gQueue <= SWAP_QUEUE ? gQueue : 1;
}
static TUNABLE(uint32_t, gTouchLat, "touch_lat", 0);
static inline uint64_t
micros(uint64_t absolute)
{
 uint64_t ns;
 absolutetime_to_nanoseconds(absolute, &ns);
 return ns / 1000;
}
static TUNABLE(uint32_t, gMacan, "macan", 0);
static TUNABLE(uint32_t, gWaffle, "waffle", 0);
/* Waffle display consumer lease: held until CPU presentation completes. */
static TUNABLE(uint32_t, gWaffleDisplayUse, "waffle_display_use", 0);
static TUNABLE(uint32_t, gWaffleTorch, "waffle_torch", 0);
static TUNABLE(uint32_t, gMacan14, "macan_14pm", 0);
static inline uint32_t
refreshHz(void)
{
 if (gRefreshHz == kFBRefreshHz && gMacan != 0) {
  return 120;
 }
 return gRefreshHz >= 1 && gRefreshHz <= 240 ? gRefreshHz : kFBRefreshHz;
}
static void
macanButtonsNode(void)
{
 IORegistryEntry * root = IORegistryEntry::fromPath("/", gIODTPlane);
 IORegistryEntry * buttons = IORegistryEntry::fromPath("/buttons", gIODTPlane);
 uint32_t type = 2;
 if (buttons == NULL && root != NULL) {
  buttons = new IORegistryEntry;
  if (buttons != NULL && (!buttons->init() || !buttons->attachToParent(root, gIODTPlane))) {
   buttons->release();
   buttons = NULL;
  } else if (buttons != NULL) {
   buttons->setName("buttons", gIODTPlane);
   buttons->setName("buttons");
   buttons->retain();
  }
 }
 if (buttons != NULL) {
  buttons->setProperty("home-button-type", &type, sizeof(type));
  buttons->release();
 }
 if (root != NULL) {
  root->release();
 }
}
static TUNABLE(uint32_t, gMacanHaptic, "haptic", 5);
static TUNABLE(uint32_t, gMacanTorch, "torch", 3);
static IORegistryEntry *
macanProductChild(IORegistryEntry *product, const char *name)
{
 char path[80];
 snprintf(path, sizeof(path), "/product/%s", name);
 IORegistryEntry *child = IORegistryEntry::fromPath(path, gIODTPlane);
 if (child != NULL) {
  return child;
 }
 child = new IORegistryEntry;
 if (child != NULL && (!child->init() || !child->attachToParent(product, gIODTPlane))) {
  child->release();
  return NULL;
 }
 if (child != NULL) {
  child->setName(name, gIODTPlane);
  child->setName(name);
 }
 return child;
}
static void
macanPeripheralNodes(void)
{
 IORegistryEntry *product = IORegistryEntry::fromPath("/product", gIODTPlane);
 uint32_t yes = 1;
 if (product == NULL) {
  return;
 }
 if (gMacanHaptic != 0) {
  IORegistryEntry *haptics = macanProductChild(product, "haptics");
  if (haptics != NULL) {
   haptics->setProperty("closed-loop", &yes, sizeof(yes));
   haptics->setProperty("supports-3rd-party-haptics", &yes, sizeof(yes));
   haptics->release();
  }
 }
 if (gMacanTorch != 0) {
  IORegistryEntry *camera = macanProductChild(product, "camera");
  if (camera != NULL) {
   camera->setProperty("flash", &yes, sizeof(yes));
   camera->release();
  }
 }
 product->release();
}
static void
wafflePeripheralNodes(void)
{
 if (gWaffleTorch != 3) return;
 IORegistryEntry *product=IORegistryEntry::fromPath("/product",gIODTPlane);
 if (product==NULL) return;
 IORegistryEntry *camera=macanProductChild(product,"camera");
 if (camera!=NULL) {
  uint32_t yes=1;
  camera->setProperty("flash",&yes,sizeof(yes));
  camera->release();
 }
 product->release();
}
extern "C" bool redwood_gpu_ready(void);
extern "C" void redwood_gpu_to_memory(void *start, uint64_t size);
static inline uint32_t
recStep(void)
{
 return gRecStep >= 2 && gRecStep <= 8 ? gRecStep : 3;
}
#define REC_STEP recStep()
struct rec_header {
 char magic[8];
 uint32_t width, height;
 uint32_t frames;
 uint32_t oldest;
 uint64_t began;
};
struct rec_frame {
 uint64_t nanoseconds;
};
extern "C" uint64_t loader_recording[3];
extern "C" void loader_log_putc(char);
static uint32_t
swapWord(const uint8_t * swap, unsigned offset)
{
 uint32_t value;
 memcpy(&value, swap + offset, sizeof(value));
 return value;
}
struct RowJob;
class IOMobileFramebuffer : public IOService
{
 OSDeclareDefaultStructors(IOMobileFramebuffer);
public:
 IOLock * fLock;
 uint8_t * fBase;
 WaffleDisplayPresentState * fWafflePresenter;
 bool fWafflePresentTried;
 uint32_t fPanelWidth, fPanelHeight, fRowBytes;
 uint32_t fWidth, fHeight;
 MiniIOSurface * fDefaultSurface;
 uint32_t fSwapID;
 uint32_t fSwapsShown;
 uint32_t fLayersShown;
 bool fGraphics;
 IOLock * fSwapLock;
 uint8_t fSwap[SWAP_QUEUE][SWAP_SIZE];
 MiniIOSurface * fSwapSurfaces[SWAP_QUEUE][SWAP_LAYERS];
 unsigned fSwapFirst, fSwapsWaiting;
 uint64_t fSwapIssued, fSwapCompleted, fSwapTickets[SWAP_QUEUE];
 bool waitForPresentation(uint64_t ticket);
 void retireSource(uint64_t ticket);
 uint64_t fBeat;
 uint64_t fReady;
 uint32_t fStatOnBeat;
 uint64_t fStatBeatWait;
 uint32_t fStatSurfaces[8];
 uint32_t fStatHeld, fStatLost;
 uint64_t fSwapTime;
 uint32_t fStatSwapsLate;
 uint64_t fStatWaiting;
 uint32_t fStatFrames;
 uint64_t fStatSince, fStatDrawing;
 uint64_t fLastFrame;
 uint32_t fFrameTimes[FRAME_TIMES + 1], fFramePauses, fFrameLongest;
 bool fDiff;
 uint64_t fDiffPixels;
 uint32_t fDiffLeft, fDiffTop, fDiffRight, fDiffBottom;
 uint32_t * fColumn;
 uint16_t * fColumnWeight;
 uint32_t * fBlendRow;
 uint32_t fBlendRowSize;
 uint8_t * fRecBase;
 uint64_t fRecSize, fRecUsed;
 uint64_t fFirstFrame, fRecFirst;
 bool fRecDone;
 bool fRecWrapped;
 virtual bool start(IOService * provider) APPLE_KEXT_OVERRIDE;
 void publishModes(void);
 MiniIOSurface * defaultSurface(void);
 void present(const uint8_t * swap);
 void show(const uint8_t * swap, MiniIOSurface ** surfaces, uint64_t ticket);
 void presenter(void);
 static void presenterMain(void * self, wait_result_t result);
 void reportFrameTimes(void);
 void drawLayer(MiniIOSurface * s, const int32_t * src, const int32_t * dst);
 void drawRows(const struct RowJob * job, int32_t y0, int32_t y1, uint32_t * blendRow);
 static void helperMain(void * self, wait_result_t result);
 unsigned fThreads;
 IOLock * fHelperLock;
 const struct RowJob * fHelperJob;
 uint64_t fHelperGeneration;
 unsigned fHelpersBusy, fHelpersStarted;
 uint32_t * fHelperBlend[7];
 void record(MiniIOSurface * s);
};
OSDefineMetaClassAndStructors(IOMobileFramebuffer, IOService);
static void
setNumber(OSDictionary * dict, const char * key, uint64_t value)
{
 OSNumber * n = OSNumber::withNumber(value, 32);
 if (n != NULL) {
  dict->setObject(key, n);
  n->release();
 }
}
#define kFBTimingID 1
#define kFBColorID 1
void
IOMobileFramebuffer::publishModes(void)
{
 OSDictionary * timing = OSDictionary::withCapacity(8);
 OSDictionary * horizontal = OSDictionary::withCapacity(4);
 OSDictionary * vertical = OSDictionary::withCapacity(4);
 OSDictionary * color = OSDictionary::withCapacity(8);
 OSArray * timings = OSArray::withCapacity(1);
 OSArray * colors = OSArray::withCapacity(1);
 const uint32_t rate = refreshHz() << 16;
 if (timing == NULL || horizontal == NULL || vertical == NULL || color == NULL || timings == NULL || colors == NULL) {
  return;
 }
 setNumber(color, "ID", kFBColorID);
 setNumber(color, "PixelEncoding", 0);
 setNumber(color, "Depth", 8);
 setNumber(color, "Colorimetry", 1);
 setNumber(color, "EOTF", 1);
 setNumber(color, "DynamicRange", 0);
 setNumber(color, "Score", 1);
 color->setObject("IsVirtual", kOSBooleanFalse);
 colors->setObject(color);
 setNumber(horizontal, "Active", fWidth);
 setNumber(horizontal, "Total", fWidth);
 setNumber(horizontal, "SyncRate", rate);
 setNumber(horizontal, "PreciseSyncRate", rate);
 setNumber(vertical, "Active", fHeight);
 setNumber(vertical, "Total", fHeight);
 setNumber(vertical, "SyncRate", rate);
 setNumber(vertical, "PreciseSyncRate", rate);
 setNumber(timing, "ID", kFBTimingID);
 setNumber(timing, "Score", 1);
 timing->setObject("IsVirtual", kOSBooleanFalse);
 timing->setObject("IsOverscanned", kOSBooleanFalse);
 timing->setObject("HorizontalAttributes", horizontal);
 timing->setObject("VerticalAttributes", vertical);
 timing->setObject("ColorModes", colors);
 timings->setObject(timing);
 setProperty("TimingElements", timings);
 setProperty("ColorElements", colors);
 OSDictionary * refresh = OSDictionary::withCapacity(2);
 if (refresh != NULL) {
  OSNumber * interval = OSNumber::withNumber((1ULL << 32) / refreshHz(), 64);
  OSNumber * step = OSNumber::withNumber(0ULL, 64);
  if (interval != NULL && step != NULL) {
   refresh->setObject("displayMinRefreshInterval", interval);
   refresh->setObject("displayRefreshStepMachTime", step);
   setProperty("IOMFBDisplayRefresh", refresh);
  }
  OSSafeReleaseNULL(interval);
  OSSafeReleaseNULL(step);
  OSSafeReleaseNULL(refresh);
 }
 OSSafeReleaseNULL(timings);
 OSSafeReleaseNULL(colors);
 OSSafeReleaseNULL(timing);
 OSSafeReleaseNULL(horizontal);
 OSSafeReleaseNULL(vertical);
 OSSafeReleaseNULL(color);
}
bool
IOMobileFramebuffer::start(IOService * provider)
{
 thread_t thread;
 if (!IOService::start(provider)) {
  return false;
 }
 if (vinfo.v_baseaddr == 0 || vinfo.v_width == 0 || vinfo.v_height == 0 || vinfo.v_depth != 32) {
  IOLog("MiniIOMobileFramebuffer: no usable boot framebuffer (%ux%u, depth %u)\n", vinfo.v_width, vinfo.v_height,
      vinfo.v_depth);
  return false;
 }
 fWafflePresenter = NULL;fWafflePresentTried = false;
 fSwapIssued = fSwapCompleted = 0;
 bzero(fSwapTickets, sizeof(fSwapTickets));
 fLock = IOLockAlloc();
 fSwapLock = IOLockAlloc();
 if (kernel_thread_start(&IOMobileFramebuffer::presenterMain, this, &thread) != KERN_SUCCESS) {
  IOLog("MiniIOMobileFramebuffer: no thread to put frames on the panel with\n");
  return false;
 }
 thread_set_thread_name(thread, "frames to the panel");
 thread_deallocate(thread);
 fThreads = gThreads >= 1 && gThreads <= 8 ? gThreads : 1;
 if (gMacan != 0 && gThreads == 3) {
  fThreads = 6;
 }
 fHelperLock = IOLockAlloc();
 for (unsigned i = 0; i + 1 < fThreads; i++) {
  if (kernel_thread_start(&IOMobileFramebuffer::helperMain, this, &thread) != KERN_SUCCESS) {
   fThreads = i + 1;
   break;
  }
  thread_set_thread_name(thread, "frames to the panel: a helper");
  thread_deallocate(thread);
 }
 fBase = (uint8_t *) vinfo.v_baseaddr;
 fPanelWidth = vinfo.v_width;
 fPanelHeight = vinfo.v_height;
 fRowBytes = vinfo.v_rowbytes;
 fWidth = gFBWidth ? gFBWidth : fPanelWidth;
 fHeight = gFBHeight ? gFBHeight : fPanelHeight;
 if (gMacan != 0) {
  macanPeripheralNodes();
 }
 if (gWaffle != 0) wafflePeripheralNodes();
 if (gWaffle != 0 && gWaffleHardwareVSync == 1) {
  thread_t qualify;
  kern_return_t result = kernel_thread_start(waffleVSyncQualify, NULL, &qualify);
  redwood_tl("waffle-vsync: hardware_qualification_start=%x\n", result);
  if (result == KERN_SUCCESS) thread_deallocate(qualify);
 }
 if (gWaffle != 0 && gWaffleDisplayFlip == 1) {
  thread_t probe;
  kern_return_t result = kernel_thread_start(waffleDisplayFlipProbe, NULL, &probe);
  if (result == KERN_SUCCESS) thread_deallocate(probe);
  redwood_tl("waffle-display-flip: worker_start=%x hold_ms=5000 restore_required=1\n", result);
 }
 if (gWaffle != 0 && gWaffleDisplayFlush == 1) {
  thread_t probe;
  kern_return_t result = kernel_thread_start(waffleDisplayFlushProbe, NULL, &probe);
  if (result == KERN_SUCCESS) thread_deallocate(probe);
  redwood_tl("waffle-display-flush: worker_start=%x unchanged_frame_only=1\n", result);
 }
 if (gWaffle != 0 && gWaffleDisplaySurvey == 1) {
  thread_t survey;
  kern_return_t result = kernel_thread_start(waffleDisplaySurvey, NULL, &survey);
  redwood_tl("waffle-vsync: survey_start=%x framebuffer=%p panel=%ux%u stride=%u\n", result, fBase, fPanelWidth, fPanelHeight, fRowBytes);
  if (result == KERN_SUCCESS) thread_deallocate(survey);
 }

 if (gMacan != 0 && gMacan14 != 0 && gFBWidth == kFBDefaultWidth && gFBHeight == kFBDefaultHeight &&
     (gFBScale == 0 || gFBScale == kFBDefaultScale)) {
  uint32_t subtype = kFBMacanSubtype;
  IORegistryEntry * product = IORegistryEntry::fromPath("/product", gIODTPlane);
  fWidth = kFBMacanWidth;
  fHeight = kFBMacanHeight;
  if (product != NULL) {
   product->setProperty("artwork-device-subtype", &subtype, sizeof(subtype));
   product->release();
  }
  macanButtonsNode();
 }
 if (gFBScale != 0 && gFBScale != kFBDefaultScale) {
  static const char * const places[][2] = { { "/chosen", "display-scale" }, { "/product", "artwork-scale-factor" } };
  uint32_t scale = gFBScale;
  fWidth = kFBPointsWide * scale;
  fHeight = kFBPointsHigh * scale;
  for (unsigned i = 0; i < sizeof(places) / sizeof(places[0]); i++) {
   IORegistryEntry * node = IORegistryEntry::fromPath(places[i][0], gIODTPlane);
   if (node != NULL) {
    node->setProperty(places[i][1], &scale, sizeof(scale));
    node->release();
   }
  }
 }
 fColumn = IONewZero(uint32_t, fPanelWidth);
 fColumnWeight = IONewZero(uint16_t, fPanelWidth);
 fDiff = gDiff != 0;
 fDiffLeft = fDiffTop = ~0u;
 IOLog("MiniIOMobileFramebuffer: display %ux%u on a panel of %ux%u (%u bytes per row)\n", fWidth, fHeight,
     fPanelWidth, fPanelHeight, fRowBytes);
 if (gRecSeconds != 0) {
  IOBufferMemoryDescriptor * memory = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task,
      kIODirectionInOut | kIOMemoryPhysicallyContiguous, (mach_vm_size_t) gRecMegabytes << 20, ~0ULL);
  if (memory != NULL) {
   struct rec_header * header = (struct rec_header *) memory->getBytesNoCopy();
   fRecBase = (uint8_t *) header;
   fRecSize = (uint64_t) gRecMegabytes << 20;
   fRecUsed = sizeof(*header);
   bzero(header, sizeof(*header));
   memcpy(header->magic, "RWREC003", 8);
   header->width = fWidth / REC_STEP;
   header->height = fHeight / REC_STEP;
   loader_recording[0] = memory->getPhysicalSegment(0, NULL);
   loader_recording[1] = fRecUsed;
   loader_recording[2] = (uint64_t) (uintptr_t) fRecBase;
   IOLog("MiniIOMobileFramebuffer: recording %u s of the screen at %ux%u from second %u, into %u MB at %#llx%s\n",
       gRecSeconds, header->width, header->height, gRecStart, gRecMegabytes, loader_recording[0],
       gRecRing ? ", the last of it kept (rec_ring)" : "");
  } else {
   IOLog("MiniIOMobileFramebuffer: no memory for a recording of %u MB\n", gRecMegabytes);
  }
 }
 setProperty(kIOUserClientClassKey, "IOMobileFramebufferUserClient");
 setProperty("RedwoodWaitsForGPU", kOSBooleanTrue);
 publishModes();
 setName("disp0");
 registerService();
 return true;
}
void
IOMobileFramebuffer::record(MiniIOSurface * s)
{
 struct rec_header * header = (struct rec_header *) fRecBase;
 uint64_t now = mach_absolute_time(), since_first, since_start = 0, frame_size;
 struct rec_frame * frame;
 uint8_t * to;
 if (fFirstFrame == 0) {
  fFirstFrame = now;
 }
 if (fRecBase == NULL || fRecDone || s->info.width < fWidth || s->info.height < fHeight) {
  return;
 }
 absolutetime_to_nanoseconds(now - fFirstFrame, &since_first);
 if (since_first < (uint64_t) gRecStart * NSEC_PER_SEC) {
  return;
 }
 if (fRecFirst == 0) {
  uint64_t began;
  fRecFirst = now;
  absolutetime_to_nanoseconds(now, &began);
  header->began = began;
  IOLog("MiniIOMobileFramebuffer: the recording begins at %llu.%03llu s of the kernel's time (mach_absolute_time)\n",
      began / NSEC_PER_SEC, began / NSEC_PER_MSEC % 1000);
 }
 absolutetime_to_nanoseconds(now - fRecFirst, &since_start);
 frame_size = sizeof(*frame) + (uint64_t) header->width * header->height * 3;
 if (since_start > (uint64_t) gRecSeconds * NSEC_PER_SEC || (fRecUsed + frame_size > fRecSize && !gRecRing)) {
  fRecDone = true;
  IOLog("MiniIOMobileFramebuffer: recording finished: %u frames, %llu MB\n", header->frames, fRecUsed >> 20);
  return;
 }
 if (fRecUsed + frame_size > fRecSize) {
  fRecUsed = sizeof(*header);
  fRecWrapped = true;
 }
 frame = (struct rec_frame *) (fRecBase + fRecUsed);
 frame->nanoseconds = since_start;
 to = (uint8_t *) (frame + 1);
 for (uint32_t y = 0; y < header->height; y++) {
  const uint32_t * from = (const uint32_t *) (s->pixels() + (size_t) (y * REC_STEP + 1) * s->info.bytesPerRow);
  for (uint32_t x = 0; x < header->width; x++) {
   uint32_t pixel = from[x * REC_STEP + 1];
   *to++ = (uint8_t) (pixel >> 16);
   *to++ = (uint8_t) (pixel >> 8);
   *to++ = (uint8_t) pixel;
  }
 }
 fRecUsed += frame_size;
 if (!fRecWrapped) {
  header->frames++;
  loader_recording[1] = fRecUsed;
 } else {
  header->oldest = (uint32_t) ((fRecUsed - sizeof(*header)) / frame_size);
  if (header->oldest >= header->frames) {
   header->oldest = 0;
  }
  loader_recording[1] = sizeof(*header) + (uint64_t) header->frames * frame_size;
 }
}
MiniIOSurface *
IOMobileFramebuffer::defaultSurface(void)
{
 IOLockLock(fLock);
 if (fDefaultSurface == NULL) {
  fDefaultSurface = MiniIOSurfaceCreateSimple(fWidth, fHeight, FOURCC('B', 'G', 'R', 'A'));
 }
 IOLockUnlock(fLock);
 return fDefaultSurface;
}
static inline uint32_t
blend(uint32_t a, uint32_t b, uint32_t w)
{
 uint32_t rb = ((a & 0xff00ff) * (256 - w) + (b & 0xff00ff) * w) >> 8 & 0xff00ff;
 uint32_t ga = ((a >> 8 & 0xff00ff) * (256 - w) + (b >> 8 & 0xff00ff) * w) & 0xff00ff00;
 return rb | ga;
}
static inline int64_t
sample_at(int64_t i, int64_t in, int64_t out)
{
 int64_t at = ((2 * i + 1) * in - out) * 128 / out;
 return at < 0 ? 0 : at > (in - 1) * 256 ? (in - 1) * 256 : at;
}
struct RowJob {
 const uint8_t * pixels;
 uint32_t stride;
 int32_t sx, sy, sw, sh, px0, py0, px1, py1, cx0, cx1;
 bool filter, unscaled;
};
void
IOMobileFramebuffer::drawRows(const RowJob * job, int32_t y0, int32_t y1, uint32_t * blendRow)
{
 const uint8_t * pixels = job->pixels;
 uint32_t stride = job->stride;
 int32_t sx = job->sx, sy = job->sy, sw = job->sw, sh = job->sh;
 int32_t px0 = job->px0, py0 = job->py0, px1 = job->px1, py1 = job->py1, cx0 = job->cx0, cx1 = job->cx1;
 bool filter = job->filter;
 for (int32_t y = y0; y < y1; y++) {
  const uint32_t * from;
  uint32_t * to;
  if (y < 0 || (uint32_t) y >= fPanelHeight) {
   continue;
  }
  to = (uint32_t *) (fBase + (size_t) y * fRowBytes);
  if (job->unscaled) {
   memcpy(to + px0, pixels + (size_t) (sy + y - py0) * stride + (size_t) sx * 4, (size_t) sw * 4);
   continue;
  }
  if (filter) {
   int64_t at = sample_at(y - py0, sh, py1 - py0);
   uint32_t row = (uint32_t) (at >> 8), weight = (uint32_t) (at & 255);
   const uint32_t * upper = (const uint32_t *) (pixels + (size_t) (sy + row) * stride) + sx;
   if (weight == 0 || row + 1 >= (uint32_t) sh) {
    from = upper;
   } else {
    const uint32_t * lower = (const uint32_t *) (pixels + (size_t) (sy + row + 1) * stride) + sx;
    uint32_t first = fColumn[cx0], last = fColumn[cx1 - 1] + 1 < (uint32_t) sw ? fColumn[cx1 - 1] + 1 : fColumn[cx1 - 1];
    uint32_t * __restrict mixed = blendRow;
    for (uint32_t c = first; c <= last; c++) {
     uint32_t a = upper[c], b = lower[c];
     mixed[c] = a == b ? a : blend(a, b, weight);
    }
    from = blendRow;
   }
  } else {
   from = (const uint32_t *) (pixels + (size_t) (sy + (int64_t) (y - py0) * sh / (py1 - py0)) * stride);
  }
  if (fDiff) {
   for (int32_t x = cx0; x < cx1; x++) {
    uint32_t value = filter ? blend(from[fColumn[x]], from[fColumn[x] + (fColumnWeight[x] != 0)], fColumnWeight[x]) :
        from[fColumn[x]];
    if (to[x] != value) {
     fDiffPixels++;
     fDiffLeft = (uint32_t) x < fDiffLeft ? (uint32_t) x : fDiffLeft;
     fDiffRight = (uint32_t) x > fDiffRight ? (uint32_t) x : fDiffRight;
     fDiffTop = (uint32_t) y < fDiffTop ? (uint32_t) y : fDiffTop;
     fDiffBottom = (uint32_t) y > fDiffBottom ? (uint32_t) y : fDiffBottom;
    }
   }
  }
  if (filter) {
   const uint32_t * __restrict column = fColumn + cx0;
   const uint16_t * __restrict weights = fColumnWeight + cx0;
   uint32_t * __restrict out = to + cx0;
   for (uint32_t i = 0, n = (uint32_t) (cx1 - cx0); i < n; i++) {
    uint32_t c = column[i], w = weights[i], a = from[c];
    out[i] = w == 0 || a == from[c + 1] ? a : blend(a, from[c + 1], w);
   }
  } else {
   for (int32_t x = cx0; x < cx1; x++) {
    to[x] = from[fColumn[x]];
   }
  }
 }
}
void
IOMobileFramebuffer::helperMain(void * self, wait_result_t result __unused)
{
 IOMobileFramebuffer * fb = (IOMobileFramebuffer *) self;
 unsigned index;
 uint64_t done = 0;
 IOLockLock(fb->fHelperLock);
 index = fb->fHelpersStarted++;
 IOLockUnlock(fb->fHelperLock);
 for (;;) {
  const RowJob * job;
  int32_t rows, y0, y1;
  uint32_t * blend;
  IOLockLock(fb->fHelperLock);
  while (fb->fHelperGeneration == done) {
   IOLockSleep(fb->fHelperLock, &fb->fHelperGeneration, THREAD_UNINT);
  }
  done = fb->fHelperGeneration;
  job = fb->fHelperJob;
  IOLockUnlock(fb->fHelperLock);
  rows = job->py1 - job->py0;
  y0 = job->py0 + (int32_t) ((int64_t) rows * (index + 1) / fb->fThreads);
  y1 = job->py0 + (int32_t) ((int64_t) rows * (index + 2) / fb->fThreads);
  blend = fb->fHelperBlend[index];
  fb->drawRows(job, y0, y1, blend);
  IOLockLock(fb->fHelperLock);
  fb->fHelpersBusy--;
  if (fb->fHelpersBusy == 0) {
   IOLockWakeup(fb->fHelperLock, &fb->fHelpersBusy, true);
  }
  IOLockUnlock(fb->fHelperLock);
 }
}
void
IOMobileFramebuffer::drawLayer(MiniIOSurface * s, const int32_t * src, const int32_t * dst)
{
 int32_t sx = src[0], sy = src[1], sw = src[2], sh = src[3];
 int32_t dx = dst[0], dy = dst[1], dw = dst[2], dh = dst[3];
 int32_t px0, py0, px1, py1, cx0, cx1;
 bool filter = gFilter != 0;
 RowJob job;
 if (sw <= 0 || sh <= 0) {
  sx = sy = 0;
  sw = (int32_t) s->info.width;
  sh = (int32_t) s->info.height;
 }
 if (dw <= 0 || dh <= 0) {
  dx = dy = 0;
  dw = (int32_t) fWidth;
  dh = (int32_t) fHeight;
 }
 if (sx < 0 || sy < 0 || (uint32_t) (sx + sw) > s->info.width || (uint32_t) (sy + sh) > s->info.height) {
  return;
 }
 px0 = (int32_t) ((int64_t) dx * fPanelWidth / fWidth);
 py0 = (int32_t) ((int64_t) dy * fPanelHeight / fHeight);
 px1 = (int32_t) ((int64_t) (dx + dw) * fPanelWidth / fWidth);
 py1 = (int32_t) ((int64_t) (dy + dh) * fPanelHeight / fHeight);
 /* Reject invisible rectangles before the filtered row path indexes its
  * clipped column interval. An entirely offscreen layer has no columns. */
 if (px1 <= px0 || py1 <= py0 || px1 <= 0 || py1 <= 0 ||
     px0 >= (int32_t) fPanelWidth || py0 >= (int32_t) fPanelHeight) {
  return;
 }
 if (filter && fBlendRowSize < (uint32_t) sw) {
  if (fBlendRow != NULL) {
   IODelete(fBlendRow, uint32_t, fBlendRowSize);
  }
  for (unsigned i = 0; i + 1 < fThreads; i++) {
   if (fHelperBlend[i] != NULL) {
    IODelete(fHelperBlend[i], uint32_t, fBlendRowSize);
   }
  }
  fBlendRowSize = (uint32_t) sw;
  fBlendRow = IONew(uint32_t, fBlendRowSize);
  for (unsigned i = 0; i + 1 < fThreads; i++) {
   fHelperBlend[i] = IONew(uint32_t, fBlendRowSize);
   if (fHelperBlend[i] == NULL && fBlendRow != NULL) {
    IODelete(fBlendRow, uint32_t, fBlendRowSize);
    fBlendRow = NULL;
   }
  }
  if (fBlendRow == NULL) {
   fBlendRowSize = 0;
  }
 }
 filter = filter && fBlendRow != NULL;
 cx0 = px0 < 0 ? 0 : px0;
 cx1 = (uint32_t) px1 > fPanelWidth ? (int32_t) fPanelWidth : px1;
 for (int32_t x = cx0; x < cx1; x++) {
  if (filter) {
   int64_t at = sample_at(x - px0, sw, px1 - px0);
   fColumn[x] = (uint32_t) (at >> 8);
   fColumnWeight[x] = (uint16_t) (fColumn[x] + 1 < (uint32_t) sw ? at & 255 : 0);
  } else {
   fColumn[x] = (uint32_t) (sx + (int64_t) (x - px0) * sw / (px1 - px0));
  }
 }
 job.pixels = s->pixels();
 job.stride = s->info.bytesPerRow;
 job.sx = sx;
 job.sy = sy;
 job.sw = sw;
 job.sh = sh;
 job.px0 = px0;
 job.py0 = py0;
 job.px1 = px1;
 job.py1 = py1;
 job.cx0 = cx0;
 job.cx1 = cx1;
 job.filter = filter;
 job.unscaled = px1 - px0 == sw && py1 - py0 == sh && px0 >= 0 && (uint32_t) px1 <= fPanelWidth;
 if (redwood_gpu_ready()) {
  redwood_gpu_to_memory((void *) (job.pixels + (size_t) sy * job.stride), (uint64_t) sh * job.stride);
 }
 if (fThreads <= 1 || fDiff || fHelpersStarted + 1 < fThreads) {
  drawRows(&job, py0, py1, fBlendRow);
  return;
 }
 IOLockLock(fHelperLock);
 fHelperJob = &job;
 fHelpersBusy = fThreads - 1;
 fHelperGeneration++;
 IOLockWakeup(fHelperLock, &fHelperGeneration, false);
 IOLockUnlock(fHelperLock);
 drawRows(&job, py0, py0 + (int32_t) ((int64_t) (py1 - py0) / fThreads), fBlendRow);
 IOLockLock(fHelperLock);
 while (fHelpersBusy != 0) {
  IOLockSleep(fHelperLock, &fHelpersBusy, THREAD_UNINT);
 }
 IOLockUnlock(fHelperLock);
}
void
IOMobileFramebuffer::reportFrameTimes(void)
{
 static const uint32_t limits[] = { 10, 18, 26, 35, FRAME_TIMES + 1 };
 uint32_t within[sizeof(limits) / sizeof(limits[0])] = { 0 }, total = 0, sum = 0, half = 0, most = 0;
 for (uint32_t ms = 0; ms <= FRAME_TIMES; ms++) {
  for (uint32_t i = 0; i < sizeof(limits) / sizeof(limits[0]); i++) {
   if (ms < limits[i]) {
    within[i] += fFrameTimes[ms];
    break;
   }
  }
  total += fFrameTimes[ms];
 }
 for (uint32_t ms = 0; ms <= FRAME_TIMES && total != 0; ms++) {
  sum += fFrameTimes[ms];
  if (half == 0 && 2 * sum >= total) {
   half = ms + 1;
  }
  if (most == 0 && 100 * sum >= 95 * total) {
   most = ms + 1;
  }
 }
 if (total != 0) {
  IOLog("MiniIOMobileFramebuffer: from one frame to the next: %u times under 10 ms, %u under 18, %u under 26, %u under 35, "
      "%u longer (the longest %u ms); half under %u ms, 95 in 100 under %u ms; %u pauses\n", within[0], within[1],
      within[2], within[3], within[4], fFrameLongest, half, most, fFramePauses);
 }
 bzero(fFrameTimes, sizeof(fFrameTimes));
 fFramePauses = fFrameLongest = 0;
}
void
IOMobileFramebuffer::present(const uint8_t * swap)
{
 AbsoluteTime deadline;
 uint64_t ticket = 0;
 uint64_t now = mach_absolute_time(), period, pause;
 nanoseconds_to_absolutetime(NSEC_PER_SEC / refreshHz() * 5 / 4, &period);
 nanoseconds_to_absolutetime(FRAME_PAUSE * NSEC_PER_MSEC, &pause);
 clock_interval_to_deadline(SWAP_HELD_MS, kMillisecondScale, &deadline);
 if (gTouchLat) {
  redwood_tl("tl: s %u at %llu\n", swapWord(swap, SWAP_ID), micros(now));
 }
 IOLockLock(fSwapLock);
 fStatSwapsLate += fSwapTime != 0 && now - fSwapTime > period && now - fSwapTime < pause;
 fSwapTime = now;
 fStatHeld += fSwapsWaiting >= swapQueue();
 while (fSwapsWaiting >= swapQueue()) {
  if (IOLockSleepDeadline(fSwapLock, &fSwapsWaiting, deadline, THREAD_UNINT) == THREAD_TIMED_OUT &&
      fSwapsWaiting >= swapQueue()) {
   fStatLost++;
   IOLockUnlock(fSwapLock);
   return;
  }
 }
 unsigned slot = (fSwapFirst + fSwapsWaiting) % SWAP_QUEUE;
 if (gWaffle && gWaffleDisplayPresent == 1) {
  if (fSwapIssued == UINT64_MAX) {
   IOLockUnlock(fSwapLock);
   redwood_tl("waffle-display-retire: ticket_overflow=1 refused=1\n");
   return;
  }
  ticket = ++fSwapIssued;
 }
 fSwapTickets[slot] = ticket;
 memcpy(fSwap[slot], swap, SWAP_SIZE);
 for (unsigned layer = 0; layer < SWAP_LAYERS; layer++) {
  uint32_t sid = swapWord(swap, SWAP_SURFACE(layer));
  fSwapSurfaces[slot][layer] = sid == 0 ? NULL :
      gWaffle && gWaffleDisplayUse ? MiniIOSurfaceCopyForDisplay(sid) : MiniIOSurfaceCopy(sid);
 }
 fSwapsWaiting++;
 IOLockWakeup(fSwapLock, fSwap, true);
 IOLockUnlock(fSwapLock);
 if (ticket != 0) waitForPresentation(ticket);
}
/* Source-read retirement, not an interpretation of native SwapWait flags.
 * Timeout is reported, never called retired.
 */
bool
IOMobileFramebuffer::waitForPresentation(uint64_t ticket)
{
 AbsoluteTime deadline;
 clock_interval_to_deadline(SWAP_HELD_MS, kMillisecondScale, &deadline);
 IOLockLock(fSwapLock);
 while (fSwapCompleted < ticket) {
  if (IOLockSleepDeadline(fSwapLock, &fSwapCompleted, deadline, THREAD_UNINT) == THREAD_TIMED_OUT &&
      fSwapCompleted < ticket) {
   uint64_t completed = fSwapCompleted;
   IOLockUnlock(fSwapLock);
   redwood_tl("waffle-display-retire: ticket=%llu completed=%llu timeout=1\n",
       (unsigned long long)ticket, (unsigned long long)completed);
   return false;
  }
 }
 IOLockUnlock(fSwapLock);
 return true;
}
void
IOMobileFramebuffer::retireSource(uint64_t ticket)
{
 if (ticket == 0) return;
 IOLockLock(fSwapLock);
 if (fSwapCompleted < ticket) {
  fSwapCompleted = ticket;
  IOLockWakeup(fSwapLock, &fSwapCompleted, false);
 }
 IOLockUnlock(fSwapLock);
}
void
IOMobileFramebuffer::presenterMain(void * self, wait_result_t result __unused)
{
 ((IOMobileFramebuffer *) self)->presenter();
}
void
IOMobileFramebuffer::presenter(void)
{
 static uint8_t swap[SWAP_SIZE];
 MiniIOSurface * surfaces[SWAP_LAYERS];
 for (;;) {
  IOLockLock(fSwapLock);
  while (fSwapsWaiting == 0) {
   IOLockSleep(fSwapLock, fSwap, THREAD_UNINT);
  }
  memcpy(swap, fSwap[fSwapFirst], SWAP_SIZE);
  memcpy(surfaces, fSwapSurfaces[fSwapFirst], sizeof(surfaces));
  uint64_t ticket = fSwapTickets[fSwapFirst];
  IOLockUnlock(fSwapLock);
  show(swap, surfaces, ticket);
  for (unsigned layer = 0; layer < SWAP_LAYERS; layer++) {
   if (surfaces[layer] != NULL) {
    if (gWaffle && gWaffleDisplayUse) {
     MiniIOSurfaceDropForDisplay(surfaces[layer]);
    } else {
     MiniIOSurfaceDrop(surfaces[layer]);
    }
   }
  }
  MiniIOSurfaceClearKept();
  retireSource(ticket);
 }
}
void
IOMobileFramebuffer::show(const uint8_t * swap, MiniIOSurface ** surfaces, uint64_t ticket)
{
 uint32_t set = swapWord(swap, SWAP_LAYERS_SET);
 uint64_t began = mach_absolute_time(), nanos, ready, shown, drawn;
 uint32_t layers = 0;
 MiniIOSurface * recorded = NULL;
 bool report;
 for (unsigned layer = 0; layer < SWAP_LAYERS; layer++) {
  if (surfaces[layer] != NULL && !MiniIOSurfaceDrawn(surfaces[layer], SWAP_GPU_MS)) {
   IOLog("MiniIOMobileFramebuffer: swap %u: the GPU is not done with surface %u after %u ms; shown as it is\n",
       swapWord(swap, SWAP_ID), swapWord(swap, SWAP_SURFACE(layer)), SWAP_GPU_MS);
  }
 }
 fStatWaiting += mach_absolute_time() - began;
 began = ready = mach_absolute_time();
 if (gOnTheBeat && !(fWafflePresenter && !fWafflePresenter->state.failed)) {
  uint64_t period, aim, next;
  nanoseconds_to_absolutetime(NSEC_PER_SEC / refreshHz(), &period);
  aim = period * 3 / 8;
  next = fReady;
  fReady = began;
  if (fBeat == 0 || began - next > period * 3 / 2) {
   fBeat = began;
  } else {
   for (next = fBeat + period; next < began; next += period) {
   }
   if (next - began > aim) {
    next -= (next - began - aim) / 8;
   } else {
    next += (aim - (next - began)) / 8;
   }
   clock_delay_until(next);
   fBeat = next;
   fStatOnBeat++;
   fStatBeatWait += mach_absolute_time() - began;
   began = mach_absolute_time();
  }
 }
 shown = began;
 IOLockLock(fSwapLock);
 fSwapFirst = (fSwapFirst + 1) % SWAP_QUEUE;
 fSwapsWaiting--;
 IOLockWakeup(fSwapLock, &fSwapsWaiting, true);
 IOLockUnlock(fSwapLock);
 IOLockLock(fLock);
 if (gWaffle && gWaffleDisplayPresent == 1 && !fWafflePresentTried) {
  fWafflePresentTried = true;
  if (fPanelWidth == 1440 && fPanelHeight == 3168 && fRowBytes == 5760) fWafflePresenter = waffleDisplayPresentCreate(fBase);
  if (fWafflePresenter) fBase = (uint8_t *)fWafflePresenter->working->getBytesNoCopy();
  else redwood_tl("waffle-display-present: armed=0 initialization_refused=1\n");
 }
 if (fLastFrame != 0) {
  absolutetime_to_nanoseconds(began - fLastFrame, &nanos);
  nanos /= NSEC_PER_MSEC;
  if (nanos >= FRAME_PAUSE) {
   fFramePauses++;
  } else {
   fFrameTimes[nanos < FRAME_TIMES ? nanos : FRAME_TIMES]++;
   fFrameLongest = nanos > fFrameLongest ? (uint32_t) nanos : fFrameLongest;
  }
 }
 fLastFrame = began;
 report = fSwapsShown < 8;
 if (report) {
  IOLog("MiniIOMobileFramebuffer: swap %u (#%u): surfaces %u %u %u %u, layers set 0x%x cleared 0x%x\n",
      swapWord(swap, SWAP_ID), fSwapsShown, swapWord(swap, SWAP_SURFACE(0)), swapWord(swap, SWAP_SURFACE(1)),
      swapWord(swap, SWAP_SURFACE(2)), swapWord(swap, SWAP_SURFACE(3)), set, swapWord(swap, SWAP_LAYERS_CLEARED));
 }
 uint64_t composeBegan = mach_absolute_time(), composeNanos = 0;
 for (unsigned layer = 0; layer < SWAP_LAYERS; layer++) {
  uint32_t sid = swapWord(swap, SWAP_SURFACE(layer));
  int32_t src[4], dst[4];
  MiniIOSurface * s;
  layers |= sid != 0 ? 1u << layer : 0;
  for (unsigned i = 0; layer == 0 && sid != 0 && i < 8; i++) {
   if (fStatSurfaces[i] == 0 || fStatSurfaces[i] == sid) {
    fStatSurfaces[i] = sid;
    break;
   }
  }
  if (sid == 0) {
   if (layer == 0 && (set & 1) && fGraphics) {
    for (uint32_t y = 0; y < fPanelHeight; y++) {
     bzero(fBase + (size_t) y * fRowBytes, (size_t) fPanelWidth * 4);
    }
   }
   continue;
  }
  memcpy(src, swap + SWAP_SOURCE(layer), sizeof(src));
  memcpy(dst, swap + SWAP_DEST(layer), sizeof(dst));
  s = surfaces[layer];
  if (report) {
   IOLog("MiniIOMobileFramebuffer: swap %u layer %u: surface %u%s (%ux%u '%c%c%c%c') "
       "from %d,%d %dx%d to %d,%d %dx%d, layers set 0x%x\n", swapWord(swap, SWAP_ID), layer, sid,
       s ? "" : " MISSING", s ? s->info.width : 0, s ? s->info.height : 0,
       s ? (int) (s->info.pixelFormat >> 24 & 0xff) : '?', s ? (int) (s->info.pixelFormat >> 16 & 0xff) : '?',
       s ? (int) (s->info.pixelFormat >> 8 & 0xff) : '?', s ? (int) (s->info.pixelFormat & 0xff) : '?',
       src[0], src[1], src[2], src[3], dst[0], dst[1], dst[2], dst[3], set);
  }
  if (s == NULL) {
   continue;
  }
  if (gWaffle && report) {
   IOLog("MiniIOMobileFramebuffer: display read surface %u usage_enabled=%u holds=%u system_use=%llu\n",
       sid, gWaffleDisplayUse, s->displayUses, (unsigned long long) s->shared()->useCount);
  }
  if (s->info.bytesPerElement == 4 && s->info.planeCount == 0) {
   if (!fGraphics) {
    fGraphics = true;
    PE_initialize_console(NULL, kPEGraphicsMode);
   }
   struct waffle_display_source_stamp before = {}, after = {};
   if (fWafflePresenter && s->info.allocSize >= s->info.offset) {
    before = waffle_display_source_observe(&s->shared()->seed, s->pixels(), s->info.allocSize - s->info.offset,
        s->info.width, s->info.height, s->info.bytesPerRow);
   }
   drawLayer(s, src, dst);
   if (before.valid) {
    after = waffle_display_source_observe(&s->shared()->seed, s->pixels(), s->info.allocSize - s->info.offset,
        s->info.width, s->info.height, s->info.bytesPerRow);
    if (after.valid) {
     fWafflePresenter->sourceReads++;
     if (before.seed != after.seed || before.hash != after.hash) {
      fWafflePresenter->sourceChanges++;
      fWafflePresenter->pixelChanges += before.hash != after.hash;
      if (fWafflePresenter->sourceChanges <= 32) redwood_tl("waffle-display-source: sid=%u frame=%u seed_before=%u seed_after=%u samples_changed=%u samples=16\n",
          sid, fSwapsShown, before.seed, after.seed, before.hash != after.hash);
     }
    }
   }
   if (layer == 0) {
    recorded = s;
   }
  }
 }
 absolutetime_to_nanoseconds(mach_absolute_time() - composeBegan, &composeNanos);
 /* All drawLayer jobs and source observations have finished. Only the private
  * working frame is used for scanout copy/commit below. A recording session
  * still reads its source after commit, so it retains conservative retirement.
  */
 if (fWafflePresenter && !fWafflePresenter->state.failed && gRecSeconds == 0) retireSource(ticket);
 if (fWafflePresenter && !fWafflePresenter->state.failed) {
  struct waffle_display_present_result r = {};
  uint64_t start = mach_absolute_time(), elapsed = 0;
  fWafflePresenter->copyNanos = 0;
  /* The previous copy is immutable in A/B. Compose above overlapped its
   * scanout wait; retire it here before copying the next inactive buffer. */
  struct waffle_display_present_result previous = {};
  bool ok = waffle_display_present_complete(&fWafflePresenter->io, &fWafflePresenter->state, &previous);
  if (ok) ok = gRecSeconds == 0 ?
      waffle_display_present_begin(&fWafflePresenter->io, &fWafflePresenter->state, &r) :
      waffle_display_present_frame(&fWafflePresenter->io, &fWafflePresenter->state, &r);
  if (!ok && previous.rollback_attempted) r = previous;
  absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
  unsigned completed = fWafflePresenter->state.completed;
  if (!ok || completed <= 8 || !(completed % 120)) {
   redwood_tl("waffle-display-present: committed=%u completed=%u target=%x copied=%u rollback=%u rollback_ok=%u us=%llu accepted=%u pending=%u\n",
       r.committed || previous.committed, completed, r.target, r.copied, r.rollback_attempted, r.rollback_ok,
       (unsigned long long)(elapsed / 1000), ok, fWafflePresenter->state.pending);
   redwood_tl("waffle-display-source: compose_us=%llu copy_us=%llu submit_wait_us=%llu reads=%u changes=%u pixel_changes=%u\n",
       (unsigned long long)(composeNanos / 1000), (unsigned long long)(fWafflePresenter->copyNanos / 1000),
       (unsigned long long)((elapsed - fWafflePresenter->copyNanos) / 1000), fWafflePresenter->sourceReads,
       fWafflePresenter->sourceChanges, fWafflePresenter->pixelChanges);
  }
 }
 drawn = mach_absolute_time();
 if (recorded != NULL) {
  record(recorded);
 }
 fSwapsShown++;
 if (gTouchLat) {
  redwood_tl("tl: v %u ready %llu shown %llu done %llu\n", swapWord(swap, SWAP_ID), micros(ready), micros(shown),
      micros(drawn));
 }
 if (layers != fLayersShown) {
  IOLog("MiniIOMobileFramebuffer: swap #%u: surfaces in layers 0x%x now (0x%x before): %u %u %u %u\n", fSwapsShown, layers,
      fLayersShown, swapWord(swap, SWAP_SURFACE(0)), swapWord(swap, SWAP_SURFACE(1)), swapWord(swap, SWAP_SURFACE(2)),
      swapWord(swap, SWAP_SURFACE(3)));
  fLayersShown = layers;
 }
 fStatFrames++;
 fStatDrawing += mach_absolute_time() - began;
 if (fStatSince == 0) {
  fStatSince = began;
 }
 absolutetime_to_nanoseconds(mach_absolute_time() - fStatSince, &nanos);
 if (nanos >= 5 * NSEC_PER_SEC) {
  uint64_t drawing, waiting, beat;
  unsigned different;
  absolutetime_to_nanoseconds(fStatDrawing, &drawing);
  absolutetime_to_nanoseconds(fStatWaiting, &waiting);
  absolutetime_to_nanoseconds(fStatBeatWait, &beat);
  IOLog("MiniIOMobileFramebuffer: %u frames in %llu ms (%llu a second), %llu us each in the driver, after %llu us "
      "waiting for the GPU and, %u of them, %llu us for the next refresh; %u swaps waited for the frame before, "
      "%u gave up; %u swaps came a refresh late themselves\n", fStatFrames, nanos / NSEC_PER_MSEC,
      fStatFrames * NSEC_PER_SEC / nanos, drawing / fStatFrames / NSEC_PER_USEC,
      waiting / fStatFrames / NSEC_PER_USEC, fStatOnBeat, fStatOnBeat ? beat / fStatOnBeat / NSEC_PER_USEC : 0,
      fStatHeld, fStatLost, fStatSwapsLate);
  {
   char line[96];
   snprintf(line, sizeof(line), "fps: %llu (%u frames in %llu ms), %llu us each in the driver\n",
       fStatFrames * NSEC_PER_SEC / nanos, fStatFrames, nanos / NSEC_PER_MSEC, drawing / fStatFrames / NSEC_PER_USEC);
   for (char *c = line; *c; c++) {
    loader_log_putc(*c);
   }
  }
  fStatSwapsLate = 0;
  for (different = 0; different < 8 && fStatSurfaces[different] != 0; different++) {
  }
  if (different == 8 && fStatFrames > 8) {
   uint32_t made, freed, again;
   uint64_t making, freeing;
   MiniIOSurfaceCost(&made, &making, &freed, &freeing, &again);
   IOLog("MiniIOMobileFramebuffer: the frames came in surfaces %u, %u, %u, %u, %u and on, none twice; in that time "
       "%u surfaces of all kinds were made, in %llu us each (%u of them of memory kept from one before), and %u "
       "freed, in %llu us each\n", fStatSurfaces[0], fStatSurfaces[1], fStatSurfaces[2], fStatSurfaces[3],
       fStatSurfaces[4], made, making, again, freed, freeing);
  }
  bzero(fStatSurfaces, sizeof(fStatSurfaces));
  fStatHeld = fStatLost = fStatOnBeat = 0;
  fStatWaiting = fStatBeatWait = 0;
  reportFrameTimes();
  if (fDiff) {
   IOLog("MiniIOMobileFramebuffer: %llu pixels of the panel changed a frame, all within %u,%u to %u,%u\n",
       fDiffPixels / fStatFrames, fDiffLeft, fDiffTop, fDiffRight, fDiffBottom);
   fDiffPixels = 0;
   fDiffLeft = fDiffTop = ~0u;
   fDiffRight = fDiffBottom = 0;
  }
  fStatFrames = 0;
  fStatDrawing = 0;
  fStatSince = 0;
 }
 IOLockUnlock(fLock);
}
class IOMobileFramebufferUserClient : public IOUserClient
{
 OSDeclareDefaultStructors(IOMobileFramebufferUserClient);
 task_t fTask;
 IOMobileFramebuffer * fOwner;
 IOLock * fLock;
 mach_port_t fPorts[kFBNotifyTypes];
 mach_vm_address_t fCallbacks[kFBNotifyTypes];
 io_user_reference_t fRefcons[kFBNotifyTypes];
 thread_call_t fVSyncCall;
 uint64_t fVSyncCount;
 uint64_t fVSyncTime;
 bool fVSyncRunning;
 bool fHardwareVSyncDisabled;
 struct waffle_vsync_phase fHardwarePhase;
 uint32_t fHardwareEvents;
 bool fClosed;
 static void vsyncFired(thread_call_param_t self, thread_call_param_t unused);
 void vsync(void);
 void armVSync(void);
public:
 virtual bool initWithTask(task_t owningTask, void * securityID, UInt32 type, OSDictionary * properties) APPLE_KEXT_OVERRIDE;
 virtual bool start(IOService * provider) APPLE_KEXT_OVERRIDE;
 virtual IOReturn clientClose(void) APPLE_KEXT_OVERRIDE;
 virtual void free(void) APPLE_KEXT_OVERRIDE;
 virtual IOReturn registerNotificationPort(mach_port_t port, UInt32 type, io_user_reference_t refCon) APPLE_KEXT_OVERRIDE;
 virtual IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments * args,
     IOExternalMethodDispatch * dispatch, OSObject * target, void * reference) APPLE_KEXT_OVERRIDE;
};
OSDefineMetaClassAndStructors(IOMobileFramebufferUserClient, IOUserClient);
bool
IOMobileFramebufferUserClient::initWithTask(task_t owningTask, void * securityID, UInt32 type, OSDictionary * properties)
{
 if (!IOUserClient::initWithTask(owningTask, securityID, type, properties)) {
  return false;
 }
 fTask = owningTask;
 return true;
}
bool
IOMobileFramebufferUserClient::start(IOService * provider)
{
 fOwner = OSDynamicCast(IOMobileFramebuffer, provider);
 if (fOwner == NULL || !IOUserClient::start(provider)) {
  return false;
 }
 fLock = IOLockAlloc();
 fVSyncCall = thread_call_allocate(&IOMobileFramebufferUserClient::vsyncFired, this);
 bzero(&fHardwarePhase, sizeof(fHardwarePhase));
 fHardwareVSyncDisabled = false;
 fHardwareEvents = 0;
 return fLock != NULL && fVSyncCall != NULL;
}
IOReturn
IOMobileFramebufferUserClient::clientClose(void)
{
 if (fLock != NULL) {
  IOLockLock(fLock);
  fClosed = true;
  IOLockUnlock(fLock);
 }
 if (fVSyncCall != NULL) {
  thread_call_cancel_wait(fVSyncCall);
 }
 if (!isInactive()) {
  terminate();
 }
 return kIOReturnSuccess;
}
void
IOMobileFramebufferUserClient::free(void)
{
 if (fVSyncCall != NULL) {
  thread_call_cancel_wait(fVSyncCall);
  thread_call_free(fVSyncCall);
  fVSyncCall = NULL;
 }
 for (unsigned i = 0; i < kFBNotifyTypes; i++) {
  if (fPorts[i] != NULL) {
   releaseNotificationPort(fPorts[i]);
   fPorts[i] = NULL;
  }
 }
 if (fLock != NULL) {
  IOLockFree(fLock);
  fLock = NULL;
 }
 IOUserClient::free();
}
IOReturn
IOMobileFramebufferUserClient::registerNotificationPort(mach_port_t port, UInt32 type, io_user_reference_t refCon)
{
 mach_port_t old;
 IOLog("MiniIOMobileFramebuffer: notification port for type %u\n", (unsigned) type);
 if (type >= kFBNotifyTypes) {
  return kIOReturnBadArgument;
 }
 IOLockLock(fLock);
 old = fPorts[type];
 fPorts[type] = port;
 IOLockUnlock(fLock);
 if (gWaffleHardwareVSync == 1) {
  redwood_tl("waffle-vsync: register_port client=%p type=%u present=%u\n", this, type, port != NULL);
 }

 if (old != NULL) {
  releaseNotificationPort(old);
 }
 return kIOReturnSuccess;
}
void
IOMobileFramebufferUserClient::vsyncFired(thread_call_param_t self, thread_call_param_t unused)
{
 ((IOMobileFramebufferUserClient *) self)->vsync();
}
void
IOMobileFramebufferUserClient::armVSync(void)
{
 uint64_t period, now = mach_absolute_time();
 if (gWaffleHardwareVSync == 1 && waffleVSyncReady() && !fHardwareVSyncDisabled) {
  nanoseconds_to_absolutetime(500 * NSEC_PER_USEC, &period);
  fVSyncTime = now + period;
  thread_call_enter_delayed(fVSyncCall, fVSyncTime);
  return;
 }

 nanoseconds_to_absolutetime(NSEC_PER_SEC / refreshHz(), &period);
 fVSyncTime += period;
 if (fVSyncTime <= now || fVSyncTime > now + 2 * period) {
  fVSyncTime = now + period;
 }
 thread_call_enter_delayed(fVSyncCall, fVSyncTime);
}
void
IOMobileFramebufferUserClient::vsync(void)
{
 OSAsyncReference64 ref;
 io_user_reference_t args[6];
 uint64_t now;
 bool send = false;
 IOLockLock(fLock);
 now = fVSyncTime;
 if (fClosed || fCallbacks[kFBNotifyVSync] == 0 || fPorts[kFBNotifyVSync] == NULL) {
  fVSyncRunning = false;
  if (gWaffleHardwareVSync == 1 && !fClosed) {
   redwood_tl("waffle-vsync: callback_unarmed client=%p callback=%u port0=%u port5=%u\n",
       this, fCallbacks[kFBNotifyVSync] != 0, fPorts[0] != NULL, fPorts[kFBNotifyVSync] != NULL);
  }
 } else {
  bool emit = true;
  if (gWaffleHardwareVSync == 1 && waffleVSyncReady() && !fHardwareVSyncDisabled) {
   struct waffle_vsync_clock clock = {(void *)gWaffleVSyncMap, waffleDisplayRead};
   uint64_t stamp = 0;
   bool stamp_valid = waffle_vsync_timestamp(&clock, &stamp);
   uint64_t observed = mach_absolute_time();
   enum waffle_vsync_result result = stamp_valid ?
       waffle_vsync_observe(&fHardwarePhase, stamp, observed, gWaffleVSyncPeriod, gWaffleVSyncDivider) : WAFFLE_VSYNC_FAULT;
   if (result == WAFFLE_VSYNC_WAIT) emit = false;
   else if (result == WAFFLE_VSYNC_FAULT) {
    redwood_tl("waffle-vsync: fault_input valid=%u stamp=%llu now=%llu seen=%llu period=%llu initialized=%u\n",
        stamp_valid, (unsigned long long)stamp, (unsigned long long)observed,
        (unsigned long long)fHardwarePhase.seen, (unsigned long long)gWaffleVSyncPeriod,
        fHardwarePhase.initialized);
    fHardwareVSyncDisabled = true;
    now = observed;
    redwood_tl("waffle-vsync: hardware_fallback=1 reason=timestamp_stall_or_reset emitted=%u\n", fHardwareEvents);
   } else {
    now = stamp;
    if (fHardwareEvents++ < 8) {
     uint64_t lag_ns = 0;
     absolutetime_to_nanoseconds(observed - stamp, &lag_ns);
     redwood_tl("waffle-vsync: hardware_callback=%u timestamp=%llu observed=%llu lag_ns=%llu divider=%u\n",
         fHardwareEvents, (unsigned long long)stamp, (unsigned long long)observed, (unsigned long long)lag_ns, gWaffleVSyncDivider);
    }
   }
  }
  if (emit) {
  fVSyncCount++;
  setAsyncReference64(ref, fPorts[kFBNotifyVSync], fCallbacks[kFBNotifyVSync], fRefcons[kFBNotifyVSync], fTask);
  args[0] = (uint32_t) now;
  args[1] = now >> 32;
  args[2] = (uint32_t) now;
  args[3] = now >> 32;
  args[4] = (uint32_t) fVSyncCount;
  args[5] = fVSyncCount >> 32;
  send = true;
  }
  armVSync();
 }
 IOLockUnlock(fLock);
 if (send) {
  sendAsyncResult64WithOptions(ref, kIOReturnSuccess, args, 6, kIOUserNotifyOptionCanDrop);
 }
}
IOReturn
IOMobileFramebufferUserClient::externalMethod(uint32_t selector, IOExternalMethodArguments * args,
    IOExternalMethodDispatch * dispatch, OSObject * target, void * reference)
{
 const uint64_t * in = args->scalarInput;
 uint64_t * out = args->scalarOutput;
 MiniIOSurface * s;
 if (selector < 128 && gFBCalls[selector] < gFBTrace) {
  char procname[32] = "?";
  gFBCalls[selector]++;
  proc_selfname(procname, sizeof(procname));
  IOLog("MiniIOMobileFramebuffer: %s[%d] selector %u (scalars %u in [0x%llx 0x%llx 0x%llx 0x%llx], %u out; "
      "structure %u in, %u out)\n", procname, proc_selfpid(), selector, args->scalarInputCount,
      args->scalarInputCount > 0 ? in[0] : 0, args->scalarInputCount > 1 ? in[1] : 0,
      args->scalarInputCount > 2 ? in[2] : 0, args->scalarInputCount > 3 ? in[3] : 0, args->scalarOutputCount,
      args->structureInputSize, args->structureOutputSize);
 }
 switch (selector) {
 case kFBMethodGetDisplaySize:
  if (args->scalarOutputCount < 2) {
   return kIOReturnBadArgument;
  }
  out[0] = fOwner->fWidth;
  out[1] = fOwner->fHeight;
  args->scalarOutputCount = 2;
  return kIOReturnSuccess;
 case kFBMethodGetID:
  if (args->scalarOutputCount < 1) {
   return kIOReturnBadArgument;
  }
  out[0] = 1;
  args->scalarOutputCount = 1;
  return kIOReturnSuccess;
 case kFBMethodGetDotPitch:
  if (args->scalarOutputCount < 1) {
   return kIOReturnBadArgument;
  }
  out[0] = fOwner->fWidth == kFBMacanWidth ? kFBMacanDotsPerInch : kFBDotsPerInch * fOwner->fWidth / kFBDefaultWidth;
  args->scalarOutputCount = 1;
  return kIOReturnSuccess;
 case kFBMethodGetLayerDefaultSurface:
  if (args->scalarOutputCount < 1) {
   return kIOReturnBadArgument;
  }
  s = fOwner->defaultSurface();
  if (s == NULL) {
   return kIOReturnNoMemory;
  }
  out[0] = MiniIOSurfaceMakeSendRight(fTask, s);
  args->scalarOutputCount = 1;
  return out[0] != 0 ? kIOReturnSuccess : kIOReturnNoMemory;
 case kFBMethodSwapBegin:
  if (args->scalarOutputCount < 1) {
   return kIOReturnBadArgument;
  }
  out[0] = OSIncrementAtomic(&fOwner->fSwapID) + 1;
  args->scalarOutputCount = 1;
  return kIOReturnSuccess;
 case kFBMethodSwapEnd:
  if (args->structureInput == NULL || args->structureInputSize < SWAP_SIZE) {
   IOLog("MiniIOMobileFramebuffer: swap request of %u bytes, expected %u\n", args->structureInputSize, SWAP_SIZE);
   return kIOReturnBadArgument;
  }
  fOwner->present((const uint8_t *) args->structureInput);
  return kIOReturnSuccess;
 case kFBMethodSwapWait:
  if (gTouchLat) {
   redwood_tl("tl: w %llu %#llx %#llx at %llu\n", args->scalarInputCount > 0 ? in[0] : 0,
       args->scalarInputCount > 1 ? in[1] : 0, args->scalarInputCount > 2 ? in[2] : 0, micros(mach_absolute_time()));
  }
  return kIOReturnSuccess;
 case kFBMethodSwapSignal:
 case kFBMethodSwapCancel:
 case kFBMethodSwapCancelAll:
 case kFBMethodRequestPowerChange:
 case kFBMethodChangeFrameInfo:
  return kIOReturnSuccess;
 case kFBMethodNotifications:
  if (args->scalarInputCount < 3 || in[2] >= kFBNotifyTypes) {
   return kIOReturnBadArgument;
  }
  if (gWaffleHardwareVSync == 1) {
   static unsigned subscriptions;
   if (subscriptions++ < 32) {
    redwood_tl("waffle-vsync: subscribe client=%p type=%llu enabled=%u scalar_count=%u\n",
        this, (unsigned long long)in[2], in[0] != 0, args->scalarInputCount);
   }
  }
  IOLockLock(fLock);
  /* A disabled notification stream has no continuous phase history. Keep a
   * genuine hardware fault latched, but do not treat an unsubscribe gap as
   * a panel timestamp stall when the next subscription starts. */
  if (gWaffleHardwareVSync == 1 && in[2] == kFBNotifyVSync && in[0] == 0) {
   bzero(&fHardwarePhase, sizeof(fHardwarePhase));
  }
  fCallbacks[in[2]] = in[0];
  fRefcons[in[2]] = in[1];
  if (in[2] == kFBNotifyVSync && in[0] != 0 && !fVSyncRunning && !fClosed) {
   fVSyncRunning = true;
   armVSync();
  }
  IOLockUnlock(fLock);
  return kIOReturnSuccess;
 case kFBMethodSupportedFrameInfo:
  if (args->scalarOutputCount >= 1) {
   out[0] = 0;
   args->scalarOutputCount = 1;
  }
  if (args->structureOutput != NULL) {
   bzero(args->structureOutput, args->structureOutputSize);
  }
  return kIOReturnSuccess;
 case kFBMethodGetBlock:
  if (args->structureOutput == NULL) {
   return kIOReturnBadArgument;
  }
  bzero(args->structureOutput, args->structureOutputSize);
  if (args->scalarInputCount >= 1 && in[0] == 0x40 && args->structureOutputSize >= 12) {
   uint32_t ids[2] = { kFBColorID, kFBTimingID };
   memcpy((uint8_t *) args->structureOutput + 4, ids, sizeof(ids));
  }
  return kIOReturnSuccess;
 case kFBMethodGetCurrentAbsoluteTime:
  if (args->scalarOutputCount < 1) {
   return kIOReturnBadArgument;
  }
  out[0] = mach_absolute_time();
  args->scalarOutputCount = 1;
  return kIOReturnSuccess;
 default:
  break;
 }
 if (selector < 128 && !(gFBLogged[selector / 64] & (1ULL << (selector % 64)))) {
  gFBLogged[selector / 64] |= 1ULL << (selector % 64);
  IOLog("MiniIOMobileFramebuffer: selector %u not implemented (scalars %u in [0x%llx 0x%llx 0x%llx], %u out; "
      "structure %u in, %u out)\n", selector, args->scalarInputCount, args->scalarInputCount > 0 ? in[0] : 0,
      args->scalarInputCount > 1 ? in[1] : 0, args->scalarInputCount > 2 ? in[2] : 0, args->scalarOutputCount,
      args->structureInputSize, args->structureOutputSize);
 }
 if (args->scalarOutputCount != 0) {
  bzero(out, args->scalarOutputCount * sizeof(out[0]));
 }
 if (args->structureOutput != NULL && args->structureOutputSize != 0) {
  bzero(args->structureOutput, args->structureOutputSize);
 }
 return kIOReturnSuccess;
}
static void
publishDisplayNode(void)
{
 IORegistryEntry * armio = IORegistryEntry::fromPath("/arm-io", gIODTPlane);
 IORegistryEntry * node;
 OSDictionary * props;
 OSData * data;
 if (armio == NULL) {
  IOLog("MiniIOMobileFramebuffer: no /arm-io in the device tree\n");
  return;
 }
 node = OSTypeAlloc(IORegistryEntry);
 props = OSDictionary::withCapacity(4);
 if (node != NULL && props != NULL) {
  data = OSData::withBytes("display-subsystem", sizeof("display-subsystem"));
  props->setObject("device_type", data);
  OSSafeReleaseNULL(data);
  data = OSData::withBytes("redwood,framebuffer", sizeof("redwood,framebuffer"));
  props->setObject("compatible", data);
  OSSafeReleaseNULL(data);
  data = OSData::withBytes("disp0", sizeof("disp0"));
  props->setObject("name", data);
  OSSafeReleaseNULL(data);
  if (node->init(props)) {
   node->setName("disp0");
   node->attachToParent(armio, gIODTPlane);
  }
 }
 OSSafeReleaseNULL(props);
 OSSafeReleaseNULL(node);
 armio->release();
}
class IOAcceleratorES : public IOService
{
 OSDeclareDefaultStructors(IOAcceleratorES);
};
OSDefineMetaClassAndStructors(IOAcceleratorES, IOService);
static void
publishAccelerator(IOService * provider)
{
 IOAcceleratorES * accelerator = OSTypeAlloc(IOAcceleratorES);
 if (accelerator != NULL && accelerator->init() && accelerator->attach(provider)) {
  accelerator->setName("sgx");
  accelerator->registerService();
 }
 OSSafeReleaseNULL(accelerator);
}
extern "C" void
MiniIOMobileFramebufferShow(const uint8_t * pixels, uint32_t width, uint32_t height, uint32_t rowBytes)
{
 uint32_t columns = width < vinfo.v_width ? width : (uint32_t) vinfo.v_width;
 uint32_t rows = height < vinfo.v_height ? height : (uint32_t) vinfo.v_height;
 if (vinfo.v_baseaddr == 0 || vinfo.v_depth != 32) {
  return;
 }
 for (uint32_t y = 0; y < rows; y++) {
  memcpy((void *) (vinfo.v_baseaddr + (size_t) y * vinfo.v_rowbytes), pixels + (size_t) y * rowBytes,
      (size_t) columns * 4);
 }
}
void
MiniIOMobileFramebufferStart(IOService * provider)
{
 IOMobileFramebuffer * fb = OSTypeAlloc(IOMobileFramebuffer);
 if (fb == NULL || !fb->init() || !fb->attach(provider)) {
  OSSafeReleaseNULL(fb);
  return;
 }
 if (fb->start(provider)) {
  publishDisplayNode();
  publishAccelerator(provider);
 } else {
  fb->detach(provider);
 }
 fb->release();
}
