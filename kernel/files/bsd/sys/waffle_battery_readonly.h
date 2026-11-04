/* Read-only PMIC GLINK ABI from pinned OnePlus oplus_hal_adsp.[ch]. */
#ifndef WAFFLE_BATTERY_READONLY_H
#define WAFFLE_BATTERY_READONLY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define WAFFLE_BATTERY_OWNER 32778u
#define WAFFLE_BATTERY_GET 0x30u
#define WAFFLE_BATTERY_USB_GET 0x32u
#define WAFFLE_BATTERY_MESSAGE_BYTES 24u
static inline uint32_t waffle_battery_u32(const uint8_t *p)
{
 return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static inline void waffle_battery_put(uint8_t *p, uint32_t v)
{
 for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (i * 8));
}
static inline bool waffle_battery_property_allowed(uint32_t opcode, uint32_t property)
{
 /* Initial diagnostic: status, presence, SOC, voltage, current, temperature,
  * and USB presence only. No setters, notifications or charger controls.
  */
 return opcode == WAFFLE_BATTERY_GET ?
     (property == 0 || property == 2 || property == 4 || property == 7 || property == 9 || property == 12) :
     opcode == WAFFLE_BATTERY_USB_GET && property == 0;
}
static inline bool waffle_battery_request(uint8_t *out, size_t size, uint32_t opcode, uint32_t property)
{
 if (!out || size != WAFFLE_BATTERY_MESSAGE_BYTES || !waffle_battery_property_allowed(opcode, property)) return false;
 const uint32_t words[6] = {WAFFLE_BATTERY_OWNER, 1, opcode, 0, property, 0};
 for (unsigned i = 0; i < 6; i++) waffle_battery_put(out + 4 * i, words[i]);
 return true;
}
static inline bool waffle_battery_response(const uint8_t *in, size_t size, uint32_t opcode,
    uint32_t property, uint32_t *value)
{
 if (!in || !value || size != WAFFLE_BATTERY_MESSAGE_BYTES ||
     !waffle_battery_property_allowed(opcode, property) ||
     waffle_battery_u32(in) != WAFFLE_BATTERY_OWNER || waffle_battery_u32(in + 4) != 1 ||
     waffle_battery_u32(in + 8) != opcode || waffle_battery_u32(in + 12) != property ||
     waffle_battery_u32(in + 20) != 0) return false;
 *value = waffle_battery_u32(in + 16);
 return true;
}
static inline bool waffle_battery_value_valid(uint32_t opcode, uint32_t property, uint32_t value)
{
 if (!waffle_battery_property_allowed(opcode, property)) return false;
 if (opcode == WAFFLE_BATTERY_USB_GET) return value <= 2;
 switch (property) {
 case 0: return value >= 1 && value <= 4;
 case 2: return value <= 1;
 case 4: return value <= 10000; /* hundredths of a percent */
 case 7: return value >= 2500000 && value <= 10000000; /* uV, allow dual-cell reports */
 case 9: return (int32_t)value >= -20000000 && (int32_t)value <= 20000000; /* signed uA */
 case 12: return (int32_t)value >= -4000 && (int32_t)value <= 10000; /* hundredths C */
 default: return false;
 }
}
#endif
