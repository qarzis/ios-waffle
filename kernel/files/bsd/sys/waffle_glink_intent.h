#ifndef WAFFLE_GLINK_INTENT_H
#define WAFFLE_GLINK_INTENT_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

struct waffle_glink_remote_intent {
 uint32_t id, size;
 bool there, in_use;
};

static inline int
waffle_glink_intent_admit(struct waffle_glink_remote_intent *table, size_t count,
    uint32_t id, uint32_t size, uint32_t *evicted_size)
{
 if (evicted_size) *evicted_size = 0;
 if (!table || !count || count > 64 || !size) return -1;
 for (size_t i = 0; i < count; i++) {
  if (table[i].there && table[i].id == id)
   return table[i].size == size ? (int)i : -1;
 }
 int empty = -1, replace = -1;
 for (size_t i = 0; i < count; i++) {
  if (!table[i].there) { if (empty < 0) empty = (int)i; continue; }
  if (!table[i].in_use && table[i].size < size &&
      (replace < 0 || table[i].size < table[replace].size)) replace = (int)i;
 }
 int slot = empty >= 0 ? empty : replace;
 if (slot < 0) return -1;
 if (table[slot].there && evicted_size) *evicted_size = table[slot].size;
 table[slot] = (struct waffle_glink_remote_intent){ id, size, true, false };
 return slot;
}
#endif
