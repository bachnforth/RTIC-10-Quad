# ArduCopter 4.7.1 SITL validation — nearest_waypoint_ahead V3.2

## Result

**PASS for the requested 4→6 rejoin test.** V3.2 selected mission NAV sequence 6, reconstructed the persistent 5.0 m/s horizontal speed from `DO_CHANGE_SPEED` sequence 5, made NAV 6 active, and applied 5.0 m/s after AUTO initialized. Actual EKF horizontal velocity settled near 5 m/s while NAV 6 was still active. Mission sequence 7 then executed at the NAV 6 completion boundary, and actual velocity rose toward 10 m/s on NAV 8.

This is one controlled SITL result. It does not make the script flight ready.

## Test identity and controls

- Autopilot log identity: `ArduCopter V4.7.1 (4776a3fb)` from the BIN `VER` record.
- Simulator: Mission Planner Windows SITL executable, quad plus frame, speedup 1.
- Script under test: `nearest_waypoint_ahead_v3_2.lua`.
- Source and installed script SHA-256: `08FB26474C79008156E6DC3085D8A5EB3E4F887FF77614AFB59CE140E539553E`.
- Script source was copied byte for byte into the SITL scripts directory. It was not edited.
- BIN SHA-256: `DCE0AFE490DF87EFCB00C6701A50AB2BD1B15129C738C617F81E35746FC66C68`.
- Parameters recorded in the BIN: `SCR_ENABLE=1`, `MIS_RESTART=0`, `RC7_OPTION=300`, `WP_SPD=6`, `NWA_ENABLE=1`, `NWA_MAXDIST=100`, `NWA_MINREM=20`, `NWA_DEBUG=1`, `NWA_ONCE=1`.
- Uploaded mission command IDs were verified as `16,22,16,178,16,178,16,178,16,20` for sequences 0 through 9.
- Mission records verify sequence 5 is `MAV_CMD_DO_CHANGE_SPEED` (`178`) with horizontal type 1 and speed 5.0 m/s; sequence 7 is the same command with speed 10.0 m/s.

UTC below is reconstructed from the BIN `RTC` records. The monotonic `TimeUS`/boot time is the authoritative correlation key.

## Event evidence

| UTC | Boot time | BIN or script evidence |
|---|---:|---|
| 00:01:01.023Z | 211.187158 s | Scripting1 entry switch HIGH |
| 00:01:01.027Z | 211.190490 s | Position `35.0495415,-79.4901810` |
| 00:01:01.038Z | 211.201319 s | Candidate leg `4→6`, cross track 4.0 m, fraction 0.54, remaining 51.2 m |
| 00:01:01.038Z | 211.202152 s | Selected NAV 6 and reconstructed `5.0m/s from DO seq 5` |
| 00:01:01.040Z | 211.203818 s | NAV 6 staged |
| 00:01:01.041Z | 211.204651 s | `MISE`: sequence 6, command 16 (`NAV_WAYPOINT`); MODE changes to AUTO |
| 00:01:01.042Z | 211.205484 s | `AUTO entered`; `speed applied 5.0m/s` |
| 00:01:01.141Z | 211.304611 s | `NAV 6 confirmed active` and scripted entry complete |
| 00:01:13.566Z | 223.729639 s | NAV 6 reached; `MISE`: sequence 7, command 178, speed 10.0 m/s |
| 00:01:13.566Z | 223.729639 s | Same scheduler instant: `MISE` sequence 8, command 16; NAV 8 begins |
| 00:01:31.643Z | 241.806572 s | Test capture ends; mode changes from AUTO to LOITER |

`MISE` is the DataFlash mission execution record. It establishes when sequence 7 executed more precisely than the later MAVLink `MISSION_CURRENT` observation.

## Velocity evidence

Horizontal velocity is calculated as `sqrt(XKF1.VN² + XKF1.VE²)`. The CSV also contains `GPS.Spd` and these position-controller magnitudes:

- desired: `sqrt(PSCN.DVN² + PSCE.DVE²)`
- target: `sqrt(PSCN.TVN² + PSCE.TVE²)`
- controller actual: `sqrt(PSCN.VN² + PSCE.VE²)`

