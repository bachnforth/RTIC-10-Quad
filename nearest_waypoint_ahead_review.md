# Nearest waypoint ahead: engineering review for SITL

## Result and scope

Revised script: [nearest_waypoint_ahead.lua](./nearest_waypoint_ahead.lua). Reviewed against upstream **Copter-4.7.1** source and current ArduPilot documentation. This is a controlled Mission Planner SITL candidate. I did not run an ArduCopter SITL flight or validate the custom Lumenier firmware binary. The Lua passed a 5.3 syntax parse and 11 mocked Lua runtime scenarios (straight leg, distance limit, unsupported DO, unhealthy AHRS, route endpoint, direct AUTO, once per arm, repeat, rearm, crossing, overlapping legs).

## Critical findings

1. **AUTO entry race.** Copter's `ModeAuto::run()` calls `mission.start_or_resume()` once the origin exists. Lua notices a direct mode transition only afterward, so the old script could allow the existing command to run briefly. The revised script uses RC Scripting1 as the entry trigger, calls `set_current_cmd()` while outside AUTO, then calls `vehicle:set_mode(3)`. Direct AUTO entry is logged and left alone. See [ModeAuto::run](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/mode_auto.cpp).
2. **`set_current_cmd()` is a jump, not a waypoint lookup.** While stopped, it stages a NAV command for resume. While running, it immediately advances the mission; it clears active DO state and waypoint history. On a complete mission, it resets jump tracking. A successful result does not mean preceding DO/CONDITION items ran. See [AP_Mission::set_current_cmd](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Mission/AP_Mission.cpp) and [binding declarations](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Scripting/generator/description/bindings.desc).
3. **False legs and skipped actions.** The old script connected successive command-16 items even if TAKEOFF, spline, loiter, landing, jump, DO, or CONDITION commands intervened. The revision accepts only an optional first TAKEOFF, at least two explicit ordinary WAYPOINTs, and an optional final LAND or RTL. Any other item rejects the entire selection. In particular, speed, camera, ROI, CONDITION, DO_JUMP, DO_LAND_START, return-path, and spline missions need another design.
4. **Ambiguity and endpoints.** The old first-minimum rule silently chose one branch at crossings/overlaps. The revision rejects near-tied segments using `NWA_AMBIG`. It only considers projections on the finite segment; a position beyond the final leg or before the first leg will not select an endpoint solely because it is geographically nearest. A point extremely close to a junction can be rejected; this is intentional.
5. **Geometry and position.** The lat/lon-to-N/E approximation is adequate for local missions with legs at most 5 km and latitude below 80 degrees. Longitude differences are wrapped across the dateline. The script checks arming, likely-flying state, AHRS health, non-nil EKF position, finite valid coordinates, and a positive distance limit. It uses horizontal geometry only; waypoint altitude and terrain are not evaluated.

## Behavioral limits

- The script only permits `MAV_TYPE_QUADROTOR` and assumes Copter AUTO mode **3**. It has not been checked against older firmware or other Copter frame classes.
- `MIS_RESTART` must be **0**. With `MIS_RESTART=1`, Copter would restart at the first command after a staged selection. Copter's AUTO mode also checks for a takeoff command when entering AUTO from the landed state; this script requires the aircraft already flying. See [Copter AUTO docs](https://ardupilot.org/copter/docs/auto-mode.html).
- `mission:num_commands()` includes home at sequence **0**. The selected number is the mission sequence number, not a count of NAV waypoints. An initial TAKEOFF shifts WP1 to sequence 2.
- The selection may skip ordinary WPs and the initial TAKEOFF. It never executes skipped commands. Waypoint arrival settings, altitude, terrain, fences, and collision avoidance remain Copter's responsibility. A flight path from the current position to the selected waypoint still needs review in the Plan map.
- After `set_current_cmd()` succeeds, `vehicle:set_mode()` can theoretically fail. The script attempts to restore a previously valid NAV index and reports an error; if the previous index was 0 or the mission changed concurrently, exact restoration is unavailable through this binding. Verify Mission Planner's current mission item before retrying.
- Editing the mission during the brief scan/stage interval is unsupported. The script checks mission count and running state but cannot atomically snapshot all mission content. Do not upload/edit a mission during entry.
- Parameter-table key **81** must be unique across scripts. A collision prevents this script from loading. The 4.7.1 binding provides `gcs:frame_type()`, `vehicle:get_mode()/set_mode()/get_likely_flying()`, `ahrs:get_position()/healthy()`, `mission:get_item()/num_commands()/state()/get_current_nav_index()/set_current_cmd()`, and `rc:get_aux_cached(300)`; the version on the target aircraft still needs confirmation.

## Initial parameters

