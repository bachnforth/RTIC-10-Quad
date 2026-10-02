# Nearest waypoint ahead V2 — engineering handover

**Artifact:** [nearest_waypoint_ahead.lua](./nearest_waypoint_ahead.lua)  
**Target:** upstream ArduCopter `Copter-4.7.1`, quadrotor, Mission Planner SITL.  
**Status:** static/source reviewed and mocked; **no real SITL flight run**.

## V1 → V2 changelog

- Parses `MAV_CMD_DO_CHANGE_SPEED` (178) without breaking the geometric waypoint leg. NAV sequence numbers remain the original mission sequence numbers, including TAKEOFF and DO items.
- Validates speed type, magnitude, and unused fields. Copter 4.7.1 uses types **0 and 1** for horizontal speed in **m/s**; types 2 and 3 change climb/descent speed and are rejected. Accepted positive speeds are **1–20 m/s** for this SITL candidate. Speed **0** is a no-change command. Throttle field must be 0 or -1; param4 must be 0. Every other DO/CONDITION/NAV variant remains rejected.
- Reconstructs the last positive speed command while scanning. If that command is between the two WPs of the selected leg, V2 stages that DO sequence while the mission is stopped. ArduPilot then executes the DO before starting the destination NAV on AUTO resume. With consecutive speed DOs, V2 stages the **last positive** one; later zero-speed DOs have no effect. Earlier speed DOs in that block are skipped because their final speed state has been superseded.
- If a positive speed from an **earlier leg** persists into the selected leg, V2 **rejects the AUTO request**. The 4.7.1 Lua API cannot stage that historical speed command and an arbitrary later NAV command together. This is a deliberate functional limit, not silent loss of the desired speed.
- Adds GCS diagnostics for effective speed, speed source sequence, staged DO versus NAV, selected NAV sequence, and explicit speed-related rejections. No speed parameter is changed by the script.

## Source findings and ordering

`mission:set_current_cmd(index)` is bound to `AP_Mission::set_current_cmd`. While the mission is stopped, calling it with a DO sequence finds and stages the following NAV sequence. On AUTO entry, `ModeAuto::run()` calls `mission.start_or_resume()`; `AP_Mission::resume()` replays the staged DO and starts the NAV. In `advance_current_nav_cmd()`, the first DO is started before the NAV. Later consecutive DOs are started by `advance_current_do_cmd()` on subsequent mission updates, so they are not applied atomically before NAV. V2 stages the last positive speed DO in that block to establish the final horizontal speed before NAV starts; this skips the natural transient speeds from earlier DOs. [AP_Mission source](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Mission/AP_Mission.cpp), [Copter AUTO source](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/mode_auto.cpp), [Lua bindings](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Scripting/generator/description/bindings.desc).

For a mission DO_CHANGE_SPEED, Copter executes `wp_nav->set_speed_NE_ms(target_ms)` and stores the horizontal override if `target_ms > 0`; `target_ms == 0` does nothing. The mission item stores type in param1 and target m/s in param2; Copter's DO handler ignores throttle. Type 0 is labeled airspeed but Copter handles it identically to type 1 groundspeed for horizontal waypoint navigation. Later speed DOs execute normally after the selected NAV. [Copter DO handler](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/mode_auto.cpp), [mission encoding](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Mission/AP_Mission.cpp).

**Why V2 does not call `vehicle:set_desired_speed()` before AUTO:** the binding exists and takes m/s, but Copter dispatches it to the **current** flight mode. `ModeAuto::init()` then clears `desired_speed_override_ms` and reinitializes WPNav from the `WP_SPD` default. A pre-AUTO call therefore cannot establish AUTO's speed. Calling the setter immediately after `vehicle:set_mode(AUTO)` would set ModeAuto's override, but Lua runs in a separate scripting thread; the main flight loop can run between those calls. It cannot guarantee the speed is set before AUTO's first navigation action. [Copter dispatch](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/Copter.cpp), [AUTO initialization](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/mode_auto.cpp), [scripting thread](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AP_Scripting/AP_Scripting.cpp).

