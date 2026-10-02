# LUX F765 + ESP32 Safety Demonstrator Integration Plan

Date: 2026-09-15  
Aircraft: 10-inch quad, Lumenier LUX F765 NDAA, ArduCopter 4.7.1  
Scope: inert/current-limited coursework demonstrator only

Revision note: SE and the deflection sensor are equal alternate FIRE paths.
The current proven SE implementation fires from one valid press after ARMED.

## 1. Objective and fixed boundaries

Integrate the existing ESP32 safety demonstrator with the 10-inch quad while
adding a deflection-actuated contact sensor as an alternate FIRE mechanism. The
LUX provides two validated 50 Hz PWM command signals. The ESP32 remains the
independent state-machine controller and directly monitors the mechanical
sensor.

This plan does not qualify the system for a pyrotechnic, energetic, propulsion,
weapon, or other hazardous load. All initial work uses an active buzzer or
similarly current-limited inert load. The existing PCB and firmware are
explicitly documented as a bench demonstrator rather than a flight-certified
safety controller.

Do not change the quad's four motor outputs, frame type, receiver UART, flight
mode channel, aircraft arming channel, motor protocol, or calibrated flight
parameters as part of this integration.

### Existing aircraft configuration to preserve

| Item | Recorded configuration |
|---|---|
| Flight controller | Lumenier LUX F765 NDAA |
| Firmware | ArduCopter 4.7.1 |
| Frame | `QUAD/X_REV` |
| Motor outputs | M1-M4 |
| Motor protocol | Normal PWM (`MOT_PWM_TYPE=0`) |
| Receiver | ELRS/CRSF |
| Flight modes | RC channel 7 |
| Aircraft arm/disarm | RC channel 8 |
| Proposed safety-device ARM | RC channel 6 |
| Proposed safety-device FIRE | RC channel 9 |

### Hard stop before prop-on work

The previously reported disarmed motor twitch has not been resolved. Complete
the electrical/firmware integration with all propellers removed. Do not start a
prop-on carriage or flight test until the twitch is diagnosed and the aircraft
has passed its ordinary flight-readiness checks independently of this device.

## 2. Adopt the integration architecture

Use this signal and power architecture:

```text
RadioMaster Pocket
       |
       | ELRS/CRSF: CH6 ARM, CH9 FIRE
       v
LUX F765 NDAA
  S1 / output 9  ---- protected 50 Hz PWM ----> ESP32 GPIO22 (REMOTE_ARM)
  S2 / output 10 ---- protected 50 Hz PWM ----> ESP32 GPIO21 (REMOTE_FIRE)
  GND             ----------------------------> ESP32/PCB GND

Deflection SPDT NC ---- protected input ------> ESP32 GPIO25
Deflection SPDT NO ---- protected input ------> ESP32 GPIO26
                                       (supervised alternate FIRE input)

4S battery ---- fused, filtered 5 V BEC ------> ESP32 5 V/VIN
ESP32 state machine --------------------------> inert/current-limited load
```

S1 and S2 are outputs 9 and 10. They form one output-timer group on this board,
which is suitable because both signals require the same normal PWM protocol.

The contact sensor connects to the ESP32 rather than the LUX. This preserves
local monitoring if the flight controller reboots and avoids consuming another
flight-controller output.

## 3. Define the alternate-FIRE behavior before changing firmware

For this plan, "same circuit as SE" means that both paths ultimately command
the same ESP32 `LOAD_GATE` output and the same FIRED latch. It does **not** mean
electrically connecting the switch to the LUX S2/GPIO21 PWM conductor. GPIO21
expects a valid 50 Hz pulse train; opening or grounding that line would create
a remote-input fault rather than a valid FIRE request.

Use these requirements for the inert demonstrator:

1. SE and the deflection sensor are equal, concurrently available alternate
   FIRE inputs. The sensor is not a backup that waits for SE to fail.
