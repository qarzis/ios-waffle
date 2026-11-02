#!/usr/bin/env python3
"""Exercise the kernel's actual MDT validator against captured vendor files."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, required=True)
    args = parser.parse_args()
    source = (ROOT / "kernel/files/bsd/dev/macan_adsp.c").read_text()
    types = source[source.index("#define MAX_SEGMENTS"):source.index("static struct pas_image images[]")]
    function = source[source.index("static bool\nfirmware_check("):source.index("static bool\npas_load(")]
    init = source[source.index("void\nmacan_adsp_init(void)"):]
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
static bool from_root;
static const char *directory;
static int fault;
static uint64_t mach_absolute_time(void) { return 0; }
static void absolutetime_to_nanoseconds(uint64_t v, uint64_t *out) { *out = v; }
static const uint8_t *image_file(const char *name, uint64_t *size) {
 char path[4096];
 snprintf(path, sizeof(path), "%s/%s", directory, name);
 FILE *file = fopen(path, "rb");
 if (!file) return NULL;
 assert(fseek(file, 0, SEEK_END) == 0);
 long length = ftell(file);
 assert(length > 0 && fseek(file, 0, SEEK_SET) == 0);
 uint8_t *data = malloc((size_t)length);
 assert(data && fread(data, 1, (size_t)length, file) == (size_t)length);
 fclose(file);
 from_root = true;
 *size = (uint64_t)length;
 if (strstr(name, ".mdt")) {
  if (fault == 1) data[0] = 0;
  if (fault == 2) *size = 51;
  if (fault == 3) { data[44] = 255; data[45] = 255; }
 } else if (fault == 4) { --*size; }
 return data;
}
static void file_free(const uint8_t *data, uint64_t size, bool owned) {
 (void)size;
 if (owned) free((void *)data);
}
'''
    gates = r'''
typedef uintptr_t thread_t;
#define KERN_SUCCESS 0
static uint32_t mode, adsp_vote, new_from;
static bool boot_runs;
static bool waffle_board;
static uint32_t arg_mode, arg_waffle, arg_macan;
static unsigned workers, crash_reads;
static struct pas_image images[2];
static struct { uint32_t phys; } ipcc;
static bool PE_parse_boot_argn(const char *name, void *out, size_t size) {
 assert(size == 4);
 if (!strcmp(name, "adsp")) *(uint32_t *)out = arg_mode;
 else if (!strcmp(name, "waffle")) *(uint32_t *)out = arg_waffle;
 else if (!strcmp(name, "macan")) *(uint32_t *)out = arg_macan;
 else return false;
 return true;
}
static void adsp_thread(void) { abort(); }
static int kernel_thread_start(void (*fn)(void), void *arg, thread_t *out) {
 (void)fn; (void)arg; *out = 1; ++workers; return KERN_SUCCESS;
}
static void thread_deallocate(thread_t thread) { (void)thread; }
static void show_crash_reason(void) { ++crash_reads; }
'''
    cases = r'''
static void check(const char *name, uint32_t base, uint32_t capacity, int damage, bool expected) {
 struct pas_image im = { .name = name, .base = base, .capacity = capacity };
 fault = damage;
 assert(firmware_check(&im) == expected);
 if (expected && !strcmp(name, "adsp")) assert(im.span == 0x5280000);
 file_free(im.mdt, im.mdt_size, im.owned);
}
int main(int argc, char **argv) {
 assert(argc == 2); directory = argv[1];
 check("adsp", 0x9df00000, 0x5280000, 0, true);
 check("adsp_dtb", 0x9de80000, 0x80000, 0, true);
 check("adsp", 0x9f100000, 0x4b00000, 0, false);
 for (int damage = 1; damage <= 4; ++damage)
  check("adsp", 0x9df00000, 0x5280000, damage, false);
 arg_waffle = 1; arg_macan = 1;
 for (unsigned requested = 0; requested <= 7; ++requested) {
  workers = 0; arg_mode = requested; boot_runs = false;
  macan_adsp_init();
  assert(workers == (requested >= 3 && requested <= 6));
  assert(!crash_reads);
  if (requested >= 3 && requested <= 6) {
   assert(images[0].base == 0x9de80000 && images[0].capacity == 0x80000);
   assert(images[1].base == 0x9df00000 && images[1].capacity == 0x5280000);
   assert(ipcc.phys == 0x406000);
   assert(waffle_board);
  }
 }
 arg_waffle = 0; arg_mode = 3; workers = 0; macan_adsp_init(); assert(!workers);
 arg_mode = 1; macan_adsp_init(); assert(workers == 1);
 puts("PASS: native ADSP/DTB accepted; donor capacity and four damaged inputs rejected");
 puts("PASS: Waffle diagnostic mode gates and native resources; donor boot modes preserved");
}
'''
    with tempfile.TemporaryDirectory(prefix="waffle-audio-host-") as temp:
        path = Path(temp)
        (path / "test.c").write_text(harness + types + function + gates + init + cases)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-format",
                        "-fsanitize=address,undefined", "-g", str(path / "test.c"), "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test"), str(args.firmware.resolve())], check=True)


if __name__ == "__main__":
    main()
