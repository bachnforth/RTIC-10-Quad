# 10-inch quad — workflow handover

## Purpose and current stopping point

Continue helping the user configure and troubleshoot a 10-inch ArduCopter quad for a hover test. Work one stage at a time. The user prefers concise, explicit Mission Planner instructions and does not want completed checks repeated. Do not assume that instructions given were actually executed unless confirmed below.

Latest confirmed update: the user **did not change the EKF failsafe threshold**. Instead, the user reports setting **`ARMING_MAGTHRESH = 200`** and **successfully completing the hover test**. Record this as user-reported completion; no flight log, duration, altitude, or detailed performance results have been supplied. Do not continue the earlier request to change `FS_EKF_THRESH` unless the user asks again. Its current numerical value remains unknown.

**Hover test completed successfully per user report; unresolved items remain:** one motor was reported twitching while disarmed, and no resolution has been reported. Diagnosis was paused at the user's request. Initial tuning and complete armed failsafe behavior are not verified. A successful hover does not establish that these issues are resolved or provide blanket clearance for further flight.

## Hardware and software

- FC: Lumenier LUX F765 NDAA, firmware target `LumenierLUXF765-NDAA`.
- Mission Planner 1.3.76; ArduCopter 4.7.1, git `dbe79216` (screenshots).
- Reported frame: `QUAD/X_REV`.
- Receiver: BETAFPV SuperD ELRS 2.4 GHz diversity, firmware 3.3.0 ae9df3; CRSF, 420000 UART baud; AirPort disabled, model match off.
- Transmitter: RadioMaster Pocket, ELRS packet rate 250 Hz. User uses the same transmitter model for a Hummingbird and does not want to change its channel directions.
- GNSS/compass: Matek M10Q-5883, u-blox SAM-M10Q and QMC5883L.
- Battery: standard 4S LiPo, 5200 mAh.
- Older build context: Rekon10 frame, XING2 3110 motors, 10-inch props; handover reportedly identifies a legacy Orqa 3030 4-in-1 BLHeli32 ESC. Actual ESC firmware has not been read/verified. Do not assume AM32 or propose cross-flashing.

## Verified completed work

### Receiver and radio

- Long-running no-RC issue was resolved when user powered the FC from **4S first, then USB**. The physical/firmware cause remains unproven. Use this known-working startup order.
- Initial receiver connection was the FC 4-pin receiver JST, physical UART7. A move to UART1 was discussed; whether this occurred was not conclusively established. Do not blindly change serial assignments now that RC works.
- Historical working/troubleshooting values: `SERIAL7_PROTOCOL=23`, `SERIAL7_OPTIONS=0`, `SERIAL7_BAUD=115`, `RC_OPTIONS=8224`, `RC_PROTOCOLS=1`, `RSSI_TYPE=3`. Do not treat these as a newly downloaded parameter snapshot.
- All sticks and switches move. Full radio calibration completed.
- Recorded ranges: CH1 990–2011; CH2 988–2010; CH3 994–2011; CH4 988–1988; CH5–8 approximately 999–2000.
- Yaw center about 1485; `RC4_TRIM=1484`, `RC4_DZ=20`.
- Arm switch CH8 off999/on2000; assignment previously directed: `RC8_OPTION=153` (Arm/Disarm). Physical arm/disarm behavior is not fully documented as tested.
- Mode switch CH7; user confirmed Stabilize in all three positions. Earlier configuration: `FLTMODE_CH=7`, `RC7_OPTION=0`, all six `FLTMODE` slots 0.
- User declined a separate emergency stop, believing arm/disarm serves that function. Do not equate normal disarm with a guaranteed immediate in-flight motor kill without verifying behavior.

### Pitch reversal — fixed and checked

- User reported forward pitch stick caused rearward pitch.
- Raw CH2 increases when stick is pushed forward. User wanted an aircraft-side correction to preserve Hummingbird transmitter settings.
- Changed **`RC2_REVERSED` from 0 to 1**, wrote settings and power-cycled (confirmed).
- Verified Mission Planner Status **`nav_pitch`: forward -30, rearward +30**. This is the correct interpreted nose-down/nose-up demand.
- Raw `ch2in` still increasing forward is expected; it is not evidence reversal failed. Do not reverse transmitter too, or change motor-output reversal to correct stick pitch.

### Compass, GPS, accelerometers

