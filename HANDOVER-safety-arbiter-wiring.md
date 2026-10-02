# Handover: QGC Safety ARM/DISARM for the ESP32 safety device (wiring, install, bench validation)

Date: 2026-09-29. Project folder: `C:\Users\ebach\Documents\ChatGPT\10 inch Quad`.
All new files are in `safety-arbiter\`. Read `safety-arbiter\README.md` first.

## STATUS 2026-09-30 (read this first)
Wiring, Pi setup, LUX install, phone setup and bench validation are DONE. See
`safety-arbiter/BENCH_RESULTS_2026-09-30.md` and `CHANGE-RECORD-pi-video.md`.
- Installed arbiter is **v3, SHA-256 b6e86ec026ffd19225384494aa8ab7d2d84fb90524d9a3e37432d8179dcdf534**
  (silent messages, Fly View panel via GENERATOR_STATUS, fixed fallback to 1500 us if the
  script stops). The v1 hash further down is historical.
- `esad_gate.lua` on the SD card was renamed `.disabled` (conflicted); copy in backups.
- Pi filter runs as systemd service `safety-mavlink-filter` (target 10.223.58.11:14550).
- The crash dump from the 2026-09-30 10:15 watchdog reset (IMU samples stopped at battery
  connect while on USB) was saved to backups and erased by reflashing identical 4.7.1
  at 14:3x; ARMING_CRSDP_IGN stays 0. Power up battery first, then USB.
- Open items: laptop Wi-Fi is on a static mesh IP
  (revert to DHCP when done); scope S1/S2; check the Pocket model each session; the
  deflection contact made/broke 3 times on one press once.

## About the user
- New to programming. Define jargon. Give explicit, step-by-step physical instructions.
- Wants Claude to run commands itself. Ask the user only for physical tasks (soldering, cables, power, phone taps) and approvals.
- Claude must never handle passwords (Mini, mesh, hotspot, Pi). The user types them.
- Training exercise. **Props off and the load disconnected for all work. No flight or live-load tests.**

## Goal
Add "Safety ARM" and "Safety DISARM" to QGroundControl 5.0.8 on the Galaxy S24 for the ESP32 safety device. This is not the LUX flight controller's motor Arm/Disarm; never conflate them. The RadioMaster Pocket (SB = ARM, SE = FIRE) and the app work interchangeably.

## Design approved by the user (do not re-litigate)
- A Lua script on the LUX F765 (`safety_arbiter.lua`) is the single arbiter for S1 (ARM, output 9) and S2 (FIRE, output 10). The ESP32 firmware `esp32_safety_device_phase10_linkloss_hold` is **unchanged**. Do not modify or reflash it.
- One ARM request latch; last command wins. DISARM from either source always clears it. It starts cleared after boot.
  - SB released to up: set. SB must be seen released first, so SB up at boot does nothing.
  - SB up to released: cleared.
  - App: "Safety ARM 1/2: request", then "Safety ARM 2/2: confirm" within 10 s: set. Two taps are needed because QGC 5.0.8 custom actions send instantly, with no slide-to-confirm.
  - App "Safety DISARM": cleared, even with SB up. To re-arm from SB, cycle SB down and up.
- **Pocket link loss and app link loss change nothing.** A standoff continues to ARMED and ARMED stays ARMED (approved by the user).
- Once ARMED, the deflection contact fires regardless of any link. The ESP32 already does this.
- S2 (FIRE): SE passes through while the Pocket link is valid. While it is lost, and after it returns until SE has been seen released, S2 is 1100 us (released). The app never sends FIRE.
- LUX reboot while ARMED (option A, approved): S1 goes to 1500 us and the ESP32 holds ARMED. After boot the script reads the ESP32 status. If ARMED, it keeps holding at 1500. Otherwise it sends 1100.
- SW1 SAFE, the 31 s standoff (plus 0.5 s ARM sustain), FIRE-before-ARMED faults (Code 3) and the contact behaviour are all the ESP32's and are unchanged.
- ESP32 state is reported to QGC from the ESP32's own 1 Hz JSON line over a new status wire. It is spoken and listed as STATUSTEXT, and sent as NAMED_VALUE_FLOAT `SD_STATE`, `SD_CD` (countdown), `SD_REQ` and `SD_TXOK`. An acknowledgment alone is never proof.

## Current state
- **Nothing is installed on the aircraft, ESP32, Pi or phone yet.** The user is wiring next.
- Built and tested in ArduCopter 4.7.1 SITL, with the Pi filter in the loop and a Python port of the ESP32 firmware: **58/58 checks passed** (`safety-arbiter\sim\results\`). Tested script SHA-256: `05b49ed641383ef5264fa0aece1278f06b29574d633fcb315d57d48d1b4e4432`. Re-check the hash before installing.
- The last live LUX parameter snapshot is `params\LUXF765_QGC_READONLY_2026-09-20.param`. Re-verify live values before changing anything.
- The old PC relay `tmp\qgc_readonly_udp_relay.py` is untouched. Note that it overwrites `params\LUXF765_QGC_READONLY_2026-09-20.json` while it runs.

## Files
| File | Purpose / destination |
|---|---|
| `safety-arbiter\safety_arbiter.lua` | LUX SD card `APM/scripts/` |
| `.codex_tmp\ardupilot-src-4.7.1\libraries\AP_Scripting\modules\MAVLink\` `mavlink_msgs.lua`, `mavlink_msg_COMMAND_LONG.lua`, `mavlink_msg_COMMAND_ACK.lua` | LUX SD card `APM/scripts/modules/MAVLink/` |
| `safety-arbiter\safety_arbiter_delta.param` | Parameter changes (below) |
| `safety-arbiter\SafetyDevice.json` | Phone: `/sdcard/Android/data/org.mavlink.qgroundcontrol/files/QGroundControl/MavlinkActions/` |
| `safety-arbiter\pi\safety_mavlink_filter.py` | Pi. Filtered MAVLink bridge from the LUX serial port to QGC over the mesh (UDP) |
| `safety-arbiter\sim\` | SITL harness, ESP32 model, results. Not installed anywhere |

## Parameter changes (`safety_arbiter_delta.param`)
| Param | Old | New | Why |
|---|---|---|---|
| SERVO9_FUNCTION | 145 (RCIN6Scaled) | 94 (Script1) | S1 driven by the script |
| SERVO10_FUNCTION | 148 (RCIN9Scaled) | 95 (Script2) | S2 driven by the script |
| SERIAL2_PROTOCOL | -1 | 28 (Scripting) | ESP32 status in on UART5 |
| SERIAL2_BAUD | 57 | 115 | ESP32 prints at 115200 |
| SERIAL1_PROTOCOL | -1 | 2 (MAVLink2) | Link to the Pi |
| SERIAL1_BAUD | 57 | 115 | Pi Zero 2 W mini-UART |

Relied on and unchanged: SERVO9/10_TRIM 1500, MIN 1100, MAX 1900, SCR_ENABLE 1, MAV_GCS_SYSID 255, RC6 (SB) 999/1503/2000, RC9 (SE) 1100/1500/1900. Leave SERIAL3/4/5/6/8 alone. SERIAL8 (USART6, pads RX6/TX6) is the ELRS receiver.

## Network facts (from `CHANGE-RECORD-pi-video.md` and `HANDOVER-doodle-mini-mesh-joined.md`; verify)
- Mesh: flat `10.223.0.0/16`, static IPs, no DHCP. Galaxy S24 = `10.223.58.11` on the handheld's Wi-Fi AP `Meshnet-0610`.
- As of 2026-09-28 the Pi is wired to the user's handheld radio (10.223.196.130) with a custom USB cord. The Pi's mesh address is `10.223.79.20`. The video stream already goes to 10.223.58.11:5600.
- Laptop SSH to the Pi works only over the laptop hotspot `RN081`: `ssh -i C:\Users\ebach\.ssh\id_ed25519_rpi ebach@192.168.137.2`. See the "Pi Wi-Fi" gotcha in the mesh handover: `RoboticsLan` autoconnect must be turned off to use the hotspot, and turned back on afterwards.
- The phone has USB debugging on. adb is in `platform-tools\` in the project folder.

---

## Phase A: wiring (user does this; Claude guides)

Before starting: battery unplugged, USB unplugged from everything, props off, load disconnected, SW1 in SAFE.

### A1. ESP32 status wire (1 wire + 1 resistor)
- From: ESP32 **GPIO1**. On the HiLetgo 38-pin ESP32 DevKitC this pin is labelled **TX** (sometimes TX0/TXD0), next to RX (GPIO3). Do not use GPIO17 (the red LED).
- Through: a **1 kOhm resistor** in series (solder it inline and cover it with heat-shrink).
- To: LUX **RX5** pad. It is on the **bottom** side of the LUX, in the second row of pads along the bottom edge. Reading left to right, looking at the bottom side as in `safety-arbiter/LUXF765_NDAA_BOTTOM.png` (the ArduPilot pinout image): GND, 5V, CAN_L, CAN_H, RX6, TX6, **RX5**, TX5, 5V, GND.
- **RX6 and TX6, immediately left of RX5, are the ELRS receiver. Do not bridge them.**
- Leave TX5 empty. No new ground is needed: the S1/S2 harness already shares ground between the LUX and the ESP32.

### A2. Pi to LUX serial link (2 wires, crossed)
- Pi **pin 8 (GPIO14, TXD)** goes to LUX **RX1**.
- Pi **pin 10 (GPIO15, RXD)** goes to LUX **TX1**.
- Transmit always goes to receive. Never connect TX to TX.
- LUX TX1/RX1: **bottom** side, the bottom-right group of pads (TX1, RX1, 5V, GND).
- Finding Pi pins 8 and 10 on the Pi Zero 2 W header: pin 1 has the square pad. The row along the board edge holds the even pins. Counting along that edge row from the pin-1 end: 2 (5V), 4 (5V), 6 (GND), **8 (TXD)**, **10 (RXD)**. Confirm pin 1 by its square pad before soldering.
- No new ground: the Pi is already grounded to the FC.

### A3. Checks after soldering (multimeter, power still off)
- No continuity between RX5 and RX6, RX5 and TX6, RX5 and TX5, or TX1 and RX1.
- No continuity from any new pad to 5V or GND.
- About 1 kOhm between ESP32 TX and LUX RX5.
- Continuity: Pi pin 8 to RX1, and Pi pin 10 to TX1.
- Tug-test each joint, then photograph the joints for the record.

## Phase B: Pi setup (Claude over SSH on the hotspot; user does Wi-Fi/network physical steps)
Do this before the LUX SERIAL1 parameters are enabled.
1. Check the live `/boot/firmware/cmdline.txt` and `/boot/firmware/config.txt`. The saved copies `quadpi-cmdline.txt` and `quadpi-config.txt` are from 2026-09-11 and show `console=serial0,115200`.
2. Back up both files (`sudo cp X X.pre-safety-arbiter`) and record the change in `CHANGE-RECORD-pi-video.md`, with original and new values and how to revert.
3. Remove `console=serial0,115200` from cmdline.txt. Keep everything else, and keep it on one line.
4. Add `enable_uart=1` under `[all]` in config.txt.
5. Check that the serial login getty is not running on serial0 (`systemctl status serial-getty@ttyS0`), and disable it if it is.
6. Reboot the Pi. Confirm that `/dev/serial0` exists and that `picam-stream` is still running.
7. Install pymavlink in a venv (needs internet, for example over RoboticsLan): `python3 -m venv ~/mavenv && ~/mavenv/bin/pip install pymavlink`.
8. Copy `safety_mavlink_filter.py` to `~/safety-arbiter/` on the Pi (scp).

## Phase C: LUX install (Claude, with the LUX on USB to the laptop; props off)
1. Save a new full parameter backup from the live LUX to a new dated file in `params\`. Never overwrite existing backups.
2. Diff the live values against the "Old" column above. Stop and ask the user if anything differs.
3. Put `safety_arbiter.lua` and the three MAVLink module files on the SD card, either with Mission Planner MAVFtp or by removing the SD card (user's choice). Paths: `APM/scripts/safety_arbiter.lua` and `APM/scripts/modules/MAVLink/*.lua`. Verify the script's SHA-256 matches the tested hash.
4. Apply the six parameters, then reboot the LUX.
5. Expect the message `Safety arbiter running, ARM request cleared`. With the ESP32 powered and the status wire connected, expect `Safety SAFE` or `Safety FAULT ARM PWM INVALID/LOST` (the normal power-up Code 5; clear it with SW1 ENABLE then SAFE, or an SB up/down cycle).
6. If you see `Safety arbiter: SERVO9/10 not Script1/2` or `no status serial port`, the parameters did not take.

## Phase D: phone
1. `platform-tools\adb.exe push safety-arbiter\SafetyDevice.json /sdcard/Android/data/org.mavlink.qgroundcontrol/files/QGroundControl/MavlinkActions/SafetyDevice.json` (create the folder if needed).
2. In QGC: Application Settings, then Fly View, then set the MAVLink/custom actions file to `SafetyDevice.json`, then restart QGC. The exact menu label on 5.0.8 has not been confirmed; find it on the phone.
3. The actions appear in the Fly View **Actions** list: "Safety DISARM", "Safety ARM 1/2: request", "Safety ARM 2/2: confirm".

## Phase E: link over the mesh
1. On the Pi: `~/mavenv/bin/python ~/safety-arbiter/safety_mavlink_filter.py --serial /dev/serial0 --baud 115200 --udp-target 10.223.58.11:14550`.
2. QGC connects over UDP 14550 (add a UDP link if it does not connect automatically). Confirm telemetry, then open the filter's status file `/tmp/safety_mavlink_filter_status.json`.
3. Running it as a systemd service is a later, optional step. Ask the user first.

## Phase F: bench validation (props off, load disconnected)
Log the ESP32 USB serial JSON (Arduino serial monitor at 115200) alongside what QGC says and shows. If possible, scope S1/S2: 50 Hz, only 1100/1500/1900 us.
1. **Boot defaults:** arbiter message, `SD_REQ=0`, S1 1100 once status is seen, no arm.
2. **SB only:** SB up, full standoff to ARMED, SB down to SAFE.
3. **App only:** CONFIRM alone is denied; request, wait 11 s, confirm is denied; request plus confirm arms after the standoff.
4. **Conflicts:** SB up, then app DISARM: stays SAFE with SB up. An SB down/up cycle re-arms. App ARM, then SB up/down, disarms.
5. **Timing:** 31.5 s from S1 asserting to ARMED.
6. **App DISARM while ARMED.**
7. **Pocket off:**
   - During a standoff it continues to ARMED.
   - ARMED stays ARMED.
   - The contact fires (tester, not a live load).
   - App DISARM and app ARM both work.
   - On Pocket return with SE held, nothing fires until SE is released and pressed again.
8. **App link loss** (stop the filter or drop the mesh) during a standoff: it arms anyway and stays ARMED. DISARM works once the link is back.
9. **LUX reboot while ARMED:**
   - The ESP32 stays ARMED and the contact fires during the outage.
   - After boot QGC shows "Safety ARMED at LUX boot, holding" and S1 is 1500.
   - App DISARM goes SAFE.
   - SB up since boot does not arm.
10. **FIRE before ARMED:** SE in SAFE and SE during standoff each latch Code 3, with no load.

Record the results in `safety-arbiter\BENCH_RESULTS_<date>.md`.

## Known behaviour (not bugs)
- **Power-up Code 5.** No valid pulses while the LUX boots, the same as before. Clear it with SW1 ENABLE then SAFE, or an SB up/down cycle.
- **LUX reboot during a standoff** faults the ESP32 (Code 5). Re-arm from scratch.
- **SW1 to SAFE during the post-reboot hold** can latch Code 5. Clear it as above.
- **Lost acknowledgment.** An accepted ARM whose acknowledgment is lost still arms. The spoken state is the check, and DISARM always wins.
- **The app can't arm while SE is held or invalid with the Pocket on.** The ESP32 rule is unchanged.

## Don'ts
- Don't modify or reflash the ESP32 firmware. Don't overwrite parameter backups or the old relay.
- Don't use QGC's vehicle Arm button for the safety device. Don't use DO_SET_SERVO on S1/S2.
- No flight, no live load, props stay off.
