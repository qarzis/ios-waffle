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

static inline int waffle_return_seconds_allowed(uint64_t seconds)
{
#if defined(WAFFLE_USERLAND) && defined(WAFFLE_UI_SOAK_TEST)
    if (seconds == 660) return 1;
#endif
    return seconds >= 1 && seconds <= WAFFLE_RETURN_LIMIT;
}
static inline int waffle_return_token_allowed(const char *word,size_t size)
{
#if defined(WAFFLE_USERLAND) && defined(WAFFLE_UI_SOAK_TEST)
    if (waffle_number(word,size,"loader_return_after=",660,660)) return 1;
#endif
    return waffle_number(word,size,"loader_return_after=",1,WAFFLE_RETURN_LIMIT);
}
/* The resident USB loader owns one core; XNU may use the other seven. */
static inline int waffle_cpu_token_allowed(const char *word,size_t size)
{
#if defined(WAFFLE_USERLAND)
    return waffle_number(word,size,"cpus=",1,7);
#else
    (void)word; (void)size;
    return 0;
#endif
}
static inline int waffle_cmdline_allowed(const char *line)
{
    unsigned matrix=0,measure=0,lpac=0,zap=0,writeback=0,ib=0,session=0,dynamic_bo=0,compute=0,image=0,repeated=0,glsl_prepare=0,prepare_count=0,present=0,dispatch=0,gpu_count=0;
    int prepare93=0,native94=0;
    unsigned battery_readonly=0,battery_boot=0;
    unsigned soak=0,returns=0,gl_image=0,cpus=0,torch=0,audio=0,audio_budget=0,display_survey=0,hardware_vsync=0,display_flush=0,display_flip=0,display_present=0;
    while (*line) {
        while (*line == ' ') line++;
        const char *end = line;
        while (*end && *end != ' ') end++;
        size_t size = (size_t)(end - line);
        if (!size) break;
        soak+=waffle_number(line,size,"loader_return_after=",660,660);
        returns+=waffle_return_token_allowed(line,size);
        cpus+=waffle_cpu_token_allowed(line,size);
#if defined(WAFFLE_USERLAND)
        display_present+=waffle_token_equal(line,size,"waffle_display_present=1");
        battery_readonly+=waffle_number(line,size,"waffle_battery_readonly=",1,2);
        battery_boot+=waffle_token_equal(line,size,"adsp=6");
        display_flip+=waffle_token_equal(line,size,"waffle_display_flip=1");
        display_flush+=waffle_token_equal(line,size,"waffle_display_flush=1");
        hardware_vsync+=waffle_token_equal(line,size,"waffle_vsync=1");
        display_survey+=waffle_token_equal(line,size,"waffle_vsync_audit=1");
        torch+=waffle_number(line,size,"waffle_torch=",1,3);
        audio+=waffle_token_equal(line,size,"adsp=3") || waffle_token_equal(line,size,"adsp=4") || waffle_token_equal(line,size,"adsp=5") || waffle_token_equal(line,size,"adsp=6") || waffle_token_equal(line,size,"adsp=7") || waffle_token_equal(line,size,"adsp=8");
        audio_budget+=waffle_number(line,size,"loader_return_after=",1,60);
#endif
        gl_image+=waffle_token_equal(line,size,"waffle_image=13");
        matrix+=waffle_token_equal(line,size,"waffle_ecats_access=1");
        measure+=waffle_token_equal(line,size,"waffle_gpu_measure=1");
        lpac+=waffle_token_equal(line,size,"waffle_lpac_map=1");
        zap+=waffle_token_equal(line,size,"waffle_zap=1");
        writeback+=waffle_token_equal(line,size,"waffle_writeback=1");
        ib+=waffle_token_equal(line,size,"waffle_ib=1");
        session+=waffle_token_equal(line,size,"waffle_session=1");
        dynamic_bo+=waffle_token_equal(line,size,"waffle_dynamic_bo=1");
        compute+=waffle_token_equal(line,size,"waffle_compute=1") || waffle_token_equal(line,size,"waffle_compute=2");
        image+=waffle_token_equal(line,size,"waffle_image=13") || waffle_token_equal(line,size,"waffle_image=12") || waffle_token_equal(line,size,"waffle_image=11") || waffle_token_equal(line,size,"waffle_image=10") || waffle_token_equal(line,size,"waffle_image=8") || waffle_token_equal(line,size,"waffle_image=9") || waffle_token_equal(line,size,"waffle_image=1") || waffle_token_equal(line,size,"waffle_image=2") || waffle_token_equal(line,size,"waffle_image=3") || waffle_token_equal(line,size,"waffle_image=4") || waffle_token_equal(line,size,"waffle_image=5") || waffle_token_equal(line,size,"waffle_image=6") || waffle_token_equal(line,size,"waffle_image=7");
        glsl_prepare+=waffle_token_equal(line,size,"waffle_image=9");
        prepare_count+=waffle_token_equal(line,size,"waffle_compute=1");
        present+=waffle_token_equal(line,size,"waffle_image=3");
        repeated+=waffle_token_equal(line,size,"waffle_image=13") || waffle_token_equal(line,size,"waffle_image=12") || waffle_token_equal(line,size,"waffle_image=11") || waffle_token_equal(line,size,"waffle_image=10") || waffle_token_equal(line,size,"waffle_image=8") || waffle_token_equal(line,size,"waffle_image=4") || waffle_token_equal(line,size,"waffle_image=5") || waffle_token_equal(line,size,"waffle_image=6") || waffle_token_equal(line,size,"waffle_image=7");
        dispatch+=waffle_token_equal(line,size,"waffle_compute=2");
        gpu_count+=waffle_number(line,size,"waffle_gpu=",1,94);
        prepare93|=waffle_number(line,size,"waffle_gpu=",93,93);
        native94|=waffle_number(line,size,"waffle_gpu=",94,94);
        if (!waffle_token_equal(line, size, "-v") &&
            !waffle_number(line, size, "bootcpu=", 0, 7) &&
            !waffle_number(line, size, "epoch=", 0, UINT32_MAX) &&
            !waffle_return_token_allowed(line, size) &&
            !waffle_number(line, size, "fbscale=", 1, 3) &&
            !waffle_cpu_token_allowed(line,size) &&
#if defined(WAFFLE_USERLAND)
            !waffle_token_equal(line,size,"waffle_display_present=1") &&
            !waffle_number(line,size,"waffle_battery_readonly=",1,2) &&
            !waffle_token_equal(line,size,"waffle_display_flip=1") &&
            !waffle_token_equal(line,size,"waffle_display_flush=1") &&
            !waffle_token_equal(line,size,"waffle_vsync=1") &&
            !waffle_token_equal(line,size,"waffle_vsync_audit=1") &&
            !waffle_number(line,size,"waffle_torch=",1,3) &&
            !waffle_token_equal(line,size,"adsp=3") && !waffle_token_equal(line,size,"adsp=4") && !waffle_token_equal(line,size,"adsp=5") && !waffle_token_equal(line,size,"adsp=6") && !waffle_token_equal(line,size,"adsp=7") && !waffle_token_equal(line,size,"adsp=8") &&
#endif
            !waffle_gpu_token_allowed(line, size)) return 0;
        line = end;
    }
    if (battery_readonly > 1 || (battery_readonly && (battery_boot != 1 || audio != 1))) return 0;
    return display_present<=1 && (!display_present || (!audio && !display_survey && !display_flip && !display_flush && gpu_count==1 && native94 && gl_image==1)) && display_flip<=1 && (!display_flip || (!audio && !display_survey && !hardware_vsync && !display_flush && gpu_count==1 && native94 && gl_image==1)) && display_flush<=1 && (!display_flush || (!audio && !display_survey && !hardware_vsync && gpu_count==1 && native94 && gl_image==1)) && hardware_vsync<=1 && !(hardware_vsync && (audio || display_survey)) && display_survey<=1 && !(display_survey && audio) && (!audio || (audio==1 && returns==1 && audio_budget==1 && !gpu_count && !torch && !cpus)) &&
        cpus<=1 && torch<=1 && ((!matrix && !measure) ||
        (matrix<=1 && measure<=1 && gpu_count==1 && prepare93)) &&
        (!lpac || (lpac==1 && gpu_count==1 && (prepare93 || native94))) &&
        (!zap || (zap==1 && lpac==1 && gpu_count==1 && native94)) &&
        (!writeback || (writeback==1 && zap==1 && lpac==1 && gpu_count==1 && native94)) &&
        (!ib || (ib==1 && writeback==1 && zap==1 && lpac==1 && gpu_count==1 && native94)) &&
        (!session || (session==1 && ib==1 && writeback==1 && zap==1 && lpac==1 && gpu_count==1 && native94)) &&
        (!dynamic_bo || (dynamic_bo==1 && session==1 && gpu_count==1 && native94)) &&
        (!compute || (compute==1 && dynamic_bo==1 && session==1 && gpu_count==1 && native94)) &&
        (!glsl_prepare || (glsl_prepare==1 && prepare_count==1)) &&
        (!repeated || (repeated==1 && dispatch==1)) &&
        (!present || (present==1 && dispatch==1)) &&
        (!image || (image==1 && compute==1 && dynamic_bo==1 && session==1 && gpu_count==1 && native94)) &&
        (!soak || (soak==1 && returns==1 && native94 && gl_image==1));
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
        waffle_token_equal(word,size,"waffle_ecats_access=1") ||
        waffle_token_equal(word,size,"waffle_gpu_measure=1") ||
        waffle_token_equal(word,size,"waffle_lpac_map=1") ||
        waffle_token_equal(word,size,"waffle_zap=1") ||
        waffle_token_equal(word,size,"waffle_writeback=1") ||
        waffle_token_equal(word,size,"waffle_ib=1") ||
        waffle_token_equal(word,size,"waffle_session=1") ||
        waffle_token_equal(word,size,"waffle_dynamic_bo=1") ||
        waffle_token_equal(word,size,"waffle_compute=1") || waffle_token_equal(word,size,"waffle_compute=2") ||
        (waffle_token_equal(word,size,"waffle_image=1") || waffle_token_equal(word,size,"waffle_image=2") || waffle_token_equal(word,size,"waffle_image=3") || waffle_token_equal(word,size,"waffle_image=4") || waffle_token_equal(word,size,"waffle_image=5") || waffle_token_equal(word,size,"waffle_image=6") || waffle_token_equal(word,size,"waffle_image=7") || waffle_token_equal(word,size,"waffle_image=8") || waffle_token_equal(word,size,"waffle_image=9") || waffle_token_equal(word,size,"waffle_image=10") || waffle_token_equal(word,size,"waffle_image=11") || waffle_token_equal(word,size,"waffle_image=12") || waffle_token_equal(word,size,"waffle_image=13"));
#else
    (void)word; (void)size;
    return 0;
#endif
}

static inline int waffle_present_requested(const char *line)
{
    while(*line){
        while(*line==' ')line++;
        const char *end=line;while(*end && *end!=' ')end++;
        if(waffle_token_equal(line,(size_t)(end-line),"waffle_image=3"))return 1;
        line=end;
    }
    return 0;
}

#endif
