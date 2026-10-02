# V3.2 Batch 1 ArduCopter SITL validation

**Beginning-of-test Lua SHA-256: `08FB26474C79008156E6DC3085D8A5EB3E4F887FF77614AFB59CE140E539553E` — verified.**

## Overall result

Batch 1 found two material defects:

1. **The one-shot speed application has a real initialization-order race.** In two repetitions of the persistent-earlier-speed test, the same frozen script and mission produced different results. When `speed applied 5.0m/s` preceded the NAV 5 `MISE` record by 1.666 ms, NAV 5 settled near the 6 m/s `WP_SPD`. When NAV 5 initialized first and the setter followed 2.499 ms later, NAV 5 settled near 5 m/s.
2. **Rollback to old mission index 0 reports success but restores the first executable NAV index, sequence 1.** Rollback to a nonzero index works. V3.2's index-zero helper returns true without checking the resulting NAV index, and the telemetry shows `MISSION_CURRENT=1` after the rollback.

The original nominal V3.2 test remains a valid observation for that run. These results invalidate the conclusion that its immediate post-`set_mode(AUTO)` speed architecture is generally reliable.

## Common configuration

- Firmware from every BIN `VER` record: **ArduCopter V4.7.1 (`4776a3fb`)**.
- Windows command-line SITL, quad plus frame, speedup 1.
- Frozen script source and installed file hash matched the expected hash before testing.
- Common parameters: `SCR_ENABLE=1`, `MIS_RESTART=0`, `RC7_OPTION=300`, `WP_SPD=6`, `NWA_ENABLE=1`, `NWA_MAXDIST=100`, `NWA_MINREM=20`, `NWA_DEBUG=1`, `NWA_ONCE=1`, `NWA_AMBIG=1`.
- `ARMING_SKIPCHK=65535` was used only to make repeated SITL setup deterministic. Guided arming still waited until the EKF reported that it was using GPS, and the frozen script's independent AHRS-health and position checks remained active.
- Aircraft started airborne in GUIDED at approximately 20 m unless a case states otherwise.
- Test teardown mode changes, forced disarming, and resulting sequence reset to zero occurred only after each evidence interval.
- UTC timestamps in extracted event files are reconstructed from each BIN's `RTC` records. Boot time is the primary correlation key.

## 1. WP_SPD fallback — PASS

**Mission:** HOME; TAKEOFF; WP seq 2; WP seq 3; selected WP seq 4; `DO_CHANGE_SPEED 10` seq 5; WP seq 6; RTL. `NWA_START=3`, `NWA_END=4`, so only leg 3→4 was eligible. There was no earlier positive horizontal speed command.

- Starting mode/index: GUIDED / 1.
- Trigger: Scripting1 LOW→HIGH at boot 57.940148 s (`00:29:20.776Z`).
- Diagnostics: candidate 3→4, cross track 0.3 m, 167.2 m remaining; selected NAV 4; `effective speed 6.0m/s from WP_SPD`; staged NAV 4; AUTO entered; one `speed applied 6.0m/s`; NAV 4 confirmed.
- Mode/index transition: GUIDED/1 → AUTO/4. Test interval ended in AUTO/6 after native sequence 5 executed; teardown then selected LOITER.
- Active NAV 4 interval: boot 57.941814–89.041869 s.
- The speed setter message preceded NAV 4's `MISE` initialization by 1.666 ms. Because requested speed equals `WP_SPD`, this case verifies functional fallback behavior but cannot independently prove that the override survived NAV initialization.
- EKF horizontal speed entered and remained in the stated 6.0 ± 0.30 m/s band at boot 64.339254 s (`00:29:27.175Z`).
- Settled mean/min/max: **5.954 / 5.705 / 6.006 m/s**. Peak: **6.006 m/s**.
- At settling: **24.703 s** and approximately **147.5 m** remained to NAV 4.
- Native sequence 5 `DO_CHANGE_SPEED 10` and NAV 6 executed at boot 89.041869 s (`00:29:51.878Z`).

