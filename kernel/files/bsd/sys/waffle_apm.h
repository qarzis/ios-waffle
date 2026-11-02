#ifndef WAFFLE_APM_H
#define WAFFLE_APM_H
#include <stdint.h>
#include <stddef.h>

#define WAFFLE_APM_GRAPH_OPEN 0x01001000u
#define WAFFLE_APM_GRAPH_CLOSE 0x01001004u
#define WAFFLE_APM_SUBGRAPH 0x4f00u
#define WAFFLE_APM_CONTAINER 0x5f00u
#define WAFFLE_APM_WRITE_EP 0x6f00u
#define WAFFLE_APM_READ_EP 0x6f01u

static inline size_t
waffle_apm_packet(uint32_t *out, size_t capacity, uint32_t opcode, uint32_t token)
{
 static const uint32_t open[] = {
  1,0x08001001,48,0,1,WAFFLE_APM_SUBGRAPH,3,
  0x0800100e,4,2,0x0800100f,4,2,0x08001010,4,1,
  1,0x08001000,64,0,1,WAFFLE_APM_CONTAINER,4,
  0x08001011,8,1,1,0x08001012,4,1,0x08001013,4,0xffffffff,0x08001014,4,2,
  1,0x08001002,32,0,1,WAFFLE_APM_SUBGRAPH,WAFFLE_APM_CONTAINER,2,
  0x07001000,WAFFLE_APM_WRITE_EP,0x07001001,WAFFLE_APM_READ_EP,
  1,0x08001003,56,0,2,
  WAFFLE_APM_WRITE_EP,1,0x08001015,8,0,1,
  WAFFLE_APM_READ_EP,1,0x08001015,8,1,0,0,
  1,0x08001004,24,0,1,WAFFLE_APM_WRITE_EP,1,WAFFLE_APM_READ_EP,2,0
 };
 static const uint32_t close[] = {1,0x08001005,8,0,1,WAFFLE_APM_SUBGRAPH};
 const uint32_t *payload;
 size_t size;
 if (opcode == WAFFLE_APM_GRAPH_OPEN) { payload = open; size = sizeof(open); }
 else if (opcode == WAFFLE_APM_GRAPH_CLOSE) { payload = close; size = sizeof(close); }
 else return 0;
 if (!out || capacity < size + 40) return 0;
 out[0] = (uint32_t)(size + 40) << 8 | 6u << 4;
 out[1] = 0x0302; out[2] = 1; out[3] = 1; out[4] = token; out[5] = opcode;
 out[6] = out[7] = out[8] = 0; out[9] = (uint32_t)size;
 for (size_t i = 0; i < size / 4; i++) out[i+10] = payload[i];
 return size + 40;
}
#endif
