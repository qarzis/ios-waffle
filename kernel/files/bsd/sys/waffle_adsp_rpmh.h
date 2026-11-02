#ifndef WAFFLE_ADSP_RPMH_H
#define WAFFLE_ADSP_RPMH_H
#include <stdint.h>
#include <stdbool.h>

struct waffle_adsp_rpmh_io {
 void *context;
 uint32_t (*read)(void *, unsigned);
 void (*write)(void *, unsigned, uint32_t);
 void (*pause)(void *);
 bool failed;
 uint32_t statuses[8];
};

static inline int
waffle_adsp_rpmh_batch(struct waffle_adsp_rpmh_io *io, const uint32_t *addresses,
    const uint32_t *values, unsigned count, unsigned wait)
{
 if (!io || !io->read || !io->write || !io->pause || io->failed || !count || count > 8 ||
     !addresses || !values || (wait >> count)) return 0;
 if (count == 3) {
  if (wait != 7 || addresses[0] != 0x30030 || values[0] != 7 || addresses[1] != 0x30040 ||
      values[1] != 4 || addresses[2] != 0x300d0 || values[2] != 3) return 0;
 } else if (count == 8) {
  static const uint32_t addr[] = { 0x50000,0x50004,0x50008,0x50010,0x5001c,0x50034,0x50050,0x50068 };
  static const uint32_t data[] = { 0x6fffffff,0x2fffffff,0x60000001,0x2fffffff,0x6fffffff,0x6fffffff,0x6fffffff,0x60000003 };
  if (wait != 0xf5) return 0;
  for (unsigned i = 0; i < 8; i++) if (addresses[i] != addr[i] || values[i] != data[i]) return 0;
 } else return 0;
 unsigned major = io->read(io->context, 0) >> 16 & 255;
 uint32_t config = io->read(io->context, 0xc);
 if ((major != 3 && major != 4) || ((config >> 12) & 63) < 3 || (config >> 27) < count) return 0;
 for (unsigned i = 0; i < 3; i++)
  if (!(io->read(io->context, 0xd28 + i*672) & 1)) return 0;
 if (io->read(io->context, 0xd04) & 1) return 0;
 unsigned offsets[28] = { 0xd00,0xd20,0xd24,0xd2c };
 uint32_t saved[28];
 unsigned total = 4;
 for (unsigned i = 0; i < count; i++) {
  offsets[total++] = 0xd34 + i*24;
  offsets[total++] = 0xd38 + i*24;
  offsets[total++] = 0xd3c + i*24;
 }
 for (unsigned i = 0; i < total; i++) saved[i] = io->read(io->context, offsets[i]);
 saved[2] &= ~(1u << 24);
 io->write(io->context, 0xd24, saved[2]);
 io->write(io->context, 0xd24, saved[2] & ~(1u << 16));
 for (unsigned i = 0; i < count; i++) {
  io->write(io->context, 0xd34 + i*24, 0x10108);
  io->write(io->context, 0xd38 + i*24, addresses[i]);
  io->write(io->context, 0xd3c + i*24, values[i]);
 }
 io->write(io->context, 0xd20, wait);
 io->write(io->context, 0xd2c, (1u << count)-1);
 io->write(io->context, 0xd00, saved[0] | 1);
 io->write(io->context, 0xd24, 1u << 16);
 io->write(io->context, 0xd24, (1u << 16) | (1u << 24));
 bool done = false;
 for (unsigned i = 0; i < 2000; i++) {
  if ((io->read(io->context, 0xd04) & 1) && (io->read(io->context, 0xd28) & 1)) { done = true; break; }
  io->pause(io->context);
 }
 if (!done) { io->failed = true; return -2; }
 bool valid = true;
 for (unsigned i = 0; i < count; i++) {
  uint32_t status = io->read(io->context, 0xd40 + i*24);
  io->statuses[i] = status;
  uint32_t required = (1u << 8) | ((wait & (1u << i)) ? 1u << 16 : 0);
  if ((status & required) != required) valid = false;
 }
 io->write(io->context, 0xd24, 1u << 16);
 io->write(io->context, 0xd24, 0);
 io->write(io->context, 0xd08, 1);
 for (unsigned i = total; i > 0; i--) io->write(io->context, offsets[i-1], saved[i-1]);
 for (unsigned i = 0; i < total; i++) if (io->read(io->context, offsets[i]) != saved[i]) valid = false;
 if (!valid) { io->failed = true; return -1; }
 return 1;
}
#endif
