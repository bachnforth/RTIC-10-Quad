# nearest_waypoint_ahead V3.3 review and SITL regression

## Identity

- Frozen V3.2 input SHA-256: `08FB26474C79008156E6DC3085D8A5EB3E4F887FF77614AFB59CE140E539553E`
- V3.3 output SHA-256: `F2A704BA02A26E93F01B782D05715BF94BEF937A828B5B58F21B9E3023F6A997`
- Target: ArduCopter 4.7.1
- SITL firmware reported by every BIN `VER` record: `ArduCopter V4.7.1 (4776a3fb)`
- The V3.2 input hash was verified before editing. The V3.2 file was not modified.

## Implemented changes

V3.3 preserves V3.2 mission scanning, geometry, speed reconstruction, command restrictions, trigger behavior, and external-mode handling. The focused changes are:

1. Speed application is removed from the immediate post-`set_mode(AUTO)` path.
2. Pending entry now requires the intended NAV predicate on two consecutive 100 ms Lua invocations.
3. The selected mission item command and coordinates are checked on both observations.
4. The speed setter is called once after the second valid observation, followed immediately by mode/state/index/ID checks.
5. A predicate loss between observations fails without applying speed.
6. Mission index zero is normalized, while stopped and outside AUTO, to the actual first executable NAV. That resulting nonzero index becomes the rollback index.
7. Every rollback index is verified as a loaded mission NAV and every rollback checks the resulting index.
8. `NWA_MINREM` defaults to 30 m. Position and projected remaining distance are recalculated immediately before normalization and staging.
9. Diagnostics identify V3.3, normalization, first NAV observation, stable NAV, speed application, postcheck success, and an ordering-race failure.

The script makes no attempt to suppress later native `DO_CHANGE_SPEED` commands.

## Static and mock validation

Lua parsing succeeded. The script was also loaded and executed by Fengari's Lua 5.3 VM.

| Test | Result |
|---|---|
| Setter absent on first NAV-active observation | PASS |
| Setter called once on second consecutive observation | PASS |
| Predicate loss between observations applies no speed | PASS |
| Post-set NAV change detected; no retry | PASS |
| External LOITER wins | PASS |
| External RTL wins | PASS |
| Flying-state loss causes no forced rollback | PASS |
| Disarm causes no forced rollback | PASS |
| Nonzero rollback restored | PASS |
| Index zero normalized before staging | PASS |
| Normalized rollback returns to first NAV | PASS |
| Normalization failure stops before AUTO | PASS |
| Direct AUTO does not select a NAV or set speed | PASS |
| Default `NWA_MINREM=30` | PASS |
| Later mission progress causes no Lua speed retry | PASS |

The test transcript is in `static_validation.txt`; the executable harness is `test_v33.js`.

## Real ArduCopter 4.7.1 SITL results

Eight fresh SITL instances were run. All runner processes exited zero and produced nonempty BIN logs.

### A. Persistent earlier `DO_CHANGE_SPEED` — PASS, three repetitions

Mission shape: TAKEOFF; WP; `DO_CHANGE_SPEED 5`; WP; selected destination WP; `DO_CHANGE_SPEED 10`; following WP; RTL. The selected leg was 4→5 and the reconstructed speed came from sequence 3 rather than the local block.

| Run | First→stable wait | Setter after NAV MISE | 5 m/s settle time | Settled actual speed, mean/min/max | Time left on NAV |
|---|---:|---:|---:|---:|---:|
| persistent_1 | 123.284 ms | 233.240 ms | 65.139767 s | 4.970 / 4.877 / 5.202 m/s | 28.963 s |
| persistent_2 | 104.958 ms | 229.908 ms | 64.939847 s | 4.972 / 4.886 / 5.236 m/s | 28.994 s |
| persistent_3 | 99.960 ms | 216.580 ms | 64.739094 s | 4.972 / 4.888 / 5.240 m/s | 28.995 s |

Each run emitted exactly one speed-application message. All three settled in the stated 5.0 ± 0.25 m/s band before the selected NAV completed. None settled at `WP_SPD=6`.

The peak actual velocity during the initial acceleration transient was 5.634–5.641 m/s. This occurred before settling and does not represent the sustained NAV speed.

### B. Local speed command and subsequent native command — PASS

The mission used the requested sequence structure, including `DO_CHANGE_SPEED 5` at sequence 5, destination NAV 6, `DO_CHANGE_SPEED 10` at sequence 7, and NAV 8.