2. The existing proven SE behavior remains unchanged: after the 31-second
   buffer reaches ARMED, one valid SE press enters FIRED.
3. The deflection sensor is a separate, supervised alternate FIRE path.
4. A valid deflection has no authority until the physical switch is ENABLE,
   remote ARM is asserted, both LUX PWM signals are valid, and the complete
   31-second buffer has reached ARMED.
5. Once ARMED, one continuously valid deflection lasting at least 100 ms enters
   the same FIRED state and energizes the same inert-load output as a completed
   single SE press.
6. Deflection before ARMED is a premature alternate-FIRE request. It keeps the
   load off, cancels the buffer, clears pending FIRE input state, and latches a
   `CONTACT_FIRE_FAULT`.
7. Releasing the sensor after it caused FIRED does not clear the FIRED latch,
   matching the existing SE behavior. Local SAFE or remote DISARM clears the
   output immediately.
8. After clearing, the sensor must return to a valid normal/undeflected state
   before a new arming sequence is accepted. A sensor held deflected through a
   reset cannot refire automatically.
9. LOW/LOW or HIGH/HIGH complementary readings are wiring faults, not FIRE
   requests. They immediately force the load off and latch `CONTACT_FAULT`.

This alternate automatic path remains limited to the buzzer/current-limited
dummy load. It is not authorization to attach an operational or hazardous load.

## 4. Freeze and document the working aircraft first

1. Remove all four propellers and label them by motor position before storage.
2. Disconnect any safety-device load supply.
3. Save a complete Mission Planner parameter file with a date-stamped name.
4. Save the RadioMaster model to the SD card or EdgeTX Companion.
5. Read back and archive the exact ESP32 sketch currently installed, or identify
   the exact source file and commit from which it was flashed. The attached
   Day 9 handover describes a three-press/500 ms gesture, while the user confirms
   that the current proven design fires from one SE press. Treat the verified
   single-press implementation as the source of truth and do not base the new
   revision on the conflicting Day 9 behavior.
6. Bench-test and record the current timing from a valid SE press to the inert
   load output before altering the sketch.
7. Photograph the LUX top and bottom, every connector, and the M1-M4 wiring.
8. Record the current values of:
   - `SERVO1_FUNCTION` through `SERVO12_FUNCTION`;
   - `SERVO_RC_FS_MSK`;
   - `MOT_PWM_TYPE`, `MOT_PWM_MIN`, and `MOT_PWM_MAX`;
   - `RC6_MIN/TRIM/MAX` and `RC9_MIN/TRIM/MAX`;
   - `RC7_OPTION`, `RC8_OPTION`, and `FLTMODE_CH`;
   - all `SERVO_BLH_*` and `SERVO_DSHOT_*` parameters that exist.
9. Confirm Mission Planner still displays the correct board target and
   ArduCopter version.
10. Confirm S1 and S2 are physically unused.
11. Do not proceed if either output is already assigned to another accessory.

Acceptance gate: a dated parameter backup, radio backup, exact single-press
ESP32 source backup, baseline timing record, photographs, and an
output-assignment record exist before anything is rewired.

## 5. Prepare a dedicated transmitter model

The user uses related transmitter settings for another aircraft, so do not edit
the shared working model in place.

1. Duplicate the known-working 10-inch quad model on the RadioMaster Pocket.
2. Give the duplicate an unambiguous name such as `10IN-SAFE-BENCH`.
3. Preserve sticks, channel reversals, rates, flight modes, and CH8 aircraft
   arm/disarm exactly as they are.
4. Assign a two-position safety ARM switch to CH6:
   - OFF/released: approximately 1000-1100 us;
   - ON/asserted: approximately 1900-2000 us.
5. Assign the momentary control intended for FIRE to CH9:
   - released: approximately 1000-1100 us;
   - pressed: approximately 1900-2000 us.
6. Add clear transmitter labels distinguishing aircraft ARM (CH8) from
   safety-device ARM (CH6).
