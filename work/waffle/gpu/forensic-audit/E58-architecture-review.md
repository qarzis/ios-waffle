# E58 sustained UI review before addressing observed VA fragmentation

The240-second UI window completed16,351 contiguous, verified GPU completions and four HFI tag wraps. Full parent stop passed,2,682 BOs reclaimed early and1,697 after detach (4,379 total). No crash before plannedstop was observed. Native GOP120 captured Sileo with the iOS notificationpermissiondialog before anyfallback. Original runner1 remains: rolling finalconsole lost startupmarkers; rawjournal and early snapshots preserve component evidence. Android independently boot_completed1. This establishes a bounded sustained compositor run, not indefinite driver reliability or a measured FPS.

## Current first measurable limitation

Complete1840-live-BO state at kernel773 matches117,080,064B resident,1432 retired/no retainedbacking,3272 totalissued. Physicalfree17,137,664B; largestvacantVAhole2,605,056B <3,145,728B request. Other preservedrefusals similarly have26-29MiB free but maximum2.7-3.5MiB holes for3.5/5MiB requests. Hardware continuedafterthese refusals; do notcallthis an observed GPUcrash. Per-event firstseenconsole ordering was inconsistentatoneinterleaving; reconstructing state separatelyateachrefusal exactlymatchedcdevlivecounts/bytes. Do notfabricate totalordering.

H1selected: one128MiB bound currentlyserves both residentphysicalbudget andcontiguousGPUVAplacement, allowingvirtualfragmentation toreject otherwise affordableobjects. Candidate separates them: retain128MiB physicalbudget, expandVAwindowonlyto256MiB; TABLE160 coversmax154tables including25bootstrap. Model exactliveaddresses old128refuses3MiB/new256accepts; livePA/APneighborsunaltered, fullvirtualspan65536PTEs mappedwithsyntheticPAs, owner/protectedstructsfit16KiB. This is a boundedtest, not proof256MiBcanneverfragment. No physicalheap/perBO/record/job/window growth.

H2: physicalIOBufferallocationfailure notprimary attheseobservedstates: noVAholefitsbeforeallocationcall. Nophysicalbudgetincrease now.

H3: later metadatahandles caneventuallyreach8192 issuedobjects despitefewerresidentBOs. Notyetobserved(limitlast4379); monotonicrecordscurrentboundeddiagnosticgapmustbeaddressedbeforeindefinitequalification. Needgenerationhandles/stale-handleprotection+registrytombstonereuse model, notblindlyincrease8192.

Timer240processstop and300kernelreturn are still deliberatetestlimits. Persistentbootrequires explicitreviewofthecurrentloaderpolicy andnormalrootconfiguration, plus a controlledrecoverypath; no claimthatremovingUItimeralonecreatesindefinitestableGPU. FPSoptimizationrequested: firstmeasureknownscene/readback/submit/loggercost, retainverifiedreadback/fencechecks duringhardwarebringup, thenindependentlycomparechanges. MetalportafterGPUbaseline;259fakeGPUhosttestspassed withpinnedfixtures, A750hardware/compiler/transportadaptationstillpending.
