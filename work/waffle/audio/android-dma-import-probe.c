/* Android-only diagnostic: own one4KiB DMA-heap buffer, native audio import
 * then unmap. No DSP command, HYP assignment, PCM, mixer or amplifier API. */
typedef unsigned long u64;
static long call(long n,long a,long b,long c,long d){register long x8 __asm__("x8")=n;register long x0 __asm__("x0")=a;register long x1 __asm__("x1")=b;register long x2 __asm__("x2")=c;register long x3 __asm__("x3")=d;__asm__ volatile("svc 0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2),"r"(x3):"memory");return x0;}
static void report(const char *s,long v){unsigned n=0;while(s[n])n++;call(64,1,(long)s,n,0);char h[19]="0000000000000000\n";for(int i=15;i>=0;i--){h[i]="0123456789abcdef"[(u64)v&15];v=(u64)v>>4;}call(64,1,(long)h,17,0);}
void _start(void){long code=1;long heap=call(56,-100,(long)"/dev/dma_heap/system",2|0x80000,0),audio=-1,fd=-1;report("heap=",heap);if(heap<0)goto done;
 struct {u64 len;unsigned fd,flags;u64 heap_flags;} allocation={4096,0,2|0x80000,0};
 long ret=call(29,heap,0xc0184800,(long)&allocation,0);report("allocate=",ret);if(ret<0)goto done;fd=allocation.fd;
 audio=call(56,-100,(long)"/dev/msm_audio_ion",2|0x80000,0);report("audio=",audio);if(audio<0)goto done;
 ret=call(29,audio,0x40046161,fd,0);report("audio_import=",ret);if(ret<0)goto done;
 ret=call(29,audio,0x40046162,fd,0);report("audio_unmap=",ret);code=ret<0?2:0;
 done:if(audio>=0)call(57,audio,0,0,0);if(fd>=0)call(57,fd,0,0,0);if(heap>=0)call(57,heap,0,0,0);call(93,code,0,0,0);for(;;);}