7. Start every test with aircraft disarmed, safety ARM off, FIRE released, and
   the physical safety switch at SAFE.
8. In Mission Planner's Radio Calibration or Status view, verify that CH6 and
   CH9 move correctly and independently while CH7 and CH8 remain unchanged.

Acceptance gate: CH6 and CH9 reach both endpoint bands, neither changes any
flight-control channel, and the original transmitter model remains untouched.

## 6. Configure the two LUX auxiliary PWM outputs

Carry out this phase with propellers removed and the ESP32 disconnected.

1. Use the aircraft's known working startup order: connect the 4S battery first,
   then USB if Mission Planner is needed.
2. Connect Mission Planner and save another pre-change parameter file.
3. Confirm output 9/S1 and output 10/S2 are unused.
4. Configure output 9/S1 as the scaled CH6 signal:

   ```text
   SERVO9_FUNCTION  = 145   # RCIN6Scaled
   SERVO9_MIN       = 1100
   SERVO9_TRIM      = 1500
   SERVO9_MAX       = 1900
   SERVO9_REVERSED  = 0
   ```

5. Configure output 10/S2 as the scaled CH9 signal:

   ```text
   SERVO10_FUNCTION = 148   # RCIN9Scaled
   SERVO10_MIN      = 1100
   SERVO10_TRIM     = 1500
   SERVO10_MAX      = 1900
   SERVO10_REVERSED = 0
   ```

6. Set or retain:

   ```text
   SERVO_RC_FS_MSK  = 288
   ```

   `288` selects the RCIN6Scaled and RCIN9Scaled source-function bits. It is
   not an output-number mask, so moving the signals to outputs 9 and 10 does
   not change this value to 1536. During radio failsafe, these scaled pass-through
   signals go to their 1500 us trim value, which the ESP32 deliberately treats
   as invalid.
7. Ensure the S1/S2 group remains normal PWM, not DShot. Do not add outputs 9
   or 10 to a BLHeli/DShot mask.
8. Do not change M1-M4, `MOT_PWM_TYPE`, or ESC calibration during this phase.
9. Write the parameters and reboot the flight controller.
10. Check the startup messages for the reported output protocol groups.
11. Measure S1 and S2 with an oscilloscope or logic analyzer:
    - frequency close to 50 Hz;
    - CH6 off: approximately 1100 us on S1;
    - CH6 on: approximately 1900 us on S1;
    - CH9 released: approximately 1100 us on S2;
    - CH9 pressed: approximately 1900 us on S2;
    - radio loss: approximately 1500 us or missing pulses, never 1900 us.

Acceptance gate: both waveforms are independently correct, motor outputs and
flight-control channels are unchanged, and radio loss cannot produce an
asserted command.

## 7. Build the LUX-to-ESP32 signal harness

Use S1 signal, S2 signal, and one ground only. Do not connect a servo/accessory
positive conductor from the LUX to the ESP32 PCB.

```text
LUX S1 signal ---- 1 kohm ----+---- ESP32 GPIO22 (REMOTE_ARM)
                              |
                            10 kohm
                              |
                             GND

LUX S2 signal ---- 1 kohm ----+---- ESP32 GPIO21 (REMOTE_FIRE)
                              |
                            10 kohm
                              |
                             GND

LUX ground -------------------+---- ESP32/PCB ground
```

1. Put each 10 kohm pull-down on the ESP32 side of its 1 kohm series resistor.
2. Place the resistor pairs close to the ESP32 connector.
3. Use a keyed or locking connector labeled `ARM`, `FIRE`, and `GND`.
4. Omit or physically block any unused positive-voltage position.
5. Twist each signal with a ground return where harness construction permits.
6. Route the harness away from battery leads, ESC phase wires, VTX wiring, and
   receiver antennas.
7. Provide strain relief at both boards.
8. With both controllers unpowered, verify:
   - no continuity from either signal to battery or accessory voltage;
   - approximately 10 kohm from each protected input to PCB ground;
   - ground continuity between boards;
   - S1 reaches only GPIO22 through 1 kohm;
   - S2 reaches only GPIO21 through 1 kohm.

