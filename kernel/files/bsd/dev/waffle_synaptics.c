/* OnePlus 12 PJD110: S3910 TouchComm v1 over GPIO SPI.
 * Wiring: captured Android FDT; protocol: OnePlus synaptics_hbp driver.
 * Only volatile report/dynamic configuration is written. No flash commands.
 * VDD uses the live FDT's apps RSC DRV2 and captured cmd-db ldob4 address.
 */
#include <kern/clock.h>
#include <kern/thread.h>
#include <mach/mach_types.h>
#include <sys/systm.h>
#include <sys/macan_input.h>
#include "macan_touch_report.h"

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern kern_return_t thread_terminate(thread_t);
extern void loader_log_putc(char);

#define MISO 48
#define MOSI 49
#define CLK 50
#define CS 51
#define AVDD 108
#define RESET 161
#define IRQ 162
#define MAX_PAYLOAD 1024

static vm_offset_t pins;
static volatile unsigned stopping;
static int owned;
static const unsigned pin_ids[] = {MISO, MOSI, CLK, CS, AVDD, RESET, IRQ};
static uint32_t saved_cfg[7], saved_io[7];
static struct macan_contact contacts[10];
static unsigned max_x, max_y;

static uint32_t rd(unsigned p, unsigned off)
{
    return *(volatile uint32_t *)(pins + p * 0x1000 + off);
}
static void wr(unsigned p, unsigned off, uint32_t v)
{
    *(volatile uint32_t *)(pins + p * 0x1000 + off) = v;
    __asm__ volatile("dsb sy");
}
static void say(const char *fmt, ...) __printflike(1, 2);
static void say(const char *fmt, ...)
{
    char buf[256]; va_list ap;
    va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
    for (char *p = buf; *p; ++p) loader_log_putc(*p);
    printf("%s", buf);
}
static void level(unsigned p, int high) { wr(p, 4, high ? 2 : 0); }
static void edge(void) { delay_for_interval(2, NSEC_PER_USEC); }
static uint32_t rr(vm_offset_t base, unsigned off)
{
    return *(volatile uint32_t *)(base + off);
}
static void rw(vm_offset_t base, unsigned off, uint32_t value)
{
    *(volatile uint32_t *)(base + off) = value;
    __asm__ volatile("dsb sy");
}
static int enable_vdd(void)
{
    /* Live FDT: apps_rsc drv-2 17A20000, tcs-offset D00.
     * Android debugfs cmd-db: ldob4=41C00. Stock voltage=1800mV, HPM=7.
     * Channel0 reserves TCS0..2 for active requests. Use idle TCS0 only.
     * EFI USB is on its own CPU; no other XNU RPMh drivers are enabled.
     */
    vm_offset_t rsc = ml_io_map(0x17a20000, 0x10000);
    if (!rsc || stopping) return 0;
    unsigned major = (rr(rsc, 0) >> 16) & 255;
    uint32_t config = rr(rsc, 0xc);
    say("waffle-touch: RSC drv2 version=%x config=%x\n", rr(rsc, 0), config);
    if ((major != 3 && major != 4) || ((config >> 12) & 63) < 3 || (config >> 27) < 3)
        return 0;
    vm_offset_t t = rsc + 0xd00;
    if (!(rr(t, 0x28) & 1) || (rr(t, 4) & 1)) {
        say("waffle-touch: RSC TCS0 busy/pending; no power writes\n");
        return 0;
    }
    const unsigned off[] = {0, 0x20, 0x24, 0x2c,
        0x34, 0x38, 0x3c, 0x4c, 0x50, 0x54, 0x64, 0x68, 0x6c};
    uint32_t saved[13];
    for (unsigned i = 0; i < 13; ++i) saved[i] = rr(t, off[i]);
    say("waffle-touch: idle TCS0 control=%x irq=%x\n", saved[2], rr(t, 4));
    /* Trigger remains latched after a completed request. Match Linux's
     * clear-trigger, then clear-enable ordering. Never restore a trigger. */
    saved[2] &= ~(1u << 24);
    rw(t, 0x24, saved[2]);
    rw(t, 0x24, saved[2] & ~(1u << 16));
    const uint32_t addr[] = {0x41c00, 0x41c08, 0x41c04};
    const uint32_t data[] = {1800, 7, 1};
    for (unsigned i = 0; i < 3; ++i) {
        rw(t, 0x34 + i * 24, 0x10108);
        rw(t, 0x38 + i * 24, addr[i]);
        rw(t, 0x3c + i * 24, data[i]);
    }
    rw(t, 0x20, 7); rw(t, 0x2c, 7); rw(t, 0, saved[0] | 1);
    rw(t, 0x24, 1u << 16);
    rw(t, 0x24, (1u << 16) | (1u << 24));
    unsigned tries;
    for (tries = 0; tries < 2000 && !(rr(t, 4) & 1); ++tries)
        delay_for_interval(100, NSEC_PER_USEC);
    if (tries == 2000) {
        say("waffle-touch: VDD vote timed out; TCS left untouched\n");
        return 0;
    }
    int ok = 1;
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t status = rr(t, 0x40 + i * 24);
        say("waffle-touch: VDD command%u status=%x\n", i, status);
        if ((status & 0x10100) != 0x10100) ok = 0;
    }
    rw(t, 0x24, 1u << 16); rw(t, 0x24, 0); rw(t, 8, 1);
    for (unsigned i = 13; i > 0; --i) rw(t, off[i - 1], saved[i - 1]);
    /* Keep the volatile 1.8V vote through EFI return; Android owns DRV2
     * again after reboot. Never drop an inherited/shared rail on exit. */
    say("waffle-touch: VDD ldob4 1800mV HPM enabled=%d\n", ok);
    return ok;
}
static void gpio(unsigned p, int output, unsigned drive)
{
    /* Preserve platform bits; GPIO mux, no pull, AP ownership if available. */
    uint32_t v = rd(p, 0) & ~0x13ffu;
    if (v & (1u << 11)) v |= 1u << 12;
    wr(p, 0, v | (drive << 6) | (output ? 1u << 9 : 0));
}
static int transfer(const uint8_t *tx, uint8_t *rx, unsigned n)
{
    if (stopping) return 0;
    level(CS, 0); edge();
    for (unsigned i = 0; i < n; ++i) {
        uint8_t value = 0;
        for (int bit = 7; bit >= 0; --bit) {
            if (stopping) return 0;
            level(MOSI, tx ? (tx[i] >> bit) & 1 : 1);
            edge(); level(CLK, 1); edge();
            value = (uint8_t)((value << 1) | (rd(MISO, 4) & 1));
            level(CLK, 0);
        }
        if (rx) rx[i] = value;
    }
    edge(); level(CS, 1); edge();
    return 1;
}
static int packet(uint8_t *code, uint8_t *payload, unsigned *length)
{
    uint8_t header[4], tail[MAX_PAYLOAD + 3];
    static unsigned samples;
    if (!transfer(NULL, header, sizeof(header))) return 0;
    unsigned n = macan_le16(header + 2);
    if (samples++ < 12)
        say("waffle-touch: RX %02x %02x %02x %02x irq=%u\n",
            header[0], header[1], header[2], header[3], rd(IRQ, 4) & 1);
    if (header[0] != 0xa5 || n > MAX_PAYLOAD) return 0;
    if (n) {
        /* TCMv1 starts a NEW transaction with marker + CONTINUED_READ. */
        if (!transfer(NULL, tail, n + 3) || tail[0] != 0xa5 ||
            tail[1] != 3 || tail[n + 2] != 0x5a) {
            say("waffle-touch: invalid continuation len=%u\n", n);
            return 0;
        }
        memcpy(payload, tail + 2, n);
    }
    *code = header[1]; *length = n;
    return 1;
}
static int command(uint8_t cmd, const uint8_t *data, unsigned n,
    uint8_t *response, unsigned *length)
{
    uint8_t tx[MAX_PAYLOAD + 3], code;
    if (n > MAX_PAYLOAD) return 0;
    tx[0] = cmd; tx[1] = (uint8_t)n; tx[2] = (uint8_t)(n >> 8);
    if (n) memcpy(tx + 3, data, n);
    if (!transfer(tx, NULL, n + 3)) return 0;
    for (unsigned i = 0; i < 100 && !stopping; ++i) {
        delay_for_interval(5, NSEC_PER_MSEC);
        if (rd(IRQ, 4) & 1) continue;
        if (!packet(&code, response, length)) continue;
        /* Reports may precede the response. Busy/idle are not completion. */
        if (code == 0 || code == 2 || code == 3 || code >= 0x10) continue;
        say("waffle-touch: CMD %02x status=%02x len=%u\n", cmd, code, *length);
        return code == 1;
    }
    say("waffle-touch: CMD %02x timeout\n", cmd);
    return 0;
}
static void release_contacts(void)
{
    for (unsigned i = 0; i < 10; ++i) {
        if (contacts[i].active)
            redwood_touch_post(REDWOOD_TOUCH_UP, i, contacts[i].x, contacts[i].y);
        contacts[i].active = 0;
    }
}
static void restore_pins(void)
{
    if (!owned) return;
    level(CS, 1);
    /* Hold reset while returning SPI and AVDD to the firmware's settings. */
    level(RESET, 0);
    for (unsigned i = 0; i < 7; ++i) {
        wr(pin_ids[i], 4, saved_io[i] & 2);
        wr(pin_ids[i], 0, saved_cfg[i]);
    }
    owned = 0;
}
void waffle_synaptics_quiesce(void)
{
    /* RAM tests run one XNU CPU; loader_return stops other CPUs first. */
    stopping = 1;
    restore_pins();
}
static int configure(void)
{
    uint8_t response[MAX_PAYLOAD], code;
    unsigned n = 0;
    if (!packet(&code, response, &n) || code != 0x10 || n < 2 || response[1] != 1) {
        say("waffle-touch: no application identify; leaving firmware unchanged\n");
        return 0;
    }
    say("waffle-touch: identify version=%u application=%u\n", response[0], response[1]);
    if (!command(0x20, NULL, 0, response, &n) || n < 40 || macan_le16(response + 2))
        return 0;
    unsigned config_size = macan_le16(response + 12);
    max_x = macan_le16(response + 32); max_y = macan_le16(response + 34);
    unsigned objects = macan_le16(response + 36);
    say("waffle-touch: application x=%u y=%u objects=%u config=%u\n",
        max_x, max_y, objects, config_size);
    if (!max_x || !max_y || objects != 10 || config_size < 11 || config_size > MAX_PAYLOAD)
        return 0;
    uint8_t report = 0x23;
    if (!command(0x06, &report, 1, response, &n)) return 0;
    uint8_t lbp[] = {0x11, 2, 0}; /* DC_CONTROL_LBP_HBP = native coordinates */
    if (!command(0x24, lbp, sizeof(lbp), response, &n)) return 0;
    report = 0x11;
    if (!command(0x06, &report, 1, response, &n)) return 0;
    uint8_t config[MAX_PAYLOAD] = {2, 6, 4, 7, 4, 8, 16, 9, 16, 3, 0};
    if (!command(0x26, config, config_size, response, &n) ||
        !command(0x25, NULL, 0, response, &n) || n < 11 || memcmp(config, response, 11))
        return 0;
    return command(0x05, &report, 1, response, &n);
}
static void poll_reports(void)
{
    uint8_t response[MAX_PAYLOAD], code;
    unsigned n, failures = 0, frames = 0;
    say("waffle-touch: native coordinate polling started\n");
    while (!stopping && failures < 20) {
        if (rd(IRQ, 4) & 1) { delay_for_interval(2, NSEC_PER_MSEC); continue; }
        if (!packet(&code, response, &n)) {
            ++failures; delay_for_interval(5, NSEC_PER_MSEC); continue;
        }
        if (code == 0x10) { say("waffle-touch: unexpected controller reset\n"); break; }
        if (code != 0x11) { delay_for_interval(1, NSEC_PER_MSEC); continue; }
        struct macan_contact next[10];
        if (!macan_parse_contacts(response, n, max_x, max_y, next)) {
            ++failures; continue;
        }
        failures = 0; ++frames;
        for (unsigned i = 0; i < 10; ++i) {
            if (next[i].active)
                redwood_touch_post(contacts[i].active ? REDWOOD_TOUCH_MOVE : REDWOOD_TOUCH_DOWN,
                    i, next[i].x, next[i].y);
            else if (contacts[i].active)
                redwood_touch_post(REDWOOD_TOUCH_UP, i, contacts[i].x, contacts[i].y);
            if (frames <= 12 && (next[i].active || contacts[i].active))
                say("waffle-touch: frame=%u id=%u active=%u x=%u y=%u\n",
                    frames, i, next[i].active, next[i].x, next[i].y);
            contacts[i] = next[i];
        }
    }
    release_contacts();
    say("waffle-touch: poll ended frames=%u failures=%u\n", frames, failures);
}
static void probe(void *arg, wait_result_t result)
{
    (void)arg; (void)result;
    pins = ml_io_map(0x0f100000, 0x0b0000);
    if (!pins || stopping) goto done;
    if (!enable_vdd()) {
        say("waffle-touch: VDD unavailable; no GPIO changes\n");
        goto done;
    }
    for (unsigned i = 0; i < 7; ++i) {
        saved_cfg[i] = rd(pin_ids[i], 0); saved_io[i] = rd(pin_ids[i], 4);
        say("waffle-touch: GPIO%u cfg=%x io=%x\n", pin_ids[i], saved_cfg[i], saved_io[i]);
    }
    owned = 1;
    level(RESET, 0); gpio(RESET, 1, 3);
    level(AVDD, 1); gpio(AVDD, 1, 3);
    gpio(IRQ, 0, 3);
    level(CS, 1); level(CLK, 0); level(MOSI, 1);
    gpio(MISO, 0, 2); gpio(MOSI, 1, 2); gpio(CLK, 1, 2); gpio(CS, 1, 2);
    for (unsigned i = 0; i < 7; ++i)
        say("waffle-touch: configured GPIO%u cfg=%x io=%x\n",
            pin_ids[i], rd(pin_ids[i], 0), rd(pin_ids[i], 4));
    delay_for_interval(200, NSEC_PER_MSEC);
    if (stopping) goto done;
    level(RESET, 1);
    delay_for_interval(80, NSEC_PER_MSEC);
    if (!stopping && configure()) poll_reports();
    else if (!stopping) say("waffle-touch: setup failed; no touch input\n");
done:
    restore_pins();
    thread_terminate(current_thread());
}
void waffle_synaptics_init(void)
{
    thread_t t;
    if (kernel_thread_start(probe, NULL, &t) == KERN_SUCCESS) thread_deallocate(t);
}
