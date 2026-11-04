#include <assert.h>
#include <string.h>
#include <sys/waffle_battery_readonly.h>
int main(void)
{
 uint8_t request[26], reply[26];
 memset(request, 0xa5, sizeof(request));
 assert(waffle_battery_request(request + 1, 24, 0x30, 4));
 const uint8_t expected[24] = {0x0a,0x80,0,0,1,0,0,0,0x30,0,0,0,0,0,0,0,4,0,0,0,0,0,0,0};
 assert(!memcmp(request + 1, expected, 24) && request[0] == 0xa5 && request[25] == 0xa5);
 for (unsigned opcode = 0; opcode < 256; opcode++) {
  if (opcode == 0x30 || opcode == 0x32) continue;
  assert(!waffle_battery_request(request + 1, 24, opcode, 4));
  assert(!memcmp(request + 1, expected, 24));
 }
 assert(!waffle_battery_request(request, 23, 0x30, 4));
 assert(!waffle_battery_request(NULL, 24, 0x30, 4));
 assert(!waffle_battery_request(request, 24, 0x30, 13)); /* HakiOS other-phone temperature ID */
 assert(!waffle_battery_request(request, 24, 0x30, UINT32_MAX));
 memset(reply, 0, sizeof(reply));
 waffle_battery_put(reply + 1, 32778);waffle_battery_put(reply + 5, 1);
 waffle_battery_put(reply + 9, 0x30);waffle_battery_put(reply + 13, 4);
 waffle_battery_put(reply + 17, 9600);
 uint32_t value = 0;
 assert(waffle_battery_response(reply + 1, 24, 0x30, 4, &value) && value == 9600);
 for (unsigned n = 0; n < 26; n++) if (n != 24) {
  value = 0xdeadbeef;
  assert(!waffle_battery_response(reply + 1, n, 0x30, 4, &value) && value == 0xdeadbeef);
 }
 const unsigned fields[] = {0,4,8,12,20};
 for (unsigned i = 0; i < sizeof(fields)/sizeof(fields[0]); i++) {
  unsigned at = 1 + fields[i];uint8_t old = reply[at];reply[at] ^= 1;value = 0xdeadbeef;
  assert(!waffle_battery_response(reply + 1, 24, 0x30, 4, &value) && value == 0xdeadbeef);
  reply[at] = old;
 }
 assert(!waffle_battery_response(NULL, 24, 0x30, 4, &value));
 assert(!waffle_battery_response(reply + 1, 24, 0x30, 4, NULL));
 assert(waffle_battery_value_valid(0x30,4,0) && waffle_battery_value_valid(0x30,4,10000));
 assert(!waffle_battery_value_valid(0x30,4,10001));
 assert(waffle_battery_value_valid(0x30,9,(uint32_t)-123456));
 assert(!waffle_battery_value_valid(0x30,9,INT32_MAX));
 assert(waffle_battery_value_valid(0x30,12,(uint32_t)-4000));
 assert(!waffle_battery_value_valid(0x30,12,(uint32_t)-4001));
 assert(!waffle_battery_value_valid(0x30,12,10001));
 assert(waffle_battery_value_valid(0x30,7,8600000));
 assert(!waffle_battery_value_valid(0x30,7,0));
 assert(waffle_battery_value_valid(0x32,0,2) && !waffle_battery_value_valid(0x32,0,3));
 return 0;
}
