# Bench configuration patch

This patch is for the confirmed ArduCopter 4.7.1 quad with a standard 4S 5200 mAh LiPo and a three-position mode switch on RC channel 7.

## Changes in `bench_autonomous_setup.param`

- Corrects battery capacity from 3300 mAh to 5200 mAh.
- Uses voltage-only battery protection: low at 14.4 V for 10 seconds and critical at 14.0 V, with LAND for both events.
- Keeps capacity-based triggers disabled because current consumption is not measured.
- Assigns the observed three-position CH7 switch:
  - Low (~999): Stabilize (`FLTMODE1=0`)
  - Middle (~1503): Loiter (`FLTMODE4=5`)
  - High (~2000): Auto (`FLTMODE6=3`)

## Deliberately unchanged

- `ARMING_MAGTHRESH=200` and all EKF/compass settings.
- Motor/ESC protocol and output parameters.
- Radio failsafe settings.
- Geofence and RTL parameters, which require the actual outdoor test site and verified GPS/Home.
- Waypoint mission, which requires a valid outdoor GPS position.

## Mission Planner application procedure

1. Keep propellers removed and the vehicle disarmed.
2. Open **CONFIG > Full Parameter Tree**.
3. Select **Load from file** and choose `bench_autonomous_setup.param`.
4. Review the comparison: only the 12 parameters listed in the file should change.
5. Select **Write Params**, then reboot the flight controller.
6. Reconnect and use **Refresh Params** to verify the saved values.
7. On the DATA screen, move CH7 through all three positions and verify Stabilize, Loiter, and Auto in that order. Do not arm.

The voltage thresholds are conservative starting points for a short initial flight and may need adjustment after reviewing logged under-load voltage sag. They are not a substitute for a charged, healthy pack.
