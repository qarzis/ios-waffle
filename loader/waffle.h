#ifndef XNULOADER_WAFFLE_H
#define XNULOADER_WAFFLE_H
#include <stdint.h>
#include <stddef.h>
#if defined(WAFFLE_USERLAND)
#define WAFFLE_RETURN_LIMIT 300
#else
#define WAFFLE_RETURN_LIMIT 60
#endif

/* Waffle boot policy; unported Ace 6T peripheral options remain refused. */
static inline int waffle_gpu_token_allowed(const char *word, size_t size);
static inline int waffle_checkpoint_allowed(uint64_t checkpoint)
{
#if defined(WAFFLE_USERLAND)
    if (checkpoint == 0) return 1;
#endif
    return (checkpoint >= 1 && checkpoint <= 5) ||
        (checkpoint >= 10 && checkpoint <= 23) ||
        (checkpoint >= 50 && checkpoint <= 64) || checkpoint == 999;
}

static inline int waffle_token_equal(const char *word, size_t size, const char *value)
{
    size_t i = 0;
    while (i < size && value[i] && word[i] == value[i]) i++;
    return i == size && value[i] == 0;
}

static inline int waffle_number(const char *word, size_t size, const char *key,
    uint64_t minimum, uint64_t maximum)
{
    size_t i = 0;
    while (i < size && key[i] && word[i] == key[i]) i++;
    if (key[i] || i == size) return 0;
    uint64_t number = 0;
    for (; i < size; i++) {
        if (word[i] < '0' || word[i] > '9') return 0;
        unsigned digit = (unsigned)(word[i] - '0');
        if (number > maximum / 10 ||
            (number == maximum / 10 && digit > maximum % 10)) return 0;
        number = number * 10 + digit;
    }
    return number >= minimum;
}

static inline int waffle_cmdline_allowed(const char *line)
{
    unsigned matrix=0,gpu_count=0;
    int prepare93=0;
    while (*line) {
        while (*line == ' ') line++;
        const char *end = line;
        while (*end && *end != ' ') end++;
        size_t size = (size_t)(end - line);
        if (!size) break;
        matrix+=waffle_token_equal(line,size,"waffle_ecats_access=1");
        gpu_count+=waffle_number(line,size,"waffle_gpu=",1,94);
        prepare93|=waffle_number(line,size,"waffle_gpu=",93,93);
        if (!waffle_token_equal(line, size, "-v") &&
            !waffle_number(line, size, "bootcpu=", 0, 7) &&
            !waffle_number(line, size, "epoch=", 0, UINT32_MAX) &&
            !waffle_number(line, size, "loader_return_after=", 1, WAFFLE_RETURN_LIMIT) &&
            !waffle_number(line, size, "fbscale=", 1, 3) &&
            !waffle_gpu_token_allowed(line, size)) return 0;
        line = end;
    }
    return !matrix || (matrix==1 && gpu_count==1 && prepare93);
}
static inline int waffle_pll_control_requested(const char *line)
{
    while (*line) {
        while (*line==' ') line++;
        const char *end=line;
        while (*end && *end!=' ') end++;
        if (waffle_number(line,(size_t)(end-line),"waffle_gpu=",92,94)) return 1;
        line=end;
    }
    return 0;
}
/* Private handoff is appended only after verified firmware requests. External
 * payloads cannot submit this token through waffle_cmdline_allowed(). */
static inline int waffle_pll_append_proof(char *line,size_t capacity,int verified)
{
    if (!verified) return 0;
    size_t length=0;
    while (length<capacity && line[length]) length++;
    if (length==capacity) return 0;
    static const char proof[]=" waffle_fw_cxmx=256";
    if (sizeof(proof)>capacity-length) return 0;
    for (size_t i=0;i<sizeof(proof);i++) line[length+i]=proof[i];
    return 1;
}
static inline int waffle_gpu_token_allowed(const char *word, size_t size)
{
#if defined(WAFFLE_USERLAND)
    return waffle_number(word, size, "waffle_gpu=", 1, 94) ||
        waffle_token_equal(word,size,"waffle_ecats_access=1");
#else
    (void)word; (void)size;
    return 0;
#endif
}
#endif
