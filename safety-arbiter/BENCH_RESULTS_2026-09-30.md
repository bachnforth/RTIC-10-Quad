# Safety arbiter bench results, 2026-09-30 (stage 1)

Props off, load disconnected. Ground station for stage 1 was the laptop on the mesh
(10.223.58.10), sending exactly the QGC `SafetyDevice.json` commands through the
real path: mesh, Pi filter (`/dev/serial0` 115200), LUX SERIAL1, `safety_arbiter.lua`,
S1/S2, ESP32. Evidence: `bench\bench_log_2026-09-30.txt` (ESP32 USB serial, LUX USB
MAVLink and the mesh feed, time-stamped together).

Installed: `safety_arbiter.lua` SHA-256 `05b49ed6...4e4432` (verified on the SD card by
readback); ESP32 firmware unchanged (`phase10_linkloss_hold`).

| # | Test | Result | Evidence (log time) |
|---|---|---|---|
| 1 | Boot defaults | PASS | Request cleared at boot; S1 1500 until ESP32 status seen, then 1100; ESP32 SAFE, no faults |
| 2 | SB only | PASS | SB up: S1 1900, ARM accepted 0.46 s later, countdown 31..1, ARMED 31.54 s after S1; SB down: SAFE in 0.2 s (10:31:26-10:32:10) |
| 3 | App only | PASS | CONFIRM alone denied; REQUEST expired at 10 s, late CONFIRM denied; REQUEST+CONFIRM: ARMED 31.48 s after S1 (10:33:13-10:34:10) |
| 4 | Conflicts | PASS | App DISARM with SB held up: SAFE, stayed SAFE; SB down/up re-armed; app ARM then SB up/down: SAFE (10:37:08-10:40:08) |
| 5 | Standoff timing | PASS | 31.48-31.54 s from S1 assert to ARMED (0.5 s sustain + 31 s) |
| 6 | App DISARM while ARMED | PASS | SAFE within 0.2 s (10:34:14) |
| 7 | Pocket off | PASS | Pocket lost 8 s into standoff: continued to ARMED (10:42:59-10:43:22); contact fired with no transmitter (10:43:48); app DISARM and app ARM worked with Pocket off, no Code 5 (10:44:19-10:44:55); Pocket back on with SE held 20 s: S2 stayed 1100, no fire; fresh SE press fired (10:56:47) |
| 8 | App link loss | PASS | Filter stopped 5 s into app-started standoff: ARMED anyway, stayed ARMED; DISARM worked once restored (10:52:51-10:53:40) |
| 9 | LUX reboot while ARMED | PASS | ESP32 held ARMED through the reboot; after boot "Safety ARMED at LUX boot, holding", S1 1500; contact fired during the hold; app DISARM to SAFE (10:57:55-11:00:39). "SB up since boot does not arm" verified in SITL only |
| 10 | FIRE before ARMED | PASS | SE in SAFE: Code 3 FIRE WHILE SAFE, no load, self-cleared on release (x4); SE during standoff: Code 3 FIRE DURING STANDOFF, no load, cleared by SB down (10:54:51) |
| - | Filter rejections | PASS | Wrong key and QGC built-in vehicle ARM (400) blocked at the Pi (2 blocked, no ACK) |

All state and countdown messages reached the mesh ground station 0.1-0.4 s after the LUX sent them.

## Findings to act on
1. **LUX watchdog reset at 10:15:36** (IMU samples stopped, main loop stuck ~1.8 s),
   coinciding with plugging in the battery and other devices while the LUX was on USB.
   No recurrence in 42+ minutes of battery running through all tests. Crash dump saved in
   `backups\LUX_crashdump_2026-09-30\`. The LUX now shows `PreArm: CrashDump data detected`
   (blocks motor arming) - review before any flight.
2. **Pocket was on the wrong model at first**: SB was on CH6 but SE drove no channel, so
   radio FIRE could not work. Corrected by the user. Check the model before every session.
3. **Contact made/broke three times in ~1.5 s on one press** (11:00:26: 127 ms, 813 ms,
   197 ms closures). Each qualified as a fire. Check the contact mechanically before any
   live-load work.
4. At the LUX output start-up after reboot, the ESP32 logged one "PWM VALID" blip that
   reverted in the same instant (10:58:06). No state change. Scope S1/S2 during a LUX
   reboot to confirm there is no stray pulse.

## Not yet done
- Scope measurement of S1/S2 pulse widths (also see "Still to do" at the end).

## Stage 2: phone (QGC 5.0.8 over the mesh) - 11:05
PASS. CONFIRM alone denied; REQUEST+CONFIRM started a standoff; DISARM returned SAFE.
The operator does not want audio, and saw neither a countdown nor ESAD state in the
Fly View (v1 only spoke them). This led to v2/v3.

## v2 (panel + silent), SHA-256 43bd5aa8... - FAILED ON HARDWARE, replaced
SITL 61/61, but on the LUX the arbiter stopped after its first panel message:
`mavlink:send_chan` raises an error for channel numbers above the build's buffer count
(the LUX has fewer than SITL). While stopped, S1/S2 stayed **frozen at 1100** instead of
falling to 1500.

## Design flaw found (present since v1): outputs froze when the script stopped
ArduPilot boots with every output's "fixed PWM" flag set; nothing clears it for a
scripting function, so an expired `set_output_pwm_chan_timeout` override keeps its last
value instead of returning to SERVOx_TRIM. A script stop while ARMED would have left S1
at 1900 with app and SB unable to disarm (SW1 still worked). Neither SITL nor the stage 1
bench tested a script stop on its own. v1 reproduces it in SITL: T11 fails, S1/S2 stay
(1900, 1100).

## v3, SHA-256 b6e86ec0...4dcf534 - installed 12:4x, verified
- Clears the flag once at start (`SRV_Channels:set_output_scaled`), so a stopped script
  really falls back to 1500 us.
- Panel sender skips past the last channel instead of erroring.
- All Safety STATUSTEXT at INFO (silent); only "ARBITER STOPPED" stays CRITICAL.
- GENERATOR_STATUS at 2 Hz: status = ESAD state (0 SAFE, 1 STANDOFF, 2 ARMED,
  3x FAULT code x, 9 no status), runtime = standoff seconds left.
- SITL 68/68 including new T11 (script stop while ARMED).
- On the LUX: arbiter answers commands, panel at 2 Hz. **Script stop while ARMED
  (MAV_CMD_SCRIPTING STOP) at 12:49:39: S1/S2 went to 1500 within one status update,
  ESP32 held ARMED; contact fired while stopped (12:50:17, single 324 ms closure);
  STOP_AND_RESTART: arbiter came back in boot hold (S1 1500, "ARMED at LUX boot,
  holding"); DISARM -> SAFE (12:50:26).**

## Still to do
- Configure the Fly View values panel on the phone and check it over the mesh (needs
  battery, Pi, mesh radio and phone on the mesh).

## Stage 2 repeat with v3 and the Fly View panel - PASS (13:1x)
Pi filter running as the `safety-mavlink-filter` systemd service (target phone). Operator
configured the Fly View telemetry values bar (Generator status as "ESAD" with colour
ranges, Generator runtime as "Standoff"), and confirmed: ESAD 0 green; request+confirm
gave 1 yellow with Standoff counting down, then 2 red; DISARM back to 0 green; no audio.
Filter forwarded 3 x request, 3 x confirm, 3 x disarm. Afterwards ESP32 SAFE, fire count
unchanged (6), LUX up 26 min with no internal errors.