Acceptance gate: the harness passes all unpowered continuity checks and cannot
be shifted onto an unintended power pin.

## 8. Select and mechanically install the deflection sensor

1. Use a sealed, snap-action SPDT microswitch with separate COM, NC, and NO
   terminals. A roller-lever version is preferred when a flexible probe or
   moving surface provides the deflection.
2. Select contact ratings for low-current logic service; the contacts must not
   carry the inert load current.
3. Design a mechanical stop so the switch cannot be over-traveled or crushed.
4. Make the switch position adjustable so the actuation threshold can be set
   without bending its lever permanently.
5. Keep the switch, lever, and deflecting member outside every propeller arc at
   maximum flexure.
6. Ensure the deflecting member cannot enter a motor, propeller, GPS/compass,
   receiver antenna, or power harness after impact or vibration.
7. Use a mount that cannot rotate into the propeller plane.
8. Add connector strain relief and a service loop that cannot snag.
9. Record the intended direction, minimum required travel, maximum travel, and
   approximate actuation force.

Acceptance gate: full mechanical travel is repeatable, positively limited, and
clear of all propulsion and navigation hardware.

## 9. Wire the complementary contact inputs

Use GPIO25 and GPIO26 unless the final PCB review identifies an existing use.

```text
                         ESP32 3.3 V
                              |
                         switch COM
                         /          \
                switch NC          switch NO
                    |                   |
                  1 kohm              1 kohm
                    |                   |
             ESP32 GPIO25       ESP32 GPIO26
                    |                   |
                 10 kohm             10 kohm
                    |                   |
                   GND                 GND
```

1. Place the 1 kohm series resistors and 10 kohm pull-downs close to the ESP32.
2. Optionally fit 10-100 nF from each protected input to ground for local RF
   suppression; use equal values on both inputs.
3. Do not rely only on ESP32 internal pulls.
4. Label both signals by contact function rather than wire color alone.
5. Before connecting the ESP32, use a meter to confirm:
   - normal/undeflected: NC path closed, NO path open;
   - actuated/deflected: NC path open, NO path closed;
   - no terminal is shorted to the switch body or airframe.
6. Power only the ESP32 and verify the protected input voltages:
   - normal: GPIO25 near 3.3 V and GPIO26 near 0 V;
   - deflected: GPIO25 near 0 V and GPIO26 near 3.3 V.

Interpret the two inputs as:

| GPIO25 / NC | GPIO26 / NO | Interpretation |
|---:|---:|---|
| HIGH | LOW | Valid normal/undeflected |
| LOW | HIGH | Valid deflection |
| LOW | LOW | Invalid/open/transition/disconnected |
| HIGH | HIGH | Invalid/shorted |

Acceptance gate: every physical and disconnected-wire condition produces the
expected truth-table state.

## 10. Revise the ESP32 firmware

Create a new firmware revision from the identified, bench-verified single-press
source. Do not overwrite that source or substitute the conflicting Day 9
three-press sketch. Preserve a buildable copy of both for traceability.

1. Add named inputs:

   ```cpp
   constexpr uint8_t CONTACT_NC = 25;
   constexpr uint8_t CONTACT_NO = 26;
   ```

2. Configure both as `INPUT`; the external pull-downs define their disconnected
   state.
3. Add a contact decoder with three results:
   - `NORMAL` for HIGH/LOW;
   - `DEFLECTED` for LOW/HIGH;
   - `INVALID` for LOW/LOW or HIGH/HIGH.
4. Add a short stable-state filter. Start with 25-50 ms for contact bounce and
   require a valid deflection to remain continuously stable for 100 ms before
   accepting the alternate contact FIRE request. A shorter pulse must not fire.
   Treat any raw invalid complementary reading as an immediate output inhibit while
   the filter decides whether to latch the wiring fault.
