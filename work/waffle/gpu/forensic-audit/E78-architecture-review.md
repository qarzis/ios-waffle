# E78 pressure and presentation review

Three pressure approaches have now been exhausted: cache cleanup under an outer lock deadlocked; corrected unlocked cleanup continued until all 128 MiB were live; a 192 MiB backing budget survived E77 but exhausted during E78 interactive UI. No further budget increase is justified. GPU phase ended at 9,787 completions, 8,890 lifetime BOs; the registry reported 201,326,592 live bytes and rejected the next 16 KiB before mutation. backboardd then exited with SIGSEGV; full context close passed. This does not prove a leak or prove the driver is stable.

User reports stripes during GPU rendering; the saved native screen60 capture shows horizontal discontinuities in app-switcher cards. A scanout capture spans time, so the capture alone cannot distinguish output corruption from concurrent presentation/capture. User observation establishes visible artifacts; their cause is not yet identified. CPU-phase screen120 shows Settings without those discontinuities.

On resume, audit native Mesa live BO references/cache ownership against submitted IOSurfaces, then determine whether the application working set or retained ownership explains the physical cap. Separately trace frame completion, CPU readback and display publication ownership to test whether one buffer is presented while it is changing. Keep these hypotheses separate; allocation failure does not establish the cause of stripes. Preserve all guards and original runner results.

Current E79 changes only exact observed wallpaper metadata matching; it is a short functional wallpaper test, not another GPU pressure fix. After wallpaper completion, stop and publish per user request.
