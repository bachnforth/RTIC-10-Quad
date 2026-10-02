# Phase 15 QGroundControl live audit — 2026-09-20

## Scope

This was a read-only review over a filtered MAVLink relay. Parameter requests and mission downloads were permitted. Parameter writes, mission uploads, flight-mode changes, arming, manual control, and actuator commands were blocked.

The aircraft remained disarmed. No calibration or persistent configuration change was performed.

## Live state

- Battery voltage: approximately `14.32 V`.
- Battery current: unavailable because the configured monitor is voltage-only.
- GPS: 3D fix, `16` satellites, HDOP approximately `0.74`.
- Magnetic field: approximately `1464 mG`, above the reported pre-arm maximum of `875 mG`.
- Magnetic field warning remains unresolved because the aircraft could not be moved away from the current bench environment.

## Confirmed configuration

- Arming checks: enabled (`ARMING_SKIPCHK = 0`).
- Primary estimator: EKF3 (`AHRS_EKF_TYPE = 3`, `EK3_ENABLE = 1`).
- GPS1: enabled with automatic configuration; GPS2 disabled.
- Primary compass: one external compass, device ID `855297`, orientation `0`.
- Compass offsets: X `-76.44`, Y `48.30`, Z `-45.79` mG.
- Flight-mode channel: Channel 7.
- Flight modes: Loiter, Land, Stabilize, Stabilize, Land, Auto.
- Channel 8 option: Arm/Disarm (`153`).
- SERVO9: RC input 6 scaled (`145`), endpoints `1100/1500/1900`.
- SERVO10: RC input 9 scaled (`148`), endpoints `1100/1500/1900`.
- Servo receiver-failsafe mask: `288`.
- Throttle failsafe: enabled, PWM threshold `975`.
- RTL altitude: `50 m`; RTL loiter time: `5 seconds`; final altitude `0 m` means land at Home.
- Waypoint speed: `3 m/s`; radius `2 m`; climb `2.5 m/s`; descent `1.5 m/s`.

## Items for later review

- Battery monitor is Analog Voltage Only (`BATT_MONITOR = 3`) with capacity `5200 mAh`.
- Critical voltage is `14.0 V` and its action is Land.
- Low-battery action is Land, but both low-voltage and low-mAh thresholds are zero. This provides no earlier low-battery threshold before the critical voltage condition.
- GCS failsafe is disabled (`FS_GCS_ENABLE = 0`). RC/throttle failsafe remains enabled.
- Geofence is disabled and contains no polygon points (`FENCE_ENABLE = 0`, `FENCE_TOTAL = 0`).
- The controller reports only the sequence-zero Home placeholder (`MIS_TOTAL = 1`), so it has no executable mission.
- A September 18 parameter backup recorded `FENCE_TOTAL = 8` and `MIS_TOTAL = 14`. Those items are not present on the controller now. No mission or fence was cleared during this audit.

## Saved snapshot

- `params/LUXF765_QGC_READONLY_2026-09-20.json` — parameter values plus MAVLink type and index metadata.
- `params/LUXF765_QGC_READONLY_2026-09-20.param` — sorted Mission Planner-compatible name/value snapshot.

The live `.param` snapshot includes current telemetry-stream rate values, which can reflect the active QGC link. It is intended for comparison and recovery reference, not automatic loading.

## Deferred blocker

Do not arm or calibrate the compass in the present location. When physical access is available, repeat the magnetic-field reading with the flight battery unplugged and the aircraft separated from the computer, phone, metal furniture, speakers, tools, and power cables. If the field remains excessive in a clean outdoor location, inspect compass placement, orientation, and power-wire routing before considering recalibration.
