# Brightness audit — OnePlus 12

Current MiniIOMobileFramebuffer has no brightness implementation. Its externalMethod default logs an unknown selector then returns success with zeroed outputs; success does not establish a panel update. inject.c brightness_fixes is unused and only bypasses ALS wait; it cannot control hardware.

Exact iOS16.5 IOMobileFramebuffer SwapSetBrightness at1af1c2148 dispatches object+6f0. Initializers install either1af1c41e0 (returns0 only) or1af1c4540 (uses brightness plugin atobject+b70, queues transaction value). Therefore no direct kernel selector can be inferred from this exported wrapper. Actual CoreBrightness BLControl findBacklight at1af03f1f8 and findDisplays at1af03f680 preserved for backend matching analysis. Do not invent public APIs/selector numbers.

Pinned native dsi_panel_update_backlight delegates to Oplus feature code. Actual path: globalHBM mapping, PWM switch, demura andTE coordination, byte swap when inverted_dbv, optional Iris pass-through, then mipi_dsi_dcs_set_display_brightness. DSI transmit requires command engine/clocks and inherited link state. Generic MMIO register writes or software framebuffer dimming do not implement this path.

Live DT has multipleAA545 variants and vtdr6130 default. P3A0005 normalmax3332/max4094, P1A0006 normalmax2047/max4095, bothinvertedDBV. Defaultpanel alone doesNOTqualifyselectedpanel. Android op_display/panel of_node points to display-primary parent, not selectedpanel. AndroidsysfsID/backlight/procbootconfig reads denied; adb root/su unavailable. dumpsysdisplay readableandpreserved1440x3168/120Hznativebaseline. No permission bypass, panel writes or power toggles done.

Next qualification: discover CoreBrightness display backend and chosenpanel from actualUEFIDisplayDxe configuration/protocol; read inherited DSIhost configuration and nativecommand path. Firstchange only bounded manualbrightness, currentlevel retained/restored, noHBM/AOD/autoALS untilnormalrange works. VSync TE survey andbrightness share display transport ownership; serialize writes.
