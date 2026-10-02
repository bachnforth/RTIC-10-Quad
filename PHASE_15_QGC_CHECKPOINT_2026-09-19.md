# Phase 15 QGroundControl checkpoint — 2026-09-19

## Completed indoors

- Installed official QGroundControl `5.1.4` for Windows x86-64.
- Connected to the Lumenier LUX F765 flight controller on `COM9` over USB.
- Identified ArduCopter `4.7.1`, quad frame, disarmed state, and live MAVLink telemetry.
- Confirmed indoor GPS condition: no fix and zero satellites.
- Confirmed flight-battery sensing when connected at approximately `15.15 V`; USB-only voltage was approximately `1.35 V` when the flight battery was unplugged.
- Read back `SERVO9_FUNCTION = 145` (`RCIN6Scaled`) with `1100/1500/1900` endpoints.
- Read back `SERVO10_FUNCTION = 148` (`RCIN9Scaled`) with `1100/1500/1900` endpoints.
- Confirmed Mission Planner readback of `SERVO_RC_FS_MSK = 288`.
- Confirmed flight-mode channel `7` with positions: Loiter, Land, Stabilize, Stabilize, Land, Auto.
- Confirmed Channel 8 option `ArmDisarm`; Channels 6 and 9 show no RC option because their signals are used by SERVO9/SERVO10 scaled passthrough.
- Recorded QGC safety summary: throttle failsafe enabled with RTL, low/critical battery action Land, arming checks enabled, geofence disabled, RTL minimum altitude `50 m`, battery monitor Analog Voltage Only, capacity `5200 mAh`.

## Local mission artifact

- Created `Camp_Mackall_QGC_TEST_5m.plan` for ArduPilot multirotor planning.
- Mission order: Takeoff to `5 m` relative, three close waypoints with `2 s` holds and `2 m` acceptance radii, then RTL.
- Maximum horizontal distance from Planned Home: `7.06 m`.
- QGC multirotor estimate speed: `3 m/s`; actual speed remains governed by the aircraft's ArduPilot navigation parameters.
- JSON structure and command order validated locally.
- Copied the plan to `C:\Users\ebach\Documents\QGroundControl\Camp_Mackall_QGC_TEST_5m.plan`.
- Opened QGC using the local plan path, then closed QGC without selecting Upload.
- A read-only MAVLink query found only the sequence-zero Home placeholder on the controller; no executable mission items were stored.

## Remaining outdoor work

- Obtain a clean 3D GPS fix and verify the actual Home position.
- Confirm the physical route and obstacle clearance at the authorized launch site.
- Recheck current airspace, NOTAMs, weather, and permissions immediately before flight.
- Review the local plan in QGC before any separately authorized upload.
- Perform only props-off control and safety checks until the outdoor preflight stage is deliberately started.

The Camp Mackall coordinates are beside Mackall Army Airfield (KHFF), which has active military/UAS operations and restricted access. The saved plan is an offline planning exercise and is not flight authorization.
