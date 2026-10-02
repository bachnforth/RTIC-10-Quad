# Safety arbiter: Pocket + QGC control of the ESP32 safety device

Training exercise. Props off and load disconnected for everything below.

## What it does

A Lua script on the LUX F765 becomes the single source of the ESP32's S1 (ARM)
and S2 (FIRE) pulses. The ESP32 firmware
(`esp32_safety_device_phase10_linkloss_hold`) is **unchanged**.

| Event | ARM request | S1 |
|---|---|---|
| LUX boot | cleared | 1500 (hold) until ESP32 status is read; then 1100 unless the ESP32 reports ARMED |
| SB released -> up (SB must be seen released first) | set | 1900 |
| SB up -> released | cleared | 1100 |
| QGC "Safety ARM 1/2: request", then "2/2: confirm" within 10 s | set | 1900 |
| QGC "Safety DISARM" (even with SB up) | cleared | 1100 |
| Pocket link lost | unchanged: standoff continues, ARMED stays ARMED | unchanged |
| QGC / mesh link lost | unchanged | unchanged |
| Script stopped (v3: verified on hardware) | - | 1500 within 0.3 s (ESP32 holds ARMED, contact still fires) |
| LUX rebooting | - | no pulses, then 1500 until status is read (ESP32 holds ARMED) |

S2 (FIRE): SE passes through while the Pocket link is valid. While it is lost,
and after it returns until SE has been seen released, S2 is 1100 (released).
QGC never sends FIRE. The deflection contact is handled entirely by the ESP32:
once ARMED it fires regardless of any link.

To re-arm after an app DISARM while SB is up, move SB down, then up. To disarm
from the Pocket after an app ARM (SB down), move SB up, then down.

QGC's own Arm/Disarm still controls only the motors, and the Pi filter blocks it.

## Files

| File | Goes to |
|---|---|
| `safety_arbiter.lua` | LUX SD card `APM/scripts/` |
| ArduPilot 4.7.1 `libraries/AP_Scripting/modules/MAVLink/mavlink_msgs.lua`, `mavlink_msg_COMMAND_LONG.lua`, `mavlink_msg_COMMAND_ACK.lua` | LUX SD card `APM/scripts/modules/MAVLink/` |
| `safety_arbiter_delta.param` | LUX parameters (after a full backup) |
| `SafetyDevice.json` | Galaxy: `Android/data/org.mavlink.qgroundcontrol/files/QGroundControl/MavlinkActions/` |
| `pi/safety_mavlink_filter.py` | Pi (needs `pymavlink`) |
| `sim/` | SITL test harness and results; not installed anywhere |

## Wiring (two additions; S1/S2 are unchanged)

All new LUX pads are on the **bottom** side, along the bottom edge.

1. **ESP32 status to LUX:** ESP32 GPIO1 (U0TXD, the USB-serial TX) through a
   1 kOhm series resistor to the LUX **RX5** pad (second row, between TX6 and
   TX5). Leave TX5 empty. Ground is already common through the S1/S2 harness.
   The resistor limits current if the ESP32 is powered while the LUX is not.
   USB serial on the ESP32 keeps working.
2. **LUX to Pi:** Pi GPIO14 / TXD (header pin 8) to LUX **RX1**; Pi GPIO15 /
   RXD (header pin 10) to LUX **TX1** (bottom-right group). Ground is already
   common. 115200 baud.

**RX6/TX6, right next to RX5, is the ELRS receiver (SERIAL8).** Do not bridge
them. SERIAL3/4/5/6/8 are in use; leave them alone.

## Pi setup (before connecting the LUX)

Verify on the Pi first; the saved copies in this folder are from 2026-09-11.

1. Remove `console=serial0,115200` from `/boot/firmware/cmdline.txt`, so the
   Pi stops sending a login console out of pins 8/10.
2. Add `enable_uart=1` to `/boot/firmware/config.txt` (steadies the mini-UART
   clock). Keep backups of both files. Reboot.
3. Install pymavlink, then run the filter:
   `python3 safety_mavlink_filter.py --serial /dev/serial0 --baud 115200 --udp-target 10.223.58.11:14550`
4. In QGC, add a UDP link listening on 14550 (it may connect automatically).

## Install order

1. Save a full LUX parameter backup (new file, dated). Keep the existing backups.
2. Copy the script and the three MAVLink modules to the SD card.
3. Load `safety_arbiter_delta.param`, then reboot the LUX.
4. Confirm the QGC message `Safety arbiter running, ARM request cleared`.
5. Copy `SafetyDevice.json` to the phone. In QGC: Application Settings, Fly
   View, set the MAVLink actions file to `SafetyDevice.json`, then restart QGC.
