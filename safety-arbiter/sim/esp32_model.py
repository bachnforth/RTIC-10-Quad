"""Python port of esp32_safety_device_phase10_linkloss_hold.ino (REMOTE_PIXHAWK,
OUTPUT_RC_PWM, no battery monitor, no bench console) for SITL testing.

Inputs are the S1/S2 pulse widths the LUX is emitting (-2 = no pulses), the
SW1 position and the deflection contact. It emits the firmware's 1 Hz JSON
status line byte-for-byte in the same format.

This is a test double, not a substitute for bench validation on the real board.
"""

STANDOFF_MS = 31000
ARM_SUSTAIN_MS = 500
CONTACT_FIRE_MS = 100
PWM_FAULT_MS = 150
EARLY_FIRE_RESET_HOLD_MS = 500

PWM_MIN_US, PWM_MAX_US = 900, 2100
PWM_RELEASE_MAX_US, PWM_ASSERT_MIN_US = 1250, 1750

RELEASED, ASSERTED, INVALID = 0, 1, 2
SAFE, ARM_PENDING, ARMED, FAULT = "SAFE", "STANDOFF", "ARMED", "FAULT"


def cmd_band(us):
    if PWM_MIN_US <= us <= PWM_RELEASE_MAX_US:
        return RELEASED
    if PWM_ASSERT_MIN_US <= us <= PWM_MAX_US:
        return ASSERTED
    return INVALID