Verdict: all requested fallback behavior was observed, including one speed-application call and settling near 6 m/s before NAV completion.

## 2. Persistent earlier horizontal speed — FAIL

**Mission:** HOME; TAKEOFF; WP seq 2; `DO_CHANGE_SPEED type 1, 5 m/s` seq 3; WP seq 4; selected WP seq 5; `DO_CHANGE_SPEED 10` seq 6; WP seq 7; RTL. There was no speed DO in the local block between WP 4 and destination WP 5. `NWA_START=4`, `NWA_END=5`.

### First run: failed speed effect

- Starting mode/index: GUIDED / 1.
- At boot 58.000124 s (`00:31:01.836Z`), V3.2 selected NAV 5, reported `effective speed 5.0m/s from DO seq 3`, staged NAV 5, entered AUTO, and emitted exactly one `speed applied 5.0m/s`.
- NAV 5 initialized at boot 58.001790 s, **1.666 ms after the setter message**, and was confirmed active at 58.120909 s.
- Actual speed only crossed the 4.75–5.25 m/s band during acceleration, from boot 62.239261 to 62.639101 s, then continued upward. It never settled near 5 m/s.
- It instead entered and remained in a 6.0 ± 0.30 m/s band at boot 64.339254 s. Mean/min/max thereafter: **5.954 / 5.704 / 6.006 m/s**.
- At this 6 m/s settling point, **24.743 s** and approximately **147.8 m** remained on NAV 5.
- Position-controller desired horizontal velocity reached **6.000 m/s**, corroborating the EKF/GPS actual-speed result.
- Native sequence 6 `DO_CHANGE_SPEED 10` and NAV 7 executed normally at boot 89.081853 s (`00:31:32.918Z`).

### Confirmatory repeat: passed, with reversed ordering

- Same frozen Lua, parameters, mission, position, and trigger.
- NAV 5 initialized at boot 57.976800 s (`00:47:12.813Z`). The one-shot speed setter followed at 57.979299 s, **2.499 ms after NAV initialization**.
- NAV 5 then settled in 5.0 ± 0.25 m/s at boot 64.939847 s. Settled mean/min/max: **4.971 / 4.887 / 5.189 m/s**; transient peak before settling: **5.642 m/s**.
- **28.929 s** and approximately **144.3 m** remained after settling.
- Native sequence 6 and NAV 7 executed at boot 93.869104 s (`00:47:48.705Z`).

Verdict: V3.2 correctly reconstructs the earlier command, does not reject it, stages the destination NAV directly, and invokes the setter once. The commanded speed is **not reliable** because the call can precede mission/WPNav initialization and be lost. One failed repetition makes this case FAIL; the passing repeat confirms the race rather than curing it.

## 3. Direct AUTO protection — PASS

**Mission:** fallback mission from case 1. Starting mode/index was explicitly LOITER / 2. Scripting1 was not triggered.

- Ordinary GCS AUTO request at boot 57.054669 s (`00:32:41.891Z`).
- `MISE` activated the existing sequence 2 at 57.057168 s.
- At 57.145466 s, V3.2 reported `AUTO transition detected directly; no mission selection`.
- No candidate, selection, staging, or `speed applied` message occurred.
- Mission index before/after direct AUTO: **2 → 2**.
- Test interval final mode/index: AUTO / 2.

Verdict: direct AUTO did not invoke NWA rejoin behavior or mutate the selected mission command.

## 4. NWA_MINREM protection — PASS

**Mission:** HOME; TAKEOFF; WP seq 2; WP seq 3 approximately 100 m south; WP seq 4 approximately 10.0 m north of the aircraft; RTL. `NWA_START=3`, `NWA_END=4` isolated the 3→4 leg. The aircraft projection was on that leg with about 10 m remaining. `NWA_MINREM=20`, `NWA_MAXDIST=100`, and `NWA_AMBIG=1`.

