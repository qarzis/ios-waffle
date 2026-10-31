/* SPDX-License-Identifier: BSD-3-Clause */
#include <assert.h>
#include "../waffle-ramlog-manifest.h"
static int parse(const char *s)
{
    struct waffle_ramlog_entry entries[5];
    FILE *f = tmpfile();
    assert(f);
    fputs(s, f); rewind(f);
    int result = waffle_ramlog_manifest(f, entries);
    fclose(f);
    return result;
}
int main(void)
{
    const char *ok = "GMU_LOG 0 00000008c1000000 4000\n"
        "GMU_LOG 1 00000008c1004000 4000\n"
        "GMU_LOG 2 00000008c1008000 4000\n"
        "GMU_LOG 3 00000008c100c000 4000\n"
        "HFI 0 00000008c1010000 4000\n";
    assert(parse(ok));
    char bad[512];
    strcpy(bad, ok); bad[0] = 'X'; assert(!parse(bad));
    strcpy(bad, ok); bad[8] = '9'; assert(!parse(bad));
    strcpy(bad, ok); bad[25] = '1'; assert(!parse(bad));
    assert(!parse("GMU_LOG 0 000000000c300000 4000\n"));
    assert(!parse("GMU_LOG 0 ffffffffffffffff 4000\n"));
    assert(!parse("GMU_LOG 0 00000008c1000000 100000\n"));
    assert(!parse("GMU_LOG 0 00000008c1000000 4000"));
    strcpy(bad, ok); strcat(bad, "HFI 0 00000008c1010000 4000\n"); assert(!parse(bad));
    uint64_t v;
    assert(!waffle_ramlog_hex("10000000000000000", &v));
    assert(!waffle_ramlog_hex("", &v));
    return 0;
}