| Parameter | Initial value | Meaning |
|---|---:|---|
| `SCR_ENABLE` | 1 | Enable Lua; reboot SITL |
| `RC7_OPTION` | 300 | RC7 is Scripting1 entry switch; use a free auxiliary channel if RC7 is occupied |
| `MIS_RESTART` | 0 | Resume staged command |
| `NWA_ENABLE` | 1 | Enable selection |
| `NWA_MAXDIST` | 100 m | Reject if farther than this; **0 is invalid** |
| `NWA_START` | 1 | Earliest mission sequence used as leg start |
| `NWA_END` | 0 | 0 means mission end; otherwise last allowed leg destination |
| `NWA_MINLEG` | 2 m | Reject a mission with shorter consecutive WP leg |
| `NWA_AMBIG` | 1 m | Reject if runner-up segment is within this distance of best |
| `NWA_DEBUG` | 1 | Candidate and switch diagnostics |
| `NWA_ONCE` | 1 | One successful staged selection per arming cycle; use 0 for each trigger |

The script rejects invalid parameter values rather than silently clamping them. Keep Scripting1 LOW until ready; a LOW-to-HIGH transition initiates selection and the AUTO request. Return it LOW before another attempt.

## Mission Planner SITL procedure

1. Open **Simulation**, select **Copter / Quad**, and start a stable Copter 4.7.1 SITL build if offered. Record the actual SITL firmware version from Messages. Mission Planner's simulator may download a different branch; if so, repeat the source review for that exact version. [Simulation instructions](https://ardupilot.org/planner/docs/mission-planner-simulation.html).
2. In **Config > Full Parameter Tree**, set `SCR_ENABLE=1`, `MIS_RESTART=0`, and `RC7_OPTION=300`. Reboot SITL. Put [nearest_waypoint_ahead.lua](./nearest_waypoint_ahead.lua) in the SITL `scripts` directory (normally `Documents/Mission Planner/sitl/scripts`), then reboot again. Confirm **“NWA: loaded”** in Flight Data **Messages**, that the `NWA_` parameters exist, and no scripting error appears. [Scripting setup](https://ardupilot.org/dev/docs/common-lua-scripts.html).
3. In **Flight Data > Servos/Relay**, set/override RC7 to **1000 µs (LOW)** and keep it there. Verify the channel response on the radio/status view; do not use the RC flight-mode channel for Scripting1. Mission Planner documents RC 5–14 override controls in [Flight Data](https://ardupilot.org/planner/docs/mission-planner-flight-data.html).
4. In **Flight Plan**, upload a simple mission: home sequence 0; TAKEOFF 20 m sequence 1; five ordinary WPs on a straight line at roughly 0, 100, 200, 300, 400 m from one another (sequences 2–6); RTL sequence 7. Check each WP has explicit coordinates. The intended test point is halfway from WP3 (sequence 4) to WP4 (sequence 5). Save the mission and verify it on the vehicle.
5. Arm in GUIDED or another suitable non-AUTO mode, take off to about 20 m, then position the aircraft near that midpoint using **Fly to here Alt** or a joystick. Pause in LOITER for a stable position. For a true manual-flight rehearsal, use the joystick in LOITER to reach the same point. Keep a path to switch back to LOITER/RTL.
6. Raise RC7 to **2000 µs (HIGH)**. Expect `NWA: position`, `candidate 4->5`, `selected cmd 5`, `AUTO requested`, and `AUTO transition: scripted entry`. In Flight Data, confirm AUTO, current mission command **5**, motion toward WP4, then continuation to WP5 and RTL. Return RC7 LOW after triggering.
7. Repeat in a fresh arming cycle with the aircraft about **150 m lateral** to the route, remaining between two WPs along-track. Expect a distance-limit rejection, no `set_current_cmd`, and no AUTO request. Test direct AUTO separately: it should log a direct transition and not select a waypoint; Copter's ordinary mission behavior then applies, so be ready to retake control.
8. Test missions with unequal WP spacing, a crossing, and parallel return leg. At a crossing or sufficiently close parallel legs expect `ambig` rejection. Test just before WP4 (more than `NWA_AMBIG` from the junction) for WP4 selection; at the exact junction or just beyond the final leg expect a rejection or selection of a genuinely nearer interior leg, never an automatic nearest-endpoint fallback.
9. Upload a TAKEOFF/WPs/DO_CHANGE_SPEED/camera/LAND mission and confirm an `unsupported mission cmd` rejection. Also try spline, loiter, DO_JUMP, and CONDITION commands separately. Repeat AUTO→LOITER→Scripting1 HIGH with `NWA_ONCE=1` (reject second selection), then `NWA_ONCE=0` (recalculate). Disarm/rearm to verify the latch resets.
10. In a separate SITL run, disable simulated GPS with the version's `SIM_GPS1_ENABLE=0` or `SIM_GPS_DISABLE=1`, wait until AHRS/position is unhealthy, and trigger Scripting1. Expect a rejection and no AUTO request. Restore GPS after the test. GPS loss can itself cause a failsafe, so observe the resulting vehicle mode independently.

Save the Mission Planner Messages and `.BIN` log for each run. Verify `MODE`, `CMD`/mission-current events, selected sequence, and any failsafe. Only a successful exact-version SITL run can establish runtime compatibility; static review and mocked Lua tests do not.
