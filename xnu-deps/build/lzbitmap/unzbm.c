#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libzbitmap.h"
#define BLOCK 0x10000u
#define LZBITMAP_RSRC 14
#ifdef _WIN32
#include <wchar.h>
typedef wchar_t pchar;
#define P(s) L##s
#define popen_file _wfopen
#define premove _wremove
#define pprintf swprintf
#define PS "%ls"
#define STREAM L"%ls:%ls"
#else
typedef char pchar;
#define P(s) s
#define popen_file fopen
#define premove remove
#define pprintf snprintf
#define PS "%s"
#define STREAM "%s:%s"
#endif
static uint8_t *
slurp(const pchar *path, size_t *size)
{
 FILE *f = popen_file(path, P("rb"));
 uint8_t *data;
 if (!f) {
  return NULL;
 }
 fseek(f, 0, SEEK_END);
 *size = (size_t)ftell(f);
 rewind(f);
 data = malloc(*size + 1);
 if (fread(data, 1, *size, f) != *size) {
  free(data);
  data = NULL;
 }
 fclose(f);
 return data;
}
static uint32_t
le32(const uint8_t *p)
{
 return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}
static int
expand(const pchar *name)
{
 pchar header_path[4096], fork_path[4096];
 size_t header_size, fork_size;
 uint8_t *header, *fork, *out;
 uint64_t size, blocks;
 FILE *f;
 pprintf(header_path, sizeof(header_path) / sizeof(pchar), STREAM, name, P("com.apple.decmpfs"));
 pprintf(fork_path, sizeof(fork_path) / sizeof(pchar), STREAM, name, P("com.apple.ResourceFork"));
 header = slurp(header_path, &header_size);
 fork = slurp(fork_path, &fork_size);
 if (!header || !fork || header_size < 16 || memcmp(header, "fpmc", 4) != 0 || le32(header + 4) != LZBITMAP_RSRC) {
  fprintf(stderr, "unzbm: " PS ": not an LZBITMAP resource-fork file\n", name);
  return 1;
 }
 size = le32(header + 8) | (uint64_t)le32(header + 12) << 32;
 blocks = (size + BLOCK - 1) / BLOCK;
 if ((blocks + 1) * 4 > fork_size) {
  fprintf(stderr, "unzbm: " PS ": block table does not fit\n", name);
  return 1;
 }
 out = malloc(size ? size : 1);
 for (uint64_t b = 0; b < blocks; b++) {
  uint32_t from = le32(fork + 4 * b), to = le32(fork + 4 * (b + 1));
  size_t want = size - b * BLOCK > BLOCK ? BLOCK : (size_t)(size - b * BLOCK), got = 0;
  if (from < to && to <= fork_size && to - from == want + 1 && fork[from] == 0xff) {
   memcpy(out + b * BLOCK, fork + from + 1, want);
   continue;
  }
  if (from > to || to > fork_size || zbm_decompress(out + b * BLOCK, want, fork + from, to - from, &got) != 0 ||
      got != want) {
   fprintf(stderr, "unzbm: " PS ": block %llu does not decompress\n", name, (unsigned long long)b);
   return 1;
  }
 }
 f = popen_file(name, P("wb"));
 if (!f || fwrite(out, 1, size, f) != size || fclose(f) != 0) {
  fprintf(stderr, "unzbm: " PS ": %s\n", name, strerror(errno));
  return 1;
 }
 premove(header_path);
 premove(fork_path);
 free(out);
 free(fork);
 free(header);
 return 0;
}
#ifdef _WIN32
int
wmain(int argc, wchar_t **argv)
#else
int
main(int argc, char **argv)
#endif
{
 int failed = 0;
 for (int i = 1; i < argc; i++) {
  failed += expand(argv[i]);
 }
 return failed != 0;
}