- Starting mode/index: GUIDED / 1.
- Trigger at boot 58.085923 s (`00:33:46.922Z`).
- Diagnostic: `reject no eligible leg with >=20.0m remaining`.
- No AUTO mode, MISE execution, NAV staging, or speed application occurred.
- Test interval final mode/index: GUIDED / 1.

Verdict: rejection is specifically attributable to MINREM; route-range constraints excluded other legs and the candidate projection was geometrically valid and within MAXDIST.

## 5. Persistent vertical speed rejection — PASS

**Mission:** HOME; TAKEOFF; WP seq 2; persistent `DO_CHANGE_SPEED type 2, 3 m/s` seq 3; WP seq 4; candidate WP seq 5; RTL. `NWA_START=4`, `NWA_END=5`.

- Starting mode/index: GUIDED / 1.
- At boot 58.030945 s (`00:34:52.867Z`), candidate 4→5 was valid with cross track 0.3 m and 167.2 m remaining.
- Diagnostic: `reject persistent vertical speed type 2 seq 3 unsupported`.
- No NAV was staged, no speed override was applied, no MISE record was generated, and mode/index remained GUIDED / 1 through the test interval.
- Type 3 was not separately run because type 2 exercised the shared positive-vertical-state rejection branch.

Verdict: the positive persistent vertical speed was detected and rejected before AUTO without mission mutation.

## 6. Once per arm — PASS

**Mission:** fallback mission; `NWA_ONCE=1`.

- Starting mode/index: GUIDED / 1.
- First entry completed on NAV 4 at boot 57.863512 s (`00:35:57.700Z`), with one speed application.
- The harness immediately selected LOITER while remaining armed. A second LOW→HIGH generated `reject already selected this arm` at boot 59.308767 s (`00:35:59.145Z`).
- During the rejected request, mode stayed LOITER, mission index stayed 4, no MISE record appeared, and the speed-application count remained one.
- LAND auto-disarmed at approximately boot 87.0 s. After rearming and taking off, another request selected NAV 4, applied speed once, and reached `scripted entry complete` at boot 102.316557 s (`00:36:42.153Z`).
- Total setter invocations in the complete log: two, one for each successful arm cycle.

Verdict: same-arm replay was blocked, and disarm reset the latch.

## 7. External pilot mode intervention — PASS

**Mission:** fallback mission. The harness listened for `NWA: AUTO entered` and immediately issued external mode commands without changing the Lua source.

### LOITER

- Starting mode/index: GUIDED / 1.
- Script entered AUTO and staged NAV 4 at boot 57.975134 s.
- External LOITER became active at 57.991794 s, approximately 16.7 ms later and before the next 100 ms confirmation update.
- At 58.058434 s V3.2 reported `left AUTO before NAV confirmation; mode changed to 5 externally; no rollback`.
- LOITER remained selected until the second deliberate test action. No delayed restoration to GUIDED occurred.

### RTL

- Starting mode/index for repetition: LOITER / 4.
- Script entered AUTO at boot 60.462472 s; external RTL became active at 60.484130 s.
- At 60.569929 s V3.2 reported the corresponding `mode changed to 6 externally; no rollback` diagnostic.
- RTL remained active for the observation interval; teardown changed to LOITER at 62.076826 s.

The setter ran once in each attempted entry before the external command. Pending state cleared: the second LOW→HIGH was accepted instead of being rejected as already pending. The staged index remained 4 after intervention; V3.2 deliberately avoids mission rollback when an external mode wins.

Verdict: LOITER and RTL both won, and no delayed script rollback overrode either external selection.

## 8. Script-controlled confirmation failure and rollback — FAIL

**Mission:** fallback mission. Immediately after `AUTO entered`, the harness issued real `MISSION_SET_CURRENT(6)` commands. Pending expected NAV 4, so the mission engine activated NAV 6 before the next Lua confirmation tick.