- Full accelerometer calibration confirmed completed. Horizon motion matched drone movement.
- Original compass IDs all zero and GPS `No GPS` were not explained by being indoors.
- User corrected a suspected wrong connector/UART; afterward GPS detected SAM-M10Q and displayed `No Fix`, compass detected.
- Reported wiring: Matek GND→GND; DA→SDA; CL→SCL; TX→RX3; RX→TX3; 5V→5V.
- Compass screenshot: QMC5883L, device ID855297, I2C bus0, address13; External checked; Missing unchecked; orientation None at that time.
- User completed outdoor compass calibration successfully, then rebooted. Compass pre-arm warning disappeared.
- Later indoor screenshots show GPS `No Fix`; no recent outdoor GPS fix evidence. Do not confuse `No Fix` with `No GPS`.

### Motors

- User explicitly confirms physically testing each motor's position and spin direction with props removed.
- Recent screenshots: `MOT_PWM_TYPE=0` (Normal PWM), `MOT_PWM_MIN=1000`, `MOT_PWM_MAX=2000`.
- `SERVO3_FUNCTION=35` (Motor3), `SERVO3_MIN=1100`, `SERVO3_MAX=1900`, `SERVO3_TRIM=1500`, `SERVO3_REVERSED=0`.
- These servo endpoint fields alone do not establish the cause of motor twitching; motor PWM range is separately configured. No changes were advised to these screenshots' settings.

### Radio failsafe

- Confirmed settings: `FS_THR_ENABLE=1`, `FS_THR_VALUE=975`, `RC_FS_TIMEOUT=1`, `FS_OPTIONS=16`.
- Meaning: radio-loss RTL, fallback Land if position unusable; FS_OPTIONS bit4 allows continued pilot control on GCS failsafe, not bypass of RC failsafe.
- Props-off **disarmed** transmitter-off test produced `FAILSAFE`, `PreArm: Radio failsafe on`; log included `Radio Failsafe - Disarming` and previous `Radio Failsafe Cleared`.
- User restored transmitter and confirmed radio failsafe cleared. Radio-loss detection/recovery verified; **do not claim airborne RTL/Land behavior was tested** based on this.
- Earlier screenshot throttle1136 prompted fully-low check; subsequent status screenshot had `ch3in=994`.

## Battery sensing — important firmware discrepancy

- Initially `BATT_MONITOR=0` and no voltage/failsafe parameters visible.
- Set and confirmed `BATT_MONITOR=3` (Analog Voltage Only).
- Published FC defaults say voltage pin12, multiplier10.1. With these correct values (user initially transposed them only in text), HUD and Status both read 0V. FC stayed powered from 4S with USB removed.
- Inspected **the running revision's source**, which labels PC2 current and PC3 voltage, but defines default voltage12/current13. MCU ADC mapping identifies PC2=12 and PC3=13 — an internal inconsistency.
- Changed **`BATT_VOLT_PIN=13`**, retained **`BATT_VOLT_MULT=10.1`** and monitor3, rebooted. User reported **13.59V**, then confirmed agreement with meter/cell check (“everything is consistent”). No individual readings supplied.
- Preserve **pin13**; do not reset to website pin12.
- Current sensing NOT configured/calibrated. Displayed amps, consumed mAh or percentage cannot be relied on.

### Battery failsafe values proposed, NOT confirmed saved

For a short nearby hover over a clear landing area, the assistant instructed:

| Parameter | Requested value |
|---|---:|
| BATT_CAPACITY | 5200 |
| BATT_LOW_VOLT | 14.4 |
| BATT_CRT_VOLT | 14.0 |
| BATT_FS_LOW_ACT | 1 (Land) |
| BATT_FS_CRT_ACT | 1 (Land) |
| BATT_LOW_TIMER | 10 |
| BATT_LOW_MAH | 0 |
| BATT_CRT_MAH | 0 |

These were described as conservative starting choices, not universal manufacturer thresholds. Capacity triggers disabled because voltage-only monitor has no consumption measurement. No user confirmation of writing these settings yet.

User asked minimum starting voltage: recommended standard 4S LiPo balance charge to **16.8V total /4.20V per cell**, not LiHV. Explained lower voltage cannot guarantee test endurance and 14.4/14.0 are landing triggers, not starting targets. Last measured13.59V is unsuitable for starting this test. **Fresh charge has not been confirmed.**

## Open motor twitch diagnosis — paused

User says “motor #3” twitches on bench while disarmed without input. Prop presence was not explicitly confirmed at that moment; instructions were to remove props with power disconnected, not arm, and pause flight.

Already received motor parameters listed above. Still missing:

1. Which physical corner (top view, nose forward) is twitching? Avoid confusing logical Motor3, output3, or motor-test letter.
2. Immediate on power-up or only after idle delay? Rhythmic with beep or irregular/silent?
3. Does Status `ch3out` remain1000 during twitch or change? Ideally compare ch1out–ch4out.