The renamed 4.7.1 default waypoint speed parameter is **`WP_SPD`** in **m/s** (older firmware used `WPNAV_SPEED`). Changing `WP_SPD` to mimic a historical DO would change a global default, affect controller reinitialization and possibly later mission behavior, and require carefully timed restoration. V2 does **not** make that substitution. [WPNav source](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/libraries/AC_WPNav/AC_WPNav.cpp).

### Example and unresolved requirement

For `seq 4 WP2; seq 5 DO_CHANGE_SPEED 5; seq 6 WP3`, a WP2→WP3 selection stages **seq 5**; the staged NAV is **seq 6**. Copter replays seq 5 before it starts NAV seq 6. If seq 5 is absent and the last positive speed was seq 3, selecting seq 6 is **rejected** because the speed from seq 3 would otherwise be lost when AUTO initializes. Thus V2 supports joining legs with a local speed DO and legs with no earlier positive speed DO, but it does **not** satisfy the requested arbitrary-leg persistence case. Full support would require a Copter source change exposing an atomic way to stage both NAV index and horizontal speed override for AUTO entry, or another native mission-entry API with equivalent guarantees.

## Geometry and safety retained

V2 retains finite-segment projection, closest interior leg, `NWA_MAXDIST`, `NWA_AMBIG`, `NWA_MINLEG`, 5 km maximum leg, dateline longitude normalization, latitude restriction, and rejection beyond route endpoints. DO speed items do not break a WP-to-WP segment. It requires an armed, likely-flying quadrotor with healthy AHRS and valid position; `MIS_RESTART=0`; and a stopped or complete mission. Direct AUTO entry never triggers selection. On AUTO→LOITER, Copter stops the running mission, so a later Scripting1 trigger can stage a new command when `NWA_ONCE=0`; the same speed-replay rules apply each time. [AUTO exit and entry](https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.1/ArduCopter/mode_auto.cpp).

No speed is changed during validation or staging. If the AUTO mode request fails, V2 attempts to restore the prior valid NAV index and reports the outcome. A prior index of 0 cannot be restored exactly through this binding; inspect the current mission item before another attempt. Mission edits during entry, script failure after entry, controller faults, terrain, altitude differences, and path obstacles are outside the geometric selector. It remains a SITL candidate.

## Exact Mission Planner SITL setup

