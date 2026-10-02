# Show RN08 on the quad's OSD

Applied to the connected ArduPilot flight controller on 2026-09-16. MAVFTP download verified that `/callsign.txt` contains `RN08`; the three OSD parameters were read back after a reboot. Visual confirmation in the goggles or monitor remains to be checked.

Checked again on 2026-09-21 after RN08 was not visible during flight. The three OSD parameters had persisted, but `/callsign.txt` was missing from the SD card. The file was uploaded again and successfully read back after reboot as `RN08`. The live DisplayPort configuration was also confirmed: `OSD_TYPE2=5`, `SERIAL6_PROTOCOL=42`, and `SERIAL6_BAUD=115`.

The ArduPilot callsign panel reads its text from `callsign.txt` in the root of the flight controller's microSD card. Copy the adjacent `callsign.txt` file to that location (or upload it with MAVFTP in Mission Planner). It must contain `RN08` in capital letters.

With the flight controller connected and disarmed, load `params/RN08_OSD.param` in Mission Planner, write the three parameters, then reboot the flight controller. They enable the callsign on OSD screen 1 at column 1, row 4, below the current satellite count. You can also set these three values manually in Mission Planner's full parameter list.

Power the video system and check the OSD in the goggles or monitor. If `RN08` overlaps another field, adjust `OSD1_CALLSIGN_X` and `OSD1_CALLSIGN_Y` in Mission Planner. Keep the original full parameter backup in `params/` unchanged.
