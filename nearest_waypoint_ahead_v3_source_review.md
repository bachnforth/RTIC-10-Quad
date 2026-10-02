# Nearest waypoint ahead V3 source review

**Scope:** ArduPilot `Copter-4.7.1` (`dbe792162d06cab66c3475fd5556bf7a120f119e`). This is a source review. It does not claim a V3 SITL pass.

## Finding

The V2 `DO_CHANGE_SPEED` staging architecture should be removed. The proposed V3 late speed application can work, but waiting for the waypoint to become active is unnecessary and introduces a short interval at `WP_SPD`. The smallest stronger sequence is:

1. Outside AUTO, select the destination NAV and reconstruct its effective horizontal speed.
2. Call `mission:set_current_cmd(destination_seq)` directly while the mission is stopped.
3. Call `vehicle:set_mode(AUTO)`.
4. If that succeeds, immediately confirm mode is AUTO and call `vehicle:set_desired_speed(speed_ms)`.
5. Subsequently confirm `mission:state()==MISSION_RUNNING`, the NAV index and ID match, and `vehicle:get_target_location()` succeeds for the expected WP. This confirmation is diagnostic/fail-safe supervision; do not delay the initial speed call until it occurs.

`Copter::set_mode()` calls `ModeAuto::init()` synchronously before installing the new flight-mode pointer and returning. Therefore a successful Lua `vehicle:set_mode(AUTO)` has already passed the point where `ModeAuto::init()` clears `desired_speed_override_ms`. An immediate `vehicle:set_desired_speed()` cannot be erased by that initialization. If the 100 Hz flight loop runs between the two Lua calls, the mission may already have initialized the waypoint at `WP_SPD`, but `AC_WPNav::set_speed_NE_ms()` updates the active speed limits and recalculates the track. If it does not run between them, the override is present before waypoint initialization.

## Exact 4.7.1 paths

- `ArduCopter/mode.cpp:313-480`: `Copter::set_mode()` calls `new_flightmode->init()` at 427, assigns `flightmode` at 436, and only then returns success.
- `ArduCopter/mode_auto.cpp:23-48`: `ModeAuto::init()` initializes WPNav, clears all `desired_speed_override_ms` components, and sets `waiting_to_start`.
- `ArduCopter/mode_auto.cpp:85-114`: a later fast-loop `ModeAuto::run()` calls `mission.start_or_resume()` and clears `waiting_to_start`.
- `libraries/AP_Mission/AP_Mission.cpp:128-191`: `resume()` changes a stopped mission to running and restarts the staged NAV through `set_current_cmd()`.
- `libraries/AP_Mission/AP_Mission.cpp:596-695`: while stopped, `set_current_cmd(destination_seq)` loads that NAV without starting it; while running it uses `advance_current_nav_cmd()`.
- `libraries/AP_Mission/AP_Mission.cpp:2055-2151`: `advance_current_nav_cmd()` invokes the Copter start-command callback before marking the NAV loaded.
- `ArduCopter/mode_auto.cpp:451-488`: `ModeAuto::wp_start()` initializes WPNav with a positive override when initialization is needed, sets the destination, and then changes the AUTO submode to WP.
- `ArduCopter/Copter.cpp:497-501`: the Lua-facing vehicle method dispatches to the current flight mode's `set_speed_NE_ms()`.
- `ArduCopter/mode_auto.cpp:686-690`: AUTO writes the speed to WPNav and to `desired_speed_override_ms.xy`.
- `libraries/AC_WPNav/AC_WPNav.cpp:277-293`: the active speed setter changes `_wp_desired_speed_ne_ms`, position-controller limits, and the current track limits.
- `libraries/AP_Scripting/generator/description/bindings.desc:347-383,532-545`: the required Lua calls are bound. `set_desired_speed` is marked `skip_check`, so Lua must validate the value itself.

## Why the proposed active-NAV wait is imperfect

