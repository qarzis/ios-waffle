#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_gmu_firmware.h"
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i));
}
int main(int argc, char **argv)
{
    assert(waffle_fw_region(0, 0x4000) == 1);
    assert(waffle_fw_region(0x3ffc, 8) == 0);
    assert(waffle_fw_region(0x4000, 0x12ff0) == 3);
    assert(waffle_fw_region(0x10007fdc, 0x18) == 2);
    assert(waffle_fw_region(0x10007ffc, 8) == 0);
    assert(waffle_fw_region(0x60000000, 4096) == 4);
    assert(!waffle_fw_region(0x7ffff000, 8192));
    assert(!waffle_fw_region(0xfffffff0, 4096));
    assert(!waffle_fw_region(0, 0));
    uint8_t bytes[36] = {0};
    put32(bytes, 0x4000); put32(bytes + 8, 1); put32(bytes + 12, 4096);
    put32(bytes + 16, 0x4000); put32(bytes + 20, 4); put32(bytes + 32, 0x12345678);
    struct waffle_fw_block b;
    size_t at = 0;
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == 1 && at == 16 && b.value == 4096);
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == 1 && at == 36 && waffle_fw_u32(b.payload) == 0x12345678);
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == 0);
    at = 0;
    assert(waffle_fw_next(bytes, 15, &at, &b) == -1 && at == 0);
    at = 16;
    assert(waffle_fw_next(bytes, 35, &at, &b) == -1 && at == 16);
    put32(bytes + 20, 0xfffffffc);
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == -1 && at == 16);
    put32(bytes, 3); at = 0;
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == -1 && at == 0);
    put32(bytes, 0xfffffffc); put32(bytes + 4, 8);
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == -1 && at == 0);
    at = sizeof(bytes) + 1;
    assert(waffle_fw_next(bytes, sizeof(bytes), &at, &b) == -1);
    if (argc > 1) {
        FILE *file = fopen(argv[1], "rb"); assert(file);
        assert(!fseek(file, 0, SEEK_END)); long size = ftell(file);
        assert(size > 0 && size <= 1024 * 1024); rewind(file);
        uint8_t *data = malloc((size_t)size); assert(data);
        assert(fread(data, 1, (size_t)size, file) == (size_t)size); fclose(file);
        unsigned count = 0, payloads = 0; at = 0; int result;
        while ((result = waffle_fw_next(data, (size_t)size, &at, &b)) == 1) {
            ++count;
            if (b.size) { ++payloads; assert(waffle_fw_region(b.address, b.size)); }
            else if (b.type == 1 || b.type == 7) assert(waffle_fw_region(b.address, b.value));
        }
        assert(result == 0 && at == (size_t)size && count && payloads);
        printf("Captured GMU firmware: %u blocks, %u payloads parsed\n", count, payloads);
        free(data);
    }
    puts("GMU parser boundary checks passed");
    return 0;
}
