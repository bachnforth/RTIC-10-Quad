# Nearest Waypoint Ahead V3.3 — Batch 2 SITL Validation

## Scope and configuration

- Firmware recorded in the DataFlash logs: `ArduCopter V4.7.1 (4776a3fb)`.
- Frozen Lua SHA-256 before testing: `F2A704BA02A26E93F01B782D05715BF94BEF937A828B5B58F21B9E3023F6A997`.
- Frozen Lua SHA-256 after testing: `F2A704BA02A26E93F01B782D05715BF94BEF937A828B5B58F21B9E3023F6A997`.
- The installed SITL copy had the same final hash.
- The Lua file was not modified.
- Normal configuration: `SCR_ENABLE=1`, `RC7_OPTION=300`, `WP_SPD=6`, `NWA_ENABLE=1`, `NWA_ONCE=0`, `NWA_MAXDIST=100`, `NWA_MINLEG=2`, `NWA_AMBIG=1`, `NWA_MINREM=30`, and `MIS_RESTART=0`. Individual parameter tests changed only the field under test. `ARMING_SKIPCHK=65535` was used to make the Windows SITL setup repeatable; V3.3 still independently required armed, flying, AHRS and position state.
- Evidence came from MAVLink event capture and DataFlash `.BIN` logs. HUD screenshots were not used.

This was controlled SITL validation. It is not flight-readiness testing.

## Results

The 45 requested headings expanded to 54 deterministic rows because commands and parameter boundaries were tested as separate variants.

| Result | Count |
|---|---:|
| PASS | 51 |
| FAIL | 0 |
| INCONCLUSIVE | 3 |

All 51 executed deterministic variants passed their evidence based assertion. Five timing cases initially carried a harness `FAIL` because long ArduPilot `STATUSTEXT` messages were split at the MAVLink boundary and the harness expected the complete suffix. Their event streams establish the required outcomes: cases 35–37 retained the externally selected mode with zero speed applications, case 40 lost the NAV stability predicate and applied no speed, and case 42 made no second mission selection during direct AUTO. The consolidated CSV records the corrected evidence verdict and reason. No Lua behavior was changed.

### Geometry and mission selection

- Mid-leg and near-leg-start positions selected the expected ahead destination.
- Projections before a leg or beyond its destination were ineligible.
- The measured inside-boundary cases accepted at 99.3 m cross track and 30.7 m remaining. The corresponding outside cases rejected without staging, AUTO, or a speed setter.
- Short legs, ambiguous parallel legs, and intersecting legs rejected conservatively.
- TAKEOFF followed by explicit waypoints, terminal RTL, and terminal LAND were accepted in the documented mission shape.
- All accepted cases recorded one staging operation and one speed setter unless the test deliberately interrupted the pending entry.

### Mission semantics and speed state

- Multiple earlier horizontal speed commands reconstructed the most recent positive value: case 15 selected NAV 6 and reconstructed 7.0 m/s from DO sequence 4.
- A later speed value of zero did not erase the earlier persistent 5.0 m/s state.
- Horizontal speed types 0 and 1 both reconstructed 5.0 m/s.
- Positive vertical speed types 2 and 3 rejected before staging.
- DO_JUMP, CONDITION, and malformed mission shapes rejected before staging.
- Each accepted speed case applied the Lua speed exactly once after NAV initialization and a stable follow-up observation.

DataFlash `XKF1` velocity and `PSCN`/`PSCE` navigation fields produced these measurements:

| Case | Intended NAV | Lua speed | NAV start (boot s) | Speed applied (boot s) | Next DO (boot s) | Settled velocity | Time left on NAV at settle |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 multiple speed | 6 | 7.0 m/s | 71.302 | 71.492 | 96.557 | mean 6.957 m/s | 17.257 s |
| 16 zero/no-change | 6 | 5.0 m/s | 71.332 | 71.517 | 103.887 | mean 4.969 m/s | 25.187 s |
| 17 speed type 0 | 5 | 5.0 m/s | 71.407 | 71.585 | 103.952 | mean 4.971 m/s | 25.552 s |
| 18 speed type 1 | 5 | 5.0 m/s | 70.517 | 70.697 | 103.062 | mean 4.972 m/s | 25.562 s |

The next native 10 m/s `DO_CHANGE_SPEED` executed at the recorded “Next DO” timestamp, simultaneously followed by the next NAV command in these missions. During the next five seconds the measured horizontal velocity rose to 8.66, 7.56, 7.63, and 7.62 m/s respectively, and the PSC desired/target fields increased toward the new command. The short post-transition capture does not claim that all four had settled at 10 m/s; it demonstrates that the later native speed command replaced the Lua entry speed and began the expected acceleration.

### Trigger, parameters, and failure behavior