5. Add `CONTACT_FIRE_FAULT` and `CONTACT_FAULT` states or equivalent explicit
   flags. Do not merge them with the existing remote-PWM fault because their
   recovery evidence is different.
6. At the beginning of every loop, continue setting the load output LOW by
   default.
7. Before either alternate FIRE path can authorize the load, require
   complementary local SAFE/ENABLE contacts valid, both LUX PWM commands valid
   and fresh, remote ARM asserted, the local switch at ENABLE, and the state
   machine already in ARMED.
8. Implement two equal, always-available routes from ARMED to the same FIRED
   state. Do not add failure-detection or priority logic between them:
   - radio route: one valid SE press while the contact sensor remains valid;
   - contact route: a valid DEFLECTED contact state remains continuous for
     at least 100 ms. One qualifying deflection is sufficient.
9. A confirmed deflection in LOCKED, READY_SAFE, or BUFFER must keep the output
   off, cancel the countdown, clear every pending FIRE input state, and enter
   `CONTACT_FIRE_FAULT`.
10. A confirmed deflection in ARMED enters FIRED. A deflection in FIRED leaves
    the existing latch set. Releasing the sensor alone does not clear it.
11. A confirmed invalid complementary state must immediately turn the load off,
    cancel all progress, and enter `CONTACT_FAULT`, including from FIRED.
12. Recovery from either contact fault must require all of the following
    simultaneously:
    - contact sensor valid and normal;
    - physical local switch at SAFE;
    - remote ARM released;
    - remote FIRE released.
13. Recovery must return to startup lockout or `READY_SAFE`; it must never
    resume elapsed countdown time or a pending FIRE input.
14. Add distinct OLED messages and LED patterns for premature contact FIRE
    versus contact wiring fault.
15. Preserve the existing 250 ms stale-PWM check, invalid 1251-1749 us band,
    31-second buffer, and proven single-press SE behavior.
16. Compile the new sketch and retain compiler output with the test record.

Acceptance gate: a code review can trace exactly two equal routes from ARMED to
FIRED (one valid SE press or stable valid deflection) and show that contact
invalidity, local SAFE, remote DISARM, and invalid PWM dominate both routes.

## 11. Give the ESP32 a suitable power supply

1. Use a dedicated regulated 5 V BEC rated for a 4S input and for the combined
   ESP32, OLED, LEDs, and inert-load demand with at least 50% current margin.
2. Add an appropriately sized branch fuse near the battery/PDB connection.
3. Do not use the LUX 10 V VTX rail, raw 4S voltage, or an output signal header
   to power the ESP32.
4. Add input and output filtering recommended by the BEC manufacturer.
5. Join the LUX and ESP32 grounds through the documented signal-reference
   connection; avoid multiple long parallel ground returns.
6. Measure 5 V at the ESP32 during boot, OLED updates, LED changes, and inert
   load activation.
7. Confirm that unplugging or brownout-resetting the ESP32 leaves the load off.
8. Confirm that an ESP32 reset while ARM/FIRE are asserted starts in lockout and
   cannot restore a previous FIRED state.

Acceptance gate: no reset, undervoltage, or cable disconnection energizes the
load, and ESP32 power disturbances do not reset the LUX or receiver.

## 12. Run the isolated contact-sensor test suite

Use USB power and the inert buzzer only. Leave the LUX disconnected.

1. Boot with the sensor normal: startup lockout remains until the existing
   complete safe condition is observed.
2. Boot with the sensor deflected: load remains off and premature contact FIRE
   is reported; restoring the sensor alone must not arm or fire.
3. Boot with either contact wire disconnected: load remains off and a contact
   fault is reported.
4. Boot with both sense inputs shorted high: load remains off and a contact
   fault is reported.
5. With test-generated valid ARM/FIRE PWM, deflect during LOCKED, READY_SAFE,
   and BUFFER. Verify the load remains off, progress is discarded, and
   `CONTACT_FIRE_FAULT` latches.
