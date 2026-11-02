#ifndef WAFFLE_ADSP_POWER_H
#define WAFFLE_ADSP_POWER_H
#include <stdint.h>
#include <stdbool.h>

struct waffle_adsp_resource {
 uint32_t address;
 uint16_t length;
 uint8_t aux[32];
};
struct waffle_adsp_power_command {
 const char *name;
 uint32_t address, value;
 uint8_t vcd, commit;
};
typedef bool (*waffle_adsp_lookup_t)(void *, const char *, struct waffle_adsp_resource *);

static inline bool
waffle_adsp_power_plan(waffle_adsp_lookup_t lookup, void *context,
    struct waffle_adsp_power_command out[11])
{
 static const char *const rails[] = { "lcx.lvl", "lmx.lvl", "xo.lvl" };
 static const uint32_t rail_addresses[] = { 0x30030, 0x30040, 0x300d0 };
 static const uint32_t levels[] = { 384, 384, 128 };
 static const struct {
  const char *name;
  uint32_t address;
  uint8_t vcd, mask;
 } bcms[] = {
  { "MC0", 0x50000, 0, 0 }, { "SH0", 0x50004, 1, 0 },
  { "SH1", 0x50008, 1, 1 }, { "SN0", 0x50010, 3, 0 },
  { "SN3", 0x5001c, 3, 0 }, { "CE0", 0x50034, 6, 0 },
  { "LP0", 0x50050, 10, 0 }, { "ACV", 0x50068, 12, 1 }
 };
 for (unsigned i = 0; i < 3; i++) {
  struct waffle_adsp_resource resource = { 0 };
  if (!lookup(context, rails[i], &resource) || resource.address != rail_addresses[i] ||
      resource.length < 2 || resource.length > sizeof(resource.aux) || (resource.length & 1)) return false;
  unsigned position = 0, previous = 0;
  bool found = false;
  for (unsigned n = 0; n < resource.length / 2; n++) {
   unsigned value = resource.aux[2*n] | (unsigned)resource.aux[2*n+1] << 8;
   if (n && !value) break;
   if (value < previous) return false;
   if (!found && value >= levels[i]) { position = n; found = true; }
   previous = value;
  }
  if (!found) return false;
  out[i] = (struct waffle_adsp_power_command){ rails[i], resource.address, position, 0, 0 };
 }
 for (unsigned i = 0; i < 8; i++) {
  struct waffle_adsp_resource resource = { 0 };
  if (!lookup(context, bcms[i].name, &resource) || resource.address != bcms[i].address ||
      resource.length != 8 || resource.aux[6] != bcms[i].vcd) return false;
  bool commit = i == 7 || bcms[i].vcd != bcms[i+1].vcd;
  uint32_t x = bcms[i].mask ? 0 : 0x3fff;
  uint32_t y = bcms[i].mask ? 1 : 0x3fff;
  out[i+3] = (struct waffle_adsp_power_command){ bcms[i].name, resource.address,
      (uint32_t)commit << 30 | 1u << 29 | x << 14 | y, bcms[i].vcd, commit };
 }
 return true;
}
#endif