class Esp32Model:
    def __init__(self, now):
        self.boot_ms = now
        self.sw1_enable = False        # SW1 SAFE at power-up
        self.contact = False
        self.log = []                  # (ms, text) serial event lines

        self.state = SAFE
        self.standoff_end = 0
        self.fault_code = 0
        self.fault_reason = ""
        self.fault_count = 0
        self.load = False
        self.load_on_count = 0
        self.early_fire_hold_start = None

        self.last_contact_raw = False
        self.contact_high_since = 0
        self.pwm_bad_since = None
        self.last_arm = False
        self.last_safe_pos = True
        self.arm_held_since = None
        self.fire_seen_low = False
        self.remote_hold = False
        self.last_json = now
        self.arm_us = self.fire_us = 0
        self.arm = self.fire = False
        self.contact_fire = False

    # -- helpers mirroring the firmware --
    def _event(self, now, text):
        self.log.append((now, text))

    def load_gate(self, now, on):
        if on != self.load:
            self.load = on
            if on:
                self.load_on_count += 1
            self._event(now, "LOAD %s" % ("ON" if on else "OFF"))

    def enter_safe(self, now):
        self.load_gate(now, False)
        self.state = SAFE
        self.standoff_end = 0
        self.early_fire_hold_start = None
        self.fault_code = 0
        self.fault_reason = ""

    def latch_fault(self, now, code, why):
        self.load_gate(now, False)
        self.state = FAULT
        self.early_fire_hold_start = None
        self.fault_code = code
        self.fault_reason = why
        self.fault_count += 1
        self._event(now, "FAULT %d: %s" % (code, why))

    def step(self, now, arm_us, fire_us):
        """One firmware loop. arm_us/fire_us: pulse width, or -2 for no pulses."""
        self.arm_us, self.fire_us = arm_us, fire_us
        safe_sense = not self.sw1_enable
        en_sense = self.sw1_enable
        enabled = en_sense and not safe_sense

        contact_raw = self.contact
        if contact_raw and not self.last_contact_raw:
            self.contact_high_since = now
        self.last_contact_raw = contact_raw
        contact_fire = contact_raw and now - self.contact_high_since >= CONTACT_FIRE_MS
        self.contact_fire = contact_fire

        arm_b, fire_b = cmd_band(arm_us), cmd_band(fire_us)
        arm_input_invalid = arm_b == INVALID
        remote_valid = arm_b != INVALID and fire_b != INVALID
        arm = arm_b == ASSERTED
        fire = fire_b == ASSERTED
        self.arm, self.fire = arm, fire
        remote_hold = False
        if arm_b == INVALID or fire_b == INVALID:
            remote_hold = self.state == ARMED
            if remote_hold:
                self.pwm_bad_since = None
            else:
                if self.pwm_bad_since is None:
                    self.pwm_bad_since = now
                self.load_gate(now, False)
                if now - self.pwm_bad_since > PWM_FAULT_MS and self.state != FAULT:
                    self.latch_fault(now, 5, "ARM PWM INVALID/LOST" if arm_b == INVALID
                                     else "FIRE PWM INVALID/LOST")
        else:
            self.pwm_bad_since = None

        arm_fall = self.last_arm and not arm
        safed_by_switch = (not self.last_safe_pos) and safe_sense
        self.last_arm, self.last_safe_pos = arm, safe_sense

        s = self.state
        if s == SAFE:
            self.load_gate(now, False)
            if contact_raw:
                self.latch_fault(now, 3, "CONTACT BEFORE ARMED")
            elif fire and not arm:
                self.latch_fault(now, 3, "FIRE WHILE SAFE")
            elif arm and enabled:
                if self.arm_held_since is None:
                    self.arm_held_since = now
                if now - self.arm_held_since >= ARM_SUSTAIN_MS:
                    self.state = ARM_PENDING
                    self.standoff_end = now + STANDOFF_MS
                    self._event(now, "ARM accepted -> standoff running")
            else:
                self.arm_held_since = None
        elif s == ARM_PENDING:
            self.load_gate(now, False)
            if not arm:
                self.enter_safe(now)
                self._event(now, "ARM released -> SAFE")
            elif not enabled:
                self.latch_fault(now, 4, "ENABLE LOST IN STANDOFF")
            elif contact_raw:
                self.latch_fault(now, 3, "CONTACT IN STANDOFF")
            elif fire:
                self.latch_fault(now, 3, "FIRE DURING STANDOFF")
            elif now - self.standoff_end >= 0:
                self.state = ARMED
                self.fire_seen_low = False
                self._event(now, "standoff complete -> ARMED")
        elif s == ARMED:
            if not arm and not arm_input_invalid:
                self.enter_safe(now)
                self._event(now, "ARM released -> SAFE")
            elif not enabled:
                self.enter_safe(now)
                self._event(now, "local switch SAFE -> SAFE")
            else:
                if not remote_valid:
                    self.fire_seen_low = False
                elif not fire:
                    self.fire_seen_low = True
                remote_fire = remote_valid and fire and self.fire_seen_low
                self.load_gate(now, remote_fire or contact_fire)
        elif s == FAULT:
            self.load_gate(now, False)
            inputs_safe = (self.fault_code == 3 and remote_valid and safe_sense != en_sense
                           and not arm and not (fire or contact_raw))
            if not inputs_safe:
                self.early_fire_hold_start = None
                ready = False
            elif self.early_fire_hold_start is None:
                self.early_fire_hold_start = now
                ready = False
            else:
                ready = now - self.early_fire_hold_start >= EARLY_FIRE_RESET_HOLD_MS
            if (arm_fall or safed_by_switch or ready) and safe_sense != en_sense and not contact_raw:
                self.fault_code = 0
                self.fault_reason = ""
                self.enter_safe(now)
                self._event(now, "fault cleared -> SAFE")
        if self.state != ARMED:
            remote_hold = False
        if self.state != SAFE:
            self.arm_held_since = None
        self.remote_hold = remote_hold

    def countdown(self, now):
        if self.state != ARM_PENDING:
            return 0
        return max(0, (self.standoff_end - now + 999) // 1000)

    def json_due(self, now):
        if now - self.last_json >= 1000:
            self.last_json = now
            return True
        return False

    def json_line(self, now):
        en = 1 if self.sw1_enable else 0
        return (
            '{"state":"%s","enable":%d,"safe_sense":%d,"en_sense":%d,"arm":%d,'
            '"fire":%d,"contact_raw":%d,"contact_fire":%d,'
            '"load":%d,"fires":%d,"arm_in_us":%d,'
            '"fire_in_us":%d,"remote_hold":%d,"standoff_s":%d,'
            '"bench":false,"uptime_s":%d,"faults":%d,"fault_reason":"%s",'
            '"batt_v":-1.00,"out_us":%d,"oled":1}\n'
            % (self.state, en, 1 - en, en, int(self.arm), int(self.fire),
               int(self.contact), int(self.contact_fire), int(self.load),
               self.load_on_count, self.arm_us, self.fire_us, int(self.remote_hold),
               self.countdown(now), (now - self.boot_ms) // 1000, self.fault_count,
               self.fault_reason, 2000 if self.load else (1000 if self.state == ARMED else 0))
        )
