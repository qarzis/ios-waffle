#include <assert.h>
#include <string.h>
#include "../../kernel/files/bsd/sys/waffle_hfi.h"
int main(void)
{
    uint32_t q[12] = {1,0,0,1024}, ring[1024] = {0};
    uint32_t cmd[] = {0x10030c,122,0}, output[16], next = 99;
    assert(waffle_hfi_write(q,ring,cmd,3,&next) == 3 && next == 4);
    assert(q[11] == 0 && ring[3] == 0xfafafafa);
    q[11] = next;
    assert(waffle_hfi_read(q,ring,output,16,&next) == 3 && next == 4);
    assert(q[10] == 0 && !memcmp(cmd,output,sizeof(cmd)));
    q[10] = next;
    assert(!waffle_hfi_read(q,ring,output,16,&next));
    q[10] = 1020; q[11] = 1020;
    uint32_t large[] = {0x500,1,2,3,4};
    assert(waffle_hfi_write(q,ring,large,5,&next) == 5 && next == 4);
    q[11] = next;
    assert(waffle_hfi_read(q,ring,output,16,&next) == 5 && next == 4);
    assert(!memcmp(output,large,sizeof(large)));
    q[10] = 0; q[11] = 1020;
    assert(waffle_hfi_write(q,ring,cmd,3,&next) == -2);
    q[10] = 1024;
    assert(waffle_hfi_read(q,ring,output,16,&next) == -1);
    q[10] = 1;
    assert(waffle_hfi_write(q,ring,cmd,3,&next) == -1);
    q[10] = 0; q[11] = 4; ring[0] = 0;
    assert(waffle_hfi_read(q,ring,output,16,&next) == -2);
    ring[0] = 0x500;
    assert(waffle_hfi_read(q,ring,output,16,&next) == -2);
    q[11] = 8;
    assert(waffle_hfi_read(q,ring,output,4,&next) == -2);
    assert(waffle_hfi_write(q,ring,cmd,2,&next) == -1);
    q[0] = 0;
    assert(waffle_hfi_read(q,ring,output,16,&next) == -1);
    return 0;
}
