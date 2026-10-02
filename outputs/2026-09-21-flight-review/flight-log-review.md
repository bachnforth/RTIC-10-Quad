# Flight-log review — 2026-09-21

## Finding

The aircraft performed a commanded battery-failsafe landing. It did not stop because of a GPS failure, radio loss, motor saturation, or mission-navigation error.

ArduPilot measured the standard 4S pack at about **15.02 V before takeoff**. Once airborne, its reported voltage fell to about 14.54 V, was 14.37 V when AUTO began, and crossed the configured **14.0 V critical threshold** during the outbound leg. After approximately 10 seconds below that threshold, ArduPilot declared `Battery 1 is critical`, raised `Battery Failsafe`, and changed from AUTO to LAND.

### Important correction after the initial review

Immediately after this review, the user connected the flight battery to the charger and reported **15.81 V**. After a short period of charging, the user paused the charger and obtained a simultaneous comparison: **15.74 V on a multimeter** while Mission Planner displayed **14.28 V**. The controller was therefore reporting only 90.72% of the measured voltage—**1.46 V low**, requiring a 1.10224 scale correction. The four charger cell readings were 3.963, 3.956, 3.959, and 3.958 V, a very good maximum spread of only **0.007 V**.

The diagnosis is therefore **confirmed voltage-scale calibration error causing a premature battery failsafe**, not evidence of a depleted or badly imbalanced pack. With the same scale error, the reported 13.96 V failsafe point corresponds to approximately **15.39 V actual**, or about **3.85 V/cell**. The aircraft landed with substantial charge remaining.

## Timeline

Times below are elapsed controller time from this log.

| Event | Time | Battery | Position/altitude |
|---|---:|---:|---|
| Armed | 48.4 s | 15.02 V | Launch point |
| AUTO selected | 59.9 s | 14.37 V | About 23 m above Home |
| Waypoint 3 reached | 114.4 s | 14.40 V | About 160 m from launch |
| First sustained sample below 14.0 V | 241.4 s | 14.00 V | Outbound leg |
| Critical battery failsafe; AUTO → LAND | 252.8 s | 13.96 V | About 575 m from launch and 19.5 m above Home |
| Touchdown/land detection sequence | 284.5–285.5 s | 14.07–14.09 V | About 575 m from launch |
| Disarmed | 286.8 s | 14.17 V | Landed |

The main outbound waypoint was about **1,056 m** from launch. The failsafe began about **575 m** from launch, which explains why the aircraft completed only a little over half of that leg. The aircraft landed about 34 seconds after the failsafe began.

## Battery-monitor configuration

- `BATT_MONITOR = 3`: analog voltage only.
- `BATT_CAPACITY = 5200`: nominal pack capacity, but it cannot be tracked without current measurement.
- `BATT_CRT_VOLT = 14.0` and `BATT_FS_CRT_ACT = 1`: critical voltage commands LAND.
- `BATT_LOW_TIMER = 10`: threshold must persist before the failsafe is declared.
- `BATT_LOW_VOLT = 0` and `BATT_LOW_MAH = 0`: there was no earlier low-battery warning/action.
- The log contains no valid current, consumed-mAh, remaining-percent, or energy data. The `used 0 mAh` message means **unmeasured**, not zero consumption.

The lowest recorded voltage was **13.54 V**, briefly near touchdown under motor load. It recovered to 14.17 V at disarm.

## Other flight-health observations

- GPS remained healthy: 17–25 satellites, HDOP 0.55–0.68, no GPS failsafe or position-loss event.
- Motor outputs retained substantial headroom; the highest was 1673 µs. There is no evidence that lack of thrust or output saturation caused the landing.
- Vibration was low for most of the flight and there were no IMU clipping events.
- The radio failsafe occurred after the aircraft had already landed and disarmed, so it did not cause the landing.
- The controller reported magnetic/yaw realignment during startup and one emergency yaw reset shortly after AUTO began. Navigation continued normally, but this should be checked at a magnetically clean outdoor location before another long autonomous flight.
- Outputs 2 and 4 averaged higher than outputs 1 and 3. There was still ample control headroom, but propeller type/orientation, motor/ESC condition, and center of gravity merit a physical check—especially in light of the previously reported motor twitch.

## Before another route flight

1. Do not repeat the 1 km route until the voltage measurement has been verified and corrected if necessary.
2. Stop or pause charging, disconnect the charger, and let the pack rest. Confirm that the charger recognized 4S and record all four individual cell voltages; inspect for a markedly low cell, swelling, damage, or abnormal resistance.
3. The simultaneous props-off comparison confirmed the scale error. After allowing the readings to stabilize and iterating the calibration, the final verified setting was **`BATT_VOLT_MULT = 11.18`** with both ArduPilot and the multimeter reading **15.63 V**. Retain the known-working voltage pin 13 and verify that the multiplier survives reboot/reconnection before arming.
4. Decide whether the installed hardware supports current sensing. If it does, configure and calibrate it before relying on mAh or remaining percentage. Do not simply change the monitor type without verifying the wiring and sensor.
5. Reinstate a deliberate nonzero low-battery warning/action, then tune both low and critical voltage thresholds from a short, close-in hover log using a fully charged, known-good pack. Keep the first validation over a clear landing area.
6. Check compass/magnetic conditions, props, motor/ESC behavior, and center of gravity before resuming autonomous distance testing.

## Source

- Preserved log: `00000002.BIN`
- SHA-256: `C67085AF5827446C8104A578766C3BCF9CD3DA88DF95695508CD798B3FFC8492`
