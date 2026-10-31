/* SPDX-License-Identifier: BSD-3-Clause */
/* Standalone diagnostic client using the pinned QDL USB backend. */
#include <stdlib.h>
#include <sys/stat.h>
#include <time.h>
#include "qdl.h"
#include "waffle-sahara-ramlogs.h"
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "Sahara host must be little endian");
bool qdl_debug;
struct context {
    struct qdl_device *usb;
    const char *directory;
    struct waffle_sahara_log_result *result;
    bool resetting;
};
static uint64_t milliseconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now)) return 0;
    return (uint64_t)now.tv_sec*1000+(unsigned long)now.tv_nsec/1000000;
}
static int receive(void *arg, void *data, unsigned bytes)
{
    struct context *c=arg;
    uint64_t start=milliseconds();
    int n=c->usb->read(c->usb,data,bytes,1000);
    fprintf(stderr,"RAMLOG stage=%s page=%u reset=%u RX requested=%u actual=%d elapsed_ms=%llu\n",
        waffle_sahara_log_stage_name(c->result->stage),c->result->pages,c->resetting,
        bytes,n,(unsigned long long)(milliseconds()-start));
    /* Decode only control headers, never table or page contents. */
    if (!c->resetting && n>=8 && (c->result->stage==WAFFLE_LOG_HELLO ||
        c->result->stage==WAFFLE_LOG_DEBUG_HEADER)) {
        uint32_t header[2]; memcpy(header,data,sizeof(header));
        fprintf(stderr,"RAMLOG control command=%u length=%u\n",header[0],header[1]);
    }
    return n;
}
static int transmit(void *arg, const void *data, unsigned bytes)
{
    struct context *c=arg;
    uint32_t command=0;
    if (bytes>=4) memcpy(&command,data,4);
    if (command==7) c->resetting=true;
    uint64_t start=milliseconds();
    int n=c->usb->write(c->usb,data,bytes,1000);
    fprintf(stderr,"RAMLOG stage=%s page=%u reset=%u TX command=%u requested=%u actual=%d elapsed_ms=%llu\n",
        waffle_sahara_log_stage_name(c->result->stage),c->result->pages,c->resetting,
        command,bytes,n,(unsigned long long)(milliseconds()-start));
    return n;
}
static int save_page(void *arg, unsigned slot, const void *data, unsigned bytes)
{
    struct context *c=arg;
    char path[4096];
    if(slot>4 || bytes!=0x4000) return 0;
    int n=slot==4 ? snprintf(path,sizeof(path),"%s/waffle_hfi0.bin",c->directory) :
        snprintf(path,sizeof(path),"%s/waffle_gmu%u.bin",c->directory,slot);
    if(n<0 || (size_t)n>=sizeof(path)) return 0;
    FILE *f=fopen(path,"wbx");
    if(!f) return 0;
    int ok=fwrite(data,1,bytes,f)==bytes;
    if(fclose(f)) ok=0;
    return ok;
}
int main(int argc,char **argv)
{
    struct waffle_ramlog_entry entries[5];
    if(argc!=3) { fprintf(stderr,"Usage: %s manifest output-directory\n",argv[0]);return 2; }
    FILE *f=fopen(argv[1],"r");
    if(!f) return 2;
    int valid=waffle_ramlog_manifest(f,entries);
    fclose(f);
    if(!valid) { fprintf(stderr,"Invalid RAM log manifest; no USB commands sent\n");return 2; }
    ux_set_progname(argv[0]); ux_init();
    setvbuf(stderr,NULL,_IONBF,0);
    unsigned count=0;
    struct qdl_device_desc *devices=usb_list(&count);
    int eligible=count==1 && devices && devices[0].vid==0x05c6 && devices[0].pid==0x900e &&
        !strcmp(devices[0].serial,"1C62E9AA");
    free(devices);
    if(!eligible) { fprintf(stderr,"Expected this PJD110 in 900e; no USB commands sent\n");return 2; }
    if(mkdir(argv[2],0700)) { perror("output directory");return 2; }
    struct waffle_sahara_log_result result={0};
    struct context context={usb_init(),argv[2],&result,false};
    if(!context.usb) return 2;
    if(context.usb->open(context.usb,"1C62E9AA")) { free(context.usb);return 2; }
    const struct waffle_sahara_log_io io={&context,receive,transmit,save_page};
    int ok=waffle_sahara_logs(&io,entries,&result);
    context.usb->close(context.usb); free(context.usb);
    printf("{\"pages\":%u,\"reset_sent\":%u,\"reset_ack\":%u,\"stage\":\"%s\",\"read_complete\":%s}\n",
        result.pages,result.reset_sent,result.reset_ack,waffle_sahara_log_stage_name(result.stage),ok?"true":"false");
    return ok?0:1;
}