6. Reach ARMED with remote FIRE released. Apply one valid continuous deflection
   shorter than 100 ms; verify it does not fire.
7. Repeat with one valid continuous deflection of at least 100 ms; verify it
   enters the same FIRED state and drives the same inert-load output as one SE
   press. Confirm this works without attempting or declaring an SE-path failure.
8. Release the sensor; verify FIRED remains latched until local SAFE or remote
   DISARM.
9. While FIRED, force an invalid complementary reading; verify immediate
   load-off and `CONTACT_FAULT`.
10. Release the sensor without performing the complete reset sequence; confirm
    authorization does not return.
11. Perform the complete reset sequence with the sensor valid and normal;
    confirm the device returns only to the initial safe state.
12. Tap, shake, and vibrate the sensor mount without reaching its mechanical
    threshold; verify there are no false FIRE requests.
13. Exercise the switch repeatedly and record bounce/stable timing. Adjust the
    mechanical geometry before lengthening software filters.

Acceptance gate: the contact can fire only from ARMED after 100 ms of continuous
valid deflection; every premature, wiring-fault, latch, and reset case passes
twice in succession with no unexplained transition.

## 13. Run the integrated LUX/ESP32 command tests

Keep every propeller removed and use only the inert load.

1. Connect S1, S2, and ground; leave the dedicated load supply off initially.
2. Start with aircraft disarmed, safety ARM off, FIRE released, local SAFE, and
   contact sensor normal.
3. Power the aircraft from 4S, then connect USB if needed.
4. Confirm the ESP32 receives approximately 1100 us on both channels.
5. Test CH6 alone and CH9 alone; neither may activate the load.
6. Verify CH8 aircraft arm/disarm remains independent and does not change S1 or
   S2.
7. Run the complete existing 31-second and single-press SE inert sequence with
   the sensor normal. Confirm the proven manual path still works unchanged.
8. Reset, repeat the 31-second buffer with SE released, then hold the sensor in
   valid deflection for at least 100 ms. Confirm it enters the same FIRED state
   and energizes the same inert output.
9. Repeat both routes in alternating order. Confirm both remain available on
   every valid arming cycle and neither depends on detecting failure of the
   other.
10. Release the sensor and confirm the output remains latched until local SAFE or
   remote DISARM.
11. Deflect during the countdown. Confirm the load stays off and the premature
    contact-FIRE fault requires the complete reset sequence.
12. Present an invalid contact state during ARMED and FIRED. Confirm immediate
    load-off and a distinct contact-wiring fault.
13. Repeat with the following injected failures, one at a time:
    - transmitter off;
    - receiver power removed;
    - LUX rebooted;
    - S1 disconnected;
    - S2 disconnected;
    - LUX/ESP32 signal ground disconnected;
    - either contact wire disconnected;
    - ESP32 reset;
    - ESP32 BEC removed and restored.
14. Confirm missing/malformed PWM is detected within 250 ms and cannot restore
    a previous countdown or FIRED state.
15. Restore each failure while switches remain asserted; confirm the system
    remains locked until the complete safe reset is performed.

Acceptance gate: every single injected failure leads to load-off and deliberate
recovery; no restoration of power, radio, or wiring causes automatic activation.

## 14. Check propulsion-noise immunity with props removed

Do not begin this phase until the previously reported motor twitch has been
diagnosed. Use ordinary prop-off motor-test precautions and do not perform
casual high-throttle bench runs.

1. Secure the bare airframe and remove all loose objects.
2. Confirm the inert load and contact sensor are mechanically secured.
3. Observe the two PWM inputs, two contact inputs, ESP32 supply voltage, and
   state indication while using controlled motor tests.
4. Progress from individual low-power motor tests to the minimum combination
   needed to expose electrical noise.
5. Check for:
   - false PWM faults;
   - false contact events;
   - ESP32 brownouts or resets;
   - receiver or GPS/compass disturbances;
   - harness motion near the sensor;
   - unintended state changes.