1. Start **Simulation → Copter → Quad** with ArduCopter **4.7.1** if that exact build is available. Record the firmware version in Flight Data Messages. If Mission Planner downloads another version, check that branch's mission and speed source before trusting the result. [Mission Planner simulation](https://ardupilot.org/planner/docs/mission-planner-simulation.html).
2. Set `SCR_ENABLE=1`, `MIS_RESTART=0`, `RC7_OPTION=300`, `WP_SPD=6` m/s. Reboot SITL. Place [nearest_waypoint_ahead.lua](./nearest_waypoint_ahead.lua) in `Documents/Mission Planner/sitl/scripts`, then reboot. Confirm `NWA: loaded` and that `NWA_` parameters appear. [Scripting setup](https://ardupilot.org/dev/docs/common-lua-scripts.html).
3. Use these initial script parameters: `NWA_ENABLE=1`, `NWA_MAXDIST=100`, `NWA_START=1`, `NWA_END=0`, `NWA_MINLEG=2`, `NWA_AMBIG=1`, `NWA_DEBUG=1`, `NWA_ONCE=1`. RC7 must be an unused auxiliary channel. In **Flight Data → Servos/Relay**, command RC7 **1000 µs LOW** and verify it on the radio/status display. Move it to **2000 µs HIGH** only when ready to request selection; return it LOW before another trigger. [Flight Data controls](https://ardupilot.org/planner/docs/mission-planner-flight-data.html).
4. Upload this test mission in Flight Plan: home seq 0; TAKEOFF 20 m seq 1; WP1 seq 2 at 0 m north; DO_CHANGE_SPEED type 1, 8 m/s seq 3; WP2 seq 4 at 100 m; DO_CHANGE_SPEED type 1, 5 m/s seq 5; WP3 seq 6 at 200 m; DO_CHANGE_SPEED type 1, 10 m/s seq 7; WP4 seq 8 at 300 m; RTL seq 9. Use explicit coordinates and verify the uploaded sequence numbers on the vehicle.
5. Arm and take off **outside AUTO**. Position the aircraft in GUIDED using **Fly to here Alt**, or fly it manually with a joystick in LOITER. Stabilize halfway WP2→WP3 at about 20 m altitude, with RC7 LOW. Raise RC7 HIGH. Expect Messages reporting position, candidate `4->6`, `speed 5.0m/s from DO seq 5`, `stage DO seq 5 before NAV 6`, `selected NAV 6`, AUTO request, and scripted AUTO transition. Check current mission NAV seq 6 and travel toward WP3. Inspect the `.BIN` mission command and navigation logs to confirm the DO command executed before NAV motion and that steady travel reflects the 5 m/s target (actual groundspeed may differ during acceleration or wind).
6. For another test cycle, return to LOITER before the next trigger and set RC7 LOW. With `NWA_ONCE=1`, a second HIGH trigger should reject. Set `NWA_ONCE=0`, move near the WP3→WP4 midpoint, trigger again, and expect candidate `6->8`, replay DO seq 7, NAV seq 8, and 10 m/s intended speed. Confirm AUTO→LOITER stopped the mission before retriggering.

## V2 test matrix

Repeat from a known mission and position; keep RC7 LOW until triggering. Check Messages, current NAV sequence, mode, and `.BIN` log for every case.

| Case | SITL change and expected outcome |
|---|---|
| Speed before every WP | Use the mission above. WP2→WP3 selects NAV 6 via DO 5; WP3→WP4 selects NAV 8 via DO 7. |
| Speed persists across WPs | Keep one DO 6 m/s after WP1, then WP2, WP3, WP4. Enter on WP2→WP3: **reject**, citing historical speed. Fly the mission normally separately to inspect native persistence. |
| No prior speed | Remove all DOs. Selection stages NAV directly and reports `WP_SPD=6m/s`. |
| Speed 0 | Use one 0 m/s DO before the selected NAV. With no earlier positive DO, stage NAV and use `WP_SPD`; with an earlier positive DO on another leg, **reject**. |
| Negative / high speed | Set param2 to -1 or 25 m/s: **reject**. Speeds below 1 m/s also reject. |
| Type 2 / 3 | Set param1 to climb/descent type: **reject**. Types 0 and 1 are accepted as horizontal Copter speed. |
| Consecutive DO speeds | Insert 5 then 7 m/s between the selected WPs: stage the **last positive** DO and select the following NAV. Insert 5 then 0: stage 5; 0 remains no change. |
| Direct AUTO | Use Mission Planner's AUTO button rather than RC7: script logs direct entry and makes no selection. Copter's ordinary mission behavior applies. |
| Repeat entry | AUTO→LOITER, manually reposition, RC7 LOW→HIGH. `NWA_ONCE=1` rejects; `NWA_ONCE=0` recalculates under the same speed rules. Disarm/rearm resets the once latch. |
| Mode request failure | The mock test forces `vehicle:set_mode()` to fail after staging and checks prior-index restoration. There is no deterministic safe Mission Planner control for that exact fault; a real SITL fault-injection test remains open. |
| Crossing / parallel | Place aircraft at a crossing or within `NWA_AMBIG` of two parallel legs: **reject**. |
| Distance limit | Place aircraft >100 m cross-track with an interior projection: **reject**. |
| Other commands | Insert camera/ROI DO, CONDITION, DO_JUMP, spline, loiter, etc.: **reject**. |
| Terminal item | Test final LAND and final RTL separately; both parse. |

**Verification performed:** Lua 5.3 syntax parse and 27 mocked scenarios covering the selector and staging decisions, including repeated entry and mode failure rollback. Mocks do **not** execute ArduCopter's C++ mission engine or measure AUTO speed. No actual SITL result is claimed here. The first real SITL run must confirm the DO-before-NAV ordering and speed on the exact firmware build.