| UTC | Mission seq | EKF horizontal velocity | GPS speed | PSC desired | PSC target |
|---|---:|---:|---:|---:|---:|
| 00:01:01.136Z | 6 | 0.027 m/s | 0.002 | 0.000 | 0.027 |
| 00:01:05.036Z | 6 | 4.507 m/s | 4.487 | 4.941 | 4.983 |
| 00:01:07.036Z | 6 | 5.650 m/s | 5.708 | 5.975 | 6.099 |
| 00:01:08.036Z | 6 | 5.241 m/s | 5.320 | 5.417 | 5.438 |
| 00:01:10.036Z | 6 | 5.177 m/s | 5.192 | 5.261 | 5.184 |
| 00:01:13.536Z | 6 | 4.972 m/s | 4.992 | 5.004 | 4.936 |
| 00:01:13.636Z | 8 | 4.963 m/s | 4.972 | 4.998 | 4.929 |
| 00:01:16.936Z | 8 | 5.257 m/s | 5.169 | 5.379 | 5.397 |
| 00:01:19.636Z | 8 | 9.055 m/s | 9.051 | 9.572 | 10.226 |
| 00:01:20.436Z | 8 | 9.521 m/s | 9.557 | 9.988 | 10.824 |
| 00:01:25.036Z | 8 | 9.868 m/s | 9.870 | 10.000 | 10.004 |
| 00:01:31.036Z | 8 | 9.987 m/s | 10.005 | 10.000 | 10.007 |

The first EKF velocity record after the speed-application message is at boot 211.239637 s: `VN=-0.0175`, `VE=0.0200`, horizontal velocity 0.0266 m/s. The supplied telemetry CSV continues at 10 Hz until AUTO was exited.

### NAV 6 settling result

- Time from speed application to NAV 6 completion: **12.524 s**.
- Peak EKF horizontal velocity during the acceleration transient: **5.650 m/s**.
- Using a stated settling band of 5.0 ± 0.25 m/s, velocity entered and remained in band at boot **218.139376 s** (`00:01:07.976Z`).
- This was **5.590 s before NAV 6 completed**.
- Within that settled interval, EKF horizontal velocity mean/min/max was **5.129 / 4.972 / 5.241 m/s**.

Therefore the requested question “does it settle near 5 m/s before NAV 6 completes?” is **yes**.

### Sequence 7 and NAV 8 result

- Sequence 7 executed at boot **223.729639 s** (`00:01:13.566Z`), exactly when the mission engine logged sequence 8 as the next NAV command.
- PSC desired horizontal velocity first exceeded 5.25 m/s at boot **226.939188 s**.
- Actual EKF horizontal velocity first exceeded 5.25 m/s at boot **227.039148 s**.
- PSC desired horizontal velocity first reached 9.5 m/s at boot **229.739734 s**.
- Actual EKF horizontal velocity first reached 9.5 m/s at boot **230.539414 s**.
- Mean actual EKF horizontal velocity over the final five captured seconds of NAV 8 was **9.968 m/s**.

The roughly 3.2 s interval between executing sequence 7 and rising above 5.25 m/s is a smooth navigation acceleration transition, not delayed mission-command execution: `MISE` proves the command executed at 223.729639 s, while the PSC desired-velocity trace then ramps upward.

## Test notes

- The aircraft was airborne in GUIDED at 20 m near the midpoint of the 4→6 leg before the accepted Scripting1 transition.
- The first harness RC override used a MAVLink source system that ArduCopter did not accept as the configured GCS. A source-system-255 connection supplied the actual LOW→HIGH transition later. This caused an extra hover period but did not alter the mission, script, or measured AUTO segment.
- The requested capture was complete before the harness attempted to stop the vehicle. The later harness disarm timeout occurred after AUTO was exited and does not affect the NAV 6 or NAV 8 evidence.
- This logging configuration has no dedicated scalar WPNav speed-limit field. The script status text proves the setter call occurred; the downstream PSC desired/target velocity and EKF/GPS actual velocity fields show its navigation effect.