6. On the Pi, run the filter against the LUX serial port and the mesh address.

## Fly View panel (v3)

The arbiter sends GENERATOR_STATUS at 2 Hz (this vehicle has no generator):

| Field (QGC group "Generator") | Meaning |
|---|---|
| status | ESAD state: 0 SAFE, 1 STANDOFF, 2 ARMED, 3x FAULT with code x, 9 no status |
| runtime | standoff seconds remaining (0 otherwise) |

Suggested colour ranges for status (QGC picks the first range the value is <= to; "no value" uses the first colour, so the first is grey): values -1, 0, 1, 2, 9 with colours grey, green, yellow, red, grey, and orange above 9.

All Safety messages are INFO (silent, listed in QGC messages). Only "Safety ARBITER STOPPED" is CRITICAL.

## QGC 5.0.8 notes

- The three actions are in the Fly View **Actions** list. QGC sends them on
  tap, with no slide-to-confirm, so ARM is two steps.
- Each action shows an error in QGC if the LUX does not acknowledge it.
- An acknowledgment is not proof. The ESP32's own state is reported as spoken
  messages ("Safety standoff 31", "Standoff 20", "10", "5"..."1", "Safety
  ARMED", "Safety SAFE", "Safety FAULT ...") and as NAMED_VALUE_FLOAT
  `SD_STATE` (0 SAFE, 1 STANDOFF, 2 ARMED, 3 FAULT, -1 unknown), `SD_CD`
  (countdown), `SD_REQ` (1 ARM requested, 2 boot hold) and `SD_TXOK`,
  visible in Analyze Tools, MAVLink Inspector.
- "Safety status LOST" means the status wire has been silent for 3 s; the app
  then no longer knows the device state.

## Known behaviour to be aware of

- **Power-up Code 5.** While the LUX boots it sends no valid pulses, so an ESP32
  in SAFE latches Code 5, as it does today. Clear it with SW1 (ENABLE, then
  SAFE) or an SB up/down cycle.
- **LUX reboot during a standoff** faults the ESP32 (Code 5). Re-arm from scratch.
- **SW1 to SAFE while the arbiter is in boot hold** can latch Code 5 before the
  next status line. Clear it as above.
- An ARM that is accepted but whose acknowledgment is lost still arms. The
  spoken state and the 31 s standoff are the check; DISARM always wins.
- SB in a middle position (if the switch has one) is ignored rather than
  treated as invalid.

## Bench validation (props off, load disconnected)

Run each and record the ESP32 serial JSON alongside what QGC reports.

1. Boot defaults: arbiter message, `SD_REQ=0`, S1 1100 after status, no arm.
2. SB-only: arm, full 31 s standoff, ARMED, SB down to SAFE.
3. App-only: CONFIRM alone denied; request then wait 11 s then CONFIRM denied;
   request + confirm arms after 31 s.
4. Conflicts: SB up then app DISARM stays SAFE with SB up; SB cycle re-arms;
   app ARM then SB up/down disarms.
5. Standoff timed at 31.5 s from S1 asserting (500 ms sustain + 31 s).
6. App DISARM while ARMED.
7. Pocket off: during standoff it continues; ARMED stays; contact fires; app
   DISARM and app ARM both work; on Pocket return with SE held, no fire until
   SE is released and pressed again.
8. App link loss (stop the Pi filter or drop the mesh) during standoff: arms
   anyway; stays ARMED; DISARM works once the link is back.
9. LUX reboot while ARMED: ESP32 stays ARMED and the contact fires during the
   outage; after boot QGC shows "Safety ARMED at LUX boot, holding" and S1 is
   1500; app DISARM goes SAFE; SB up since boot does not arm.
10. FIRE before ARMED: SE in SAFE and during standoff latch Code 3, no load.

Also measure S1/S2 with a scope in each state: 50 Hz, 1100/1500/1900 us only.

## SITL result (2026-09-28)

ArduCopter 4.7.1 SITL (Mission Planner build) with the Pi filter in the loop
and a Python port of the ESP32 firmware (`sim/esp32_model.py`): **58/58 checks
passed** (`sim/results/`). Tested script SHA-256:
`05b49ed641383ef5264fa0aece1278f06b29574d633fcb315d57d48d1b4e4432`.
Measured S1-assert to ARMED: 31.50-31.53 s. `sim/results_run1/` is the first
run (56/57, one harness ACK-matching bug, since fixed).

SITL proves the script logic and message flow only. It does not prove real
pulse timing, the UART wiring, QGC on the phone, or the mesh. Those are the
bench tests above.