`mission:get_current_nav_index()==destination_seq` is not proof that the command has started: staging the NAV while stopped already sets that index. `vehicle:get_mode()==AUTO` is also insufficient because `ModeAuto::init()` leaves `waiting_to_start=true`; mission start waits for an AHRS origin.

The best Lua-visible active-WP indication is the conjunction of:

- AUTO mode;
- `mission:state()==MISSION_RUNNING`;
- expected `get_current_nav_index()` and `get_current_nav_id()`;
- `vehicle:get_target_location()` returns a location.

For AUTO, `get_target_location()` reaches `ModeAuto::get_wp()`, which returns a waypoint only in WP submode (or other explicitly handled submodes). `wp_start()` changes to WP submode only after the destination has been accepted. With object avoidance enabled, the returned OA target can differ from the raw mission waypoint, so exact coordinate comparison either needs a tolerance/policy or OA must be outside the supported configuration.

There is still no atomic Lua API combining “this NAV is active” and “set this NAV's speed.” A mode or mission transition can occur between separate Lua calls. Applying speed immediately after successful AUTO entry makes the window smallest. A minimum remaining-distance rule is still advisable so a selected WP cannot complete during entry. Repeatedly reapplying the speed is unsafe because a repeat can race the transition to the next NAV and overwrite that leg's native speed.

## Speed reconstruction

For the restricted linear missions supported by this script, scan in mission execution order through the commands preceding the selected destination and retain the last **positive horizontal** `DO_CHANGE_SPEED` (speed type 0 or 1). It persists across any number of later WPs until another positive horizontal speed command. A zero or negative target does nothing in Copter 4.7.1 and must not clear the reconstructed speed. If there is no preceding positive horizontal command, use the current `WP_SPD` value.

Do not limit reconstruction to the block between the selected leg's two WPs; that was V2's false restriction. Conversely, do not include a speed command after the selected destination: it belongs to a later mission transition and the native engine will execute it when advancing toward the next NAV.

Positive climb/descent speed commands are a separate persistent state. AUTO initialization clears their overrides, and `vehicle:set_desired_speed()` restores only horizontal speed. V3 should reject a rejoin whose prior execution history contains an effective vertical speed override unless support is deliberately added through another verified API. Continue rejecting `DO_JUMP`, CONDITION commands, and other stateful commands: a linear scan cannot reconstruct their execution history or skipped side effects safely.

## Remaining limitations

- `ModeAuto::set_speed_NE_ms()` returns true unconditionally even though WPNav silently ignores a value below its minimum or when its desired speed is not initialized. Keep strict finite/range validation before the call.
- Lua has no getter for `desired_speed_override_ms` or `_wp_desired_speed_ne_ms`; success cannot prove the final internal value. Telemetry/BIN validation remains required.
- Mission editing is not locked across scan, staging, and AUTO entry. Re-read or hash all relevant mission items before staging and validate the active target afterward.
- If the speed call fails or the active NAV check later disagrees, conservatively leave AUTO for the recorded prior safe mode when that transition is still valid, and report the failure. Mode restoration can itself fail.
- A brief default-speed interval remains possible only if the fast loop runs between `set_mode()` and `set_desired_speed()`. The immediate-call sequence minimizes it; waiting for active NAV guarantees that interval instead.

## Required V2 changes

- Remove `block_last_positive`, `block_count`, the persistent-speed rejection, and staging of a DO sequence.
- Always stage `best.to`.
- Preserve `best.speed` as the last effective horizontal speed from mission start to `best.to`; otherwise snapshot `WP_SPD`.
- After successful AUTO mode request, apply the validated speed immediately and enter a bounded confirmation state.
- Add a remaining-along-track threshold and a confirmation timeout.
- Do not mark `selected_this_arm` successful until speed application succeeds; distinguish “speed applied” from “active NAV confirmed” in STATUSTEXT.