### A. Prior index 0 — FAIL

- Starting mode/index: GUIDED / **0**, preserving the natural post-upload index without issuing `MISSION_SET_CURRENT(0)`.
- AUTO/NAV 4 staged at boot 57.958474 s. NAV 6 was forced at 57.974301 s.
- At 58.063432 s V3.2 detected `NAV advanced to 6 before confirmation`, restored GUIDED, and reported `mode restored=true mission index restored=true`.
- MAVLink mission telemetry then reported **sequence 1**, not sequence 0, at boot 58.144 s. No other test action occurred before case completion.
- The later sequence 0 record at teardown followed disarming and cannot be credited to rollback.

V3.2's `restore_mission_index(0)` treats a successful `mission:set_current_cmd(0)` return as sufficient. Copter normalizes the current NAV to the leading TAKEOFF command, so the reported success is false for the requested exact-index rollback.

### B. Prior nonzero index 3 — PASS

- Starting mode/index: GUIDED / 3.
- AUTO/NAV 4 staged at boot 58.055102 s. NAV 6 was forced at 58.076760 s.
- At 58.163392 s V3.2 detected the failure, restored GUIDED, and reported both restoration flags true.
- `MISSION_CURRENT` returned to **sequence 3** at boot 58.169 s and remained there until teardown.

The speed setter ran once in each induced-failure case before verification failed, as expected from V3.2's current ordering. Because required subcase A failed, the combined case verdict is FAIL.

## Compact verdict table

| # | Case | Verdict |
|---:|---|---|
| 1 | WP_SPD fallback | **PASS** |
| 2 | Persistent earlier horizontal speed | **FAIL** — initialization race; one 6 m/s result and one 5 m/s result |
| 3 | Direct AUTO protection | **PASS** |
| 4 | NWA_MINREM protection | **PASS** |
| 5 | Persistent vertical speed rejection | **PASS** |
| 6 | Once per arm | **PASS** |
| 7 | External pilot mode intervention | **PASS** — LOITER and RTL |
| 8 | Confirmation failure/rollback | **FAIL** — index 0 normalized to sequence 1; nonzero rollback passed |

## Defects and implications

### Speed-order defect

`vehicle:set_desired_speed()` is still called too early. `vehicle:set_mode(AUTO)` returning does not guarantee that the staged mission NAV has run its waypoint initialization. The evidence pair is direct:

- setter **1.666 ms before** NAV `MISE` → controller desired speed becomes 6 m/s;
- setter **2.499 ms after** NAV `MISE` → controller and aircraft settle near 5 m/s.

The smallest next architecture to test is to defer the one-shot setter until Lua observes the intended mission running, intended current NAV index/ID, and an AUTO navigation target, then apply it. That revised ordering must be tested repeatedly to show the setter always follows NAV initialization.

### Index-zero rollback defect

V3.2 cannot claim exact rollback to mission index 0. The script skips post-set verification for zero, while Copter exposes the leading executable NAV as sequence 1. A revision must either define and verify the intended Copter semantic result or report that exact zero restoration is unsupported.

### External intervention side effect

External mode selection behaves correctly and is never overridden. The staged NAV index remains changed after that intervention. This matches V3.2's conservative no-rollback policy, but a later direct AUTO entry will resume from the staged index unless the pilot or GCS changes it.

## Recommendation

Do **not** advance frozen V3.2 to another broad validation batch. Preserve it as evidence, correct the speed-order race and the index-zero rollback claim in a new version, then repeat:

1. the original local-DO nominal case multiple times;
2. the persistent-earlier-speed case multiple times while recording setter-versus-`MISE` order;
3. both rollback indices;
4. external LOITER/RTL intervention to ensure the fixes do not override pilot-selected modes.

No Lua changes were made during this batch.

**End-of-test Lua SHA-256: `08FB26474C79008156E6DC3085D8A5EB3E4F887FF77614AFB59CE140E539553E` — unchanged and verified.**