6. If noise appears, correct harness routing, grounding, BEC filtering, or
   mechanical mounting. Do not simply widen command-validity thresholds or
   disable fault detection.

Acceptance gate: propulsion tests produce no false authorization, resets, or
sensor transitions and do not alter normal flight-controller operation.

## 15. Perform a non-operational carriage test before any powered demonstration

This stage is not permission to fly; it begins only after the aircraft's
ordinary unresolved issues have been closed and an appropriate operator has
accepted the test conditions.

1. First carry the complete sensor assembly with the ESP32 load physically
   disconnected and the safety device unpowered.
2. Inspect propeller clearance, center-of-gravity change, structural security,
   GPS/compass separation, antenna placement, and landing clearance.
3. Conduct the lowest-risk ground handling and vibration checks appropriate to
   the aircraft.
4. If later conducting a powered inert demonstration, retain the buzzer/dummy
   load and repeat the complete preflight truth-table and failsafe checks that
   day.
5. Do not replace the inert load or treat successful carriage as certification
   for an operational device.

## 16. Final acceptance checklist

The integration is accepted only as an inert demonstrator when all boxes below
are supported by recorded evidence:

- [ ] Exact LUX F765 NDAA board and running firmware recorded.
- [ ] Original aircraft and transmitter configurations backed up.
- [ ] Original/shared transmitter model unchanged.
- [ ] CH6 and CH9 verified without affecting CH7 or CH8.
- [ ] S1/S2 measured as correct normal 50 Hz PWM.
- [ ] Radio loss produces neutral-invalid or missing PWM, never asserted PWM.
- [ ] `SERVO_RC_FS_MSK=288` behavior measured rather than assumed.
- [ ] Contact sensor complementary truth table verified.
- [ ] Exactly two equal FIRE routes exist: one valid SE press or stable valid
      deflection after ARMED.
- [ ] Both FIRE routes remain concurrently available; neither waits for or
      depends on failure of the other.
- [ ] Deflection before ARMED cannot fire and produces a premature-FIRE fault.
- [ ] Invalid contact wiring immediately dominates both FIRE routes and turns
      the load off.
- [ ] Load defaults off at boot and at the beginning of every firmware loop.
- [ ] Local SAFE and remote DISARM immediately revoke authorization.
- [ ] No countdown, pending FIRE input, or FIRED state survives a fault or
      reboot.
- [ ] Every fault requires the complete deliberate safe-reset sequence.
- [ ] Dedicated BEC remains stable and does not disturb the flight controller.
- [ ] Motor/ESC noise testing completed with propellers removed.
- [ ] Previously reported motor twitch resolved before prop-on work.
- [ ] Mechanical sensor assembly cannot enter a propeller arc.
- [ ] Only an inert/current-limited load used.

## 17. Records to retain

Keep these items together in the project folder:

1. Pre- and post-integration Mission Planner parameter files.
2. The duplicated RadioMaster model file.
3. The new ESP32 firmware revision and compile log.
4. A wiring schematic and connector pinout.
5. Photographs of both resistor networks and installed harnesses.
6. Oscilloscope or logic-analyzer captures for low, high, and radio-loss PWM.
7. Contact-sensor truth-table measurements.
8. Completed test matrix with date, tester, result, and anomaly notes.
9. BEC voltage measurements under maximum inert-load demand.
10. A list of unresolved issues; any unexplained result reopens the relevant
    acceptance gate.

## References

- LUX F765 NDAA output grouping and pinout:
  https://ardupilot.org/copter/docs/common-luxf765-ndaa.html
- ArduPilot output-function mapping:
  https://ardupilot.org/copter/docs/common-rcoutput-mapping.html
- ArduPilot DShot/PWM output-group limitations:
  https://ardupilot.org/copter/docs/common-dshot-escs.html
- ESP32 GPIO restrictions:
  https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html