- Disable/enable, once-per-arm, disarm/rearm latch reset, held-HIGH behavior, and extra edges while pending behaved as specified.
- `MIS_RESTART != 0` rejected without mutation.
- `NWA_MAXDIST`, `NWA_MINLEG`, and `NWA_MINREM` accepted their documented upper/lower valid values and rejected out-of-range values. Normal geometry tests explicitly used `NWA_MINREM=30`.
- Invalid enable, ambiguity, and distance values rejected before mutation.
- External LOITER during both pending states and external RTL won immediately; there was no speed application or forced mode rollback.
- Disarm during pending emitted its diagnostic, applied no speed, and did not force a mode rollback.
- Changing the intended NAV before speed application invalidated the stability predicate, prevented the setter, and restored the saved state.
- A later ordinary direct AUTO emitted the direct-entry diagnostic and caused no second staging or speed application.
- Separate arm cycles each completed one scripted entry.
- Initial mission index 0 normalized to the first actual NAV for rollback. A nonzero initial index remained the rollback baseline and was restored after induced failure.

### Inconclusive cases

1. **AUTO request refusal (34):** no deterministic runtime mechanism was available to make only `vehicle:set_mode(AUTO)` fail while preserving the armed, flying, position, mission-stopped, and valid-mission prerequisites required to reach that call.
2. **Flying-state loss without disarm (39):** SITL could not deterministically force `AP_Vehicle::is_flying()` false inside the approximately 100 ms pending interval without using disarm, which is covered separately.
3. **NAV change during or immediately after the speed setter (41):** the check-to-set/postcheck interval is below the controllable MAVLink intervention resolution in this Windows SITL setup. A forced result would not have been a repeatable test of the documented residual race.

These are untested timing paths, not passes.

## Randomized geometry campaign

A fixed seed (`3300471`) generated 120 missions around the current aircraft position: 30 single-leg, 30 arbitrary polyline, 30 parallel-leg, and 30 crossing-leg missions. Every mission and its aircraft position were passed through a separate Python oracle that independently calculated segment length, projection, cross track, remaining distance, `MAXDIST`, `MINLEG`, `MINREM=30`, and ambiguity. The oracle did not call or translate the Lua implementation.

| Oracle result | Count | V3.3 match |
|---|---:|---:|
| Select destination | 76 | 76 |
| Reject | 44 | 44 |
| Total | 120 | 120 |

Discrepancies: **none**. Each row retains the oracle inputs and values, actual destination or rejection, status text, mode/index transitions, mission path, and verdict.

Two invalid preliminary campaigns were excluded from the result set. One used MAVLink source system 254, so SITL correctly ignored RC override intended for `SYSID_MYGCS=255`. The other allowed simulated low throttle in LOITER and landed after its first accepted case. The final campaign used source system 255 and GUIDED altitude hold, restarted from the same fixed random seed, and produced the retained 120-case evidence and `.BIN` log.

## Findings and limitations

No new V3.3 script defect was found. No result invalidates the V3.3 architecture.

Behavior that remains a documented limitation:

- The script intentionally supports a narrow mission grammar: leading TAKEOFF, explicit ordinary waypoints, supported horizontal speed commands, and a terminal RTL or LAND. Stateful or unsupported commands cause conservative rejection.
- Selection is geometric. It does not infer pilot intent or route direction from aircraft heading.
- Ambiguity is based on the difference between the two smallest eligible cross-track distances.
- The one-shot setter retains a very small check/set/postcheck race that cannot be eliminated or deterministically injected through the Copter 4.7.1 Lua and MAVLink interfaces used here.
- AUTO request refusal and non-disarm flying-state loss still need a suitable fault-injection facility.
- SITL does not cover sensor faults, RC link behavior, scheduler overload, physical dynamics, object avoidance interactions, or real vehicle failsafes.

## Recommendation

V3.3 can proceed to endurance and stress SITL testing. That phase should repeat scripted entries for long durations, vary scheduler and telemetry load, exercise larger missions, and use any available internal fault-injection hooks for the three inconclusive paths. This recommendation does not describe V3.3 as flight-ready.

## Artifact guide

- `deterministic_results.csv`: all deterministic inputs, mission definitions, positions, transitions, status text, final state, evidence paths, and verdict reasons.
- `randomized_geometry_results.csv`: all 120 independent-oracle comparisons.
- `missions/`: deterministic and randomized QGC waypoint files.
- `events/`: timestamped MAVLink capture, per-case JSON, runner output, and per-case DataFlash logs.
- `logs/`: speed-case and randomized-campaign `.BIN` logs.
- `telemetry/`: 10 Hz speed extracts and computed metrics.
- `nearest_waypoint_ahead_v3_3_TESTED_UNCHANGED.lua`: frozen tested file.
- `SHA256SUMS.txt`: hashes for the result tree.
