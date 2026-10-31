#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../kernel/files/bsd/dev/macan_touch_report.h"

static void frame(uint8_t p[50])
{
    memset(p, 0, 50);
    for (unsigned i = 0; i < 10; ++i) p[i * 5] = (uint8_t)i;
}
int main(void)
{
    uint8_t p[50]; struct macan_contact c[10];
    frame(p);
    assert(macan_parse_contacts(p, sizeof(p), 23040, 50688, c));
    for (unsigned i = 0; i < 10; ++i) assert(!c[i].active);
    /* Two contacts at opposite corners, in a permuted slot order. */
    p[0] = 0x19; p[45] = 0x20;
    p[46] = 0x00; p[47] = 0x5a; p[48] = 0x00; p[49] = 0xc6;
    assert(macan_parse_contacts(p, 50, 23040, 50688, c));
    assert(c[9].active && c[9].x == 0 && c[9].y == 0);
    assert(c[0].active && c[0].x == 65535 && c[0].y == 65535);
    p[46]++;
    assert(!macan_parse_contacts(p, 50, 23040, 50688, c));
    p[46]--; p[48]++;
    assert(!macan_parse_contacts(p, 50, 23040, 50688, c));
    frame(p); p[0] = 0x10; p[1] = 0; p[2] = 0x2d; p[3] = 0; p[4] = 0x63;
    assert(macan_parse_contacts(p, 50, 23040, 50688, c));
    assert(c[0].x == 32767 && c[0].y == 32767);
    p[0] = 0x60; /* Palm must release the previous finger. */
    assert(macan_parse_contacts(p, 50, 23040, 50688, c) && !c[0].active);
    for (unsigned n = 0; n < 50; ++n) assert(!macan_parse_contacts(p, n, 23040, 50688, c));
    assert(!macan_parse_contacts(p, 51, 23040, 50688, c));
    assert(!macan_parse_contacts(p, 50, 0, 50688, c));
    frame(p); p[5] = 0;
    assert(!macan_parse_contacts(p, 50, 23040, 50688, c));
    frame(p); p[0] = 0x1a;
    assert(!macan_parse_contacts(p, 50, 23040, 50688, c));
    frame(p); p[0] = 0x70;
    assert(!macan_parse_contacts(p, 50, 23040, 50688, c));
    puts("waffle touch: contacts, scaling, palm/release and malformed frames passed");
    return 0;
}