Steady telemetry output does not exclude brief electrical glitches. Possible ESC tones/beacon versus signal/ESC/motor fault have not been established. Do not declare a failed ESC or randomly adjust protocol, motor minimum, or flash firmware. No powered probing, signal swaps, or isolation tests performed yet.

## Magnetic arming threshold update and completed hover

- User asked to “adjust magnetic variance wider.” Assistant distinguished calibration Fitness (acceptance of calibration fit) from EKF magnetic variance (live sensor disagreement).
- Calibration already passed; no evidence to relax Fitness.
- Earlier discussion concerned increasing **`FS_EKF_THRESH`**, but the user subsequently clarified that **the EKF failsafe was NOT adjusted**. Its numerical value was never provided.
- Actual user-reported change: **`ARMING_MAGTHRESH = 200`**. Its prior value and the exact triggering warning were not supplied.
- User reports **successfully completing the hover test** after this change. Do not describe the first hover as still pending.
- This is a magnetic arming-check parameter change, not the previously discussed EKF failsafe threshold change. Do not conflate it with calibration Fitness, innovation gates, or magnetic declination. Verify the parameter's exact semantics against the running firmware if further advice is requested.
- The original magnetic-warning cause has not been diagnosed. No flight log or detailed test observations have been reviewed, and the successful hover does not independently validate the relaxed arming threshold.

## Remaining follow-up items after reported successful hover

- Resolve the previously reported uncommanded motor twitch before further flight; no fix has been reported.
- If continuing flight assessment, obtain the hover log and observations, and review the magnetic arming-check issue. Do not re-run the first-hover workflow as though the reported successful test never occurred.
- Verify battery charge and saved failsafe settings; verify battery failsafe behavior safely without deliberately deep-discharging pack.
- Verify arming/disarming behavior and remaining failsafe behavior proportionately; do not use high-throttle bench tests casually.
- Check actual initial tuning for 10-inch props, supported ESC setup/calibration, mechanical condition/prop fitting, reliable battery-only startup, and appropriate outdoor flight conditions.
- Do not claim all pre-arm checks passed merely because one screenshot lacked warning text.
- Compass/accelerometer calibrations, motor position/direction checks, and RC calibration are already confirmed; only revisit with new evidence.

## References

- FC docs: https://ardupilot.org/copter/docs/common-luxf765-ndaa.html
- Running-revision hwdef: https://raw.githubusercontent.com/ArduPilot/ardupilot/dbe79216/libraries/AP_HAL_ChibiOS/hwdef/LumenierLUXF765-NDAA/hwdef.dat
- ADC mapping: https://raw.githubusercontent.com/ArduPilot/ardupilot/dbe79216/libraries/AP_HAL_ChibiOS/hwdef/scripts/STM32F767xx.py
- Matek: https://www.mateksys.com/?portfolio=m10q-5883
- Radio failsafe: https://ardupilot.org/copter/docs/radio-failsafe.html
- Battery failsafe: https://ardupilot.org/copter/docs/failsafe-battery.html
- Compass calibration: https://ardupilot.org/copter/docs/common-compass-calibration-in-mission-planner.html
- EKF failsafe: https://ardupilot.org/copter/docs/common-ekf-inav-failsafe.html
- Pre-arm checks: https://ardupilot.org/copter/docs/common-prearm-safety-checks.html
- PWM ESC setup: https://ardupilot.org/copter/docs/common-brushless-escs.html
- Motor tests: https://ardupilot.org/copter/docs/connect-escs-and-motors.html

## Local files and environment

- Workspace: `C:\Users\ebach\Documents\ChatGPT\10 inch Quad`
- Original build handover: `C:\Users\ebach\Desktop\10 inch Project\10-inch-FPV-drone-build-handover.docx`
- Old receiver troubleshooting log: `C:\Users\ebach\Documents\Mission Planner\logs\QUADROTOR\1\1 12-31-1969 7-00-00 PM.bin` — predates fixes, not current flight evidence.
- Firmware file referenced by user: `C:\Users\ebach\Downloads\LUXNDAAF7_arducopter_4.5.7_with_bl+1.hex` — not evidence this version is running.
- Board manual URL: https://getfpv-media.s3.us-east-1.amazonaws.com/wysiwyg/files/Lumenier_LUX_F765_FC_NDAA_User_Manual_v1.pdf
- Windows screenshots are in `C:\Users\ebach\AppData\Local\Temp\codex-clipboard-*.png`; request a relevant fresh view when needed.

This file records conversation evidence and proposed next steps; it is not a live parameter download or authority to arm, fly, flash firmware, or bypass safety checks.
