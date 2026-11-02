#include "mini.h"

int main(int argc, char **argv, char **envp)
{
 (void)argc; (void)argv; (void)envp;
 int console = open("/dev/console", O_RDWR, 0);
 if (console >= 0) { dup2(console, 0); dup2(console, 1); dup2(console, 2); }
 printf("waffle-audio-probe: PID1 ready; firmware-only test, no PCM playback\n");
 for (;;) { usleep(1000000); }
}