| Event | UTC | Boot time |
|---|---|---:|
| NAV 6 `MISE` | 2026-09-21 18:22:28.833Z | 57.996792 s |
| NAV 6 first observed initialized | 2026-09-21 18:22:28.939Z | 58.102583 s |
| NAV 6 stable | 2026-09-21 18:22:29.056Z | 58.220036 s |
| Speed applied 5.0 m/s | 2026-09-21 18:22:29.056Z | 58.220036 s |
| Postcheck successful | 2026-09-21 18:22:29.056Z | 58.220036 s |
| NAV 6 complete; sequence 7 executes | 2026-09-21 18:23:04.738Z | 93.901591 s |
| NAV 8 `MISE` | 2026-09-21 18:23:04.738Z | 93.901591 s |

NAV 6 settled at 5.0 ± 0.25 m/s at boot 64.939847 s. From there through NAV completion, actual horizontal velocity mean/min/max was 4.971/4.884/5.209 m/s. NAV 6 still had 28.962 seconds and approximately 144.4 m remaining.

Sequence 7 executed at the exact mission transition into NAV 8. During the following seven-second capture, position-controller desired horizontal velocity reached 9.999 m/s and actual EKF horizontal velocity reached 9.568 m/s. This confirms that the native 10 m/s command replaced the Lua override normally.

Horizontal velocity is calculated from BIN `XKF1` as `sqrt(VN² + VE²)`. The extracted CSV also includes GPS speed and the horizontal magnitudes of `PSCN/PSCE` desired, target, and actual velocity.

### C. Initial mission index zero — PASS

- Natural post-upload mission position was sequence 0.
- Before staging, V3.3 reported: `mission index 0 normalized to first NAV 1 for recoverable entry`.
- NAV 4 was then staged and AUTO requested.
- The harness forced NAV 6 before confirmation.
- The script applied no speed, restored GUIDED, reported both restoration flags true, and MAVLink subsequently reported mission sequence 1.

This verifies normalization before staging and rollback to the verified normalized NAV. It does not claim restoration of the original unloaded index-zero representation.

### D. Nonzero rollback — PASS

The starting mission NAV was sequence 3. After the same forced confirmation failure, the script applied no speed, restored GUIDED, and mission telemetry returned to sequence 3.

### E. Direct AUTO — PASS

An ordinary AUTO entry from LOITER started the previously selected NAV 2. V3.3 reported `AUTO transition detected directly; no mission selection`. No scripted selection, staging, normalization, or speed application occurred.

### F. External mode intervention — PASS

LOITER and RTL were each commanded immediately after the script reported AUTO entry. Both external modes remained in control. V3.3 reported the external mode and performed no rollback or speed application.

## Result and limitations

V3.3 fixes both Batch 1 failures in these tests:

- all repeated persistent-speed runs settled near the reconstructed 5 m/s rather than `WP_SPD=6`;
- index-zero entry now establishes and verifies a recoverable first-NAV baseline rather than claiming that sequence zero was restored.

The Copter-4.7.1 Lua API still cannot atomically bind `set_desired_speed()` to a particular mission generation or sequence. A NAV may theoretically advance after the final predicate check and before the setter takes effect. The immediate postcheck detects that outcome, and the script never retries the setter, but it cannot prevent a brief speed write to the following NAV. `NWA_MINREM=30` and the two-observation delay reduce this risk.

There is also no Lua-visible WPNav update counter. The 100 ms stable interval is a scheduling guarantee demonstrated in SITL rather than an atomic C++ API guarantee.

On an installation that already saved the V3.2 dynamic parameter value, loading V3.3 may retain the saved `NWA_MINREM=20` despite the new source default. Set `NWA_MINREM=30` explicitly when migrating an existing parameter store.

## Recommendation

V3.3 is suitable to proceed to the broader controlled SITL validation matrix. It is not flight-ready based on this regression alone. Crossing/ambiguity cases, all rejection paths, repeated AUTO entries with `NWA_ONCE=0`, mission edits during pending entry, and relevant failsafe interactions remain appropriate broader-matrix tests.

## Artifacts

- `nearest_waypoint_ahead_v3_3.lua` — implementation
- `static_validation.txt` and `test_v33.js` — static/mock evidence
- `sitl_evidence/<case>/*.BIN` — original DataFlash logs
- `sitl_evidence/<case>/bin_events.csv` — timestamped BIN event extracts
- `sitl_evidence/<speed-case>/speed_telemetry_10hz.csv` — EKF/GPS/controller evidence
- `sitl_evidence/<case>/events.json` and `telemetry_live.csv` — timestamped live telemetry
- `sitl_evidence/<case>/mission_download.json` and `mission.waypoints` — mission evidence
- `sitl_evidence/<case>/sitl_stdout.txt`, `sitl_stderr.txt`, and `runner_output.txt` — console evidence
- `sitl_evidence/analysis_summary.json` — machine-readable measurements
- `SHA256SUMS.txt` — artifact hashes
