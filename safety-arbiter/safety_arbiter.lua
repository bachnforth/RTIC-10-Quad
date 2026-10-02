-- safety_arbiter.lua - single arbiter for the ESP32 safety device's S1 (ARM)
-- and S2 (FIRE) inputs on the LUX F765 (ArduCopter 4.7.1).
--
-- Replaces the old direct pass-throughs:
--   S1 (SERVO9)  was RCIN6Scaled (SB)  -> now SERVO9_FUNCTION  = 94 (Script1)
--   S2 (SERVO10) was RCIN9Scaled (SE)  -> now SERVO10_FUNCTION = 95 (Script2)
--
-- The ESP32 firmware is unchanged. It still owns SW1, the 31 s standoff, the
-- FIRE authorisation rules and the deflection contact. This script only decides
-- what pulse widths it is sent:
--   1100 us  released        1900 us  asserted
--   1500 us  invalid -> ESP32 holds an existing ARMED, faults otherwise
--
-- ARM request (one latch, last command wins, DISARM from either source clears):
--   boot                       -> cleared (S1 held at 1500 if the ESP32 reports
--                                 ARMED, so a LUX reboot does not disarm it)
--   SB released -> asserted    -> set     (SB must be seen released first)
--   SB asserted -> released    -> cleared
--   app ARM REQUEST + CONFIRM  -> set     (two taps within CONFIRM_WINDOW_MS)
--   app DISARM                 -> cleared (overrides SB held up)
--   transmitter or app link loss -> no change. The standoff continues and an
--                                 armed device stays armed.
--
-- FIRE (S2): scaled SE pass-through while the transmitter is valid. While the
-- transmitter is lost, and after it returns until SE has been seen released,
-- S2 is held at 1100 (released). The app never commands FIRE.
--
-- If this script stops, both overrides time out and S1/S2 return to their
-- 1500 us trim: the ESP32 holds ARMED (contact FIRE still works) and radio FIRE
-- is inhibited.
--
-- ESP32 status arrives as its existing 1 Hz JSON line on a LUX UART set to
-- SERIALx_PROTOCOL = 28 (Scripting). It is forwarded to QGC three ways:
--   GENERATOR_STATUS (2 Hz) - shown in the QGC Fly View telemetry values panel
--     (group "Generator"): status = ESAD state (0 SAFE, 1 STANDOFF, 2 ARMED,
--     3x FAULT with code x, 9 no status); runtime = standoff seconds left.
--     This vehicle has no generator, so nothing else uses the message.
--   STATUSTEXT at INFO - silent, listed in QGC messages (state changes).
--   NAMED_VALUE_FLOAT SD_* - for logs and the MAVLink Inspector.
--
-- Training exercise. Notional; not for operational use.

local mavlink_msgs = require("MAVLink/mavlink_msgs")

-- ---------- constants ----------
local LOOP_MS            = 50
local OVERRIDE_MS        = 300     -- output falls back to trim if not refreshed
local PWM_RELEASED       = 1100
local PWM_ASSERTED       = 1900
local PWM_HOLD           = 1500
local BAND_RELEASE_MAX   = 1250    -- ESP32 command bands
local BAND_ASSERT_MIN    = 1750
local EDGE_STABLE_MS     = 100     -- SB/SE must hold a band this long to count
local CONFIRM_WINDOW_MS  = 10000
local STATUS_STALE_MS    = 3000
local ESP32_BAUD         = 115200

local FUNC_ARM, FUNC_FIRE = 94, 95         -- Script1, Script2
local RC_ARM,   RC_FIRE   = 6, 9           -- SB, SE

local MAV_CMD_SAFETY     = 31010           -- MAV_CMD_USER_1
local SAFETY_KEY         = 7713            -- param2; rejects stray USER_1 traffic
local ACT_DISARM, ACT_ARM_REQUEST, ACT_ARM_CONFIRM = 0, 1, 2

local MAV_RESULT_ACCEPTED, MAV_RESULT_DENIED = 0, 2
local SEV_CRIT, SEV_ERR, SEV_WARN, SEV_NOTICE, SEV_INFO = 2, 3, 4, 5, 6

local BAND_REL, BAND_ASSERT, BAND_INVALID = 0, 1, 2

-- ---------- setup ----------
local COMMAND_LONG_ID = mavlink_msgs.get_msgid("COMMAND_LONG")
local msg_map = { [COMMAND_LONG_ID] = "COMMAND_LONG" }

local chan_arm  = SRV_Channels:find_channel(FUNC_ARM)
local chan_fire = SRV_Channels:find_channel(FUNC_FIRE)
local port      = serial:find_serial(0)

-- QGC 5 reads aloud every STATUSTEXT at NOTICE or more severe. The operator
-- wants silent status (the Fly View panel carries it), so everything is INFO.
-- Only "ARBITER STOPPED" stays CRITICAL: nothing else would announce it.
local function say(_, text) gcs:send_text(SEV_INFO, text) end

-- ---------- helpers ----------
local function now_ms() return millis():toint() end

local function p(name, default)
  local v = param:get(name)
  if v == nil then return default end
  return v
end

-- Reproduces RCINxScaled (angle type) so S2 and the SB bands see the same
-- 1100-1900 values the ESP32 was characterised against.
local function scaled(rc_chan, servo_n)
  local raw = rc:get_pwm(rc_chan)
  local rmin = p("RC" .. rc_chan .. "_MIN", 1100)
  local rtrim = p("RC" .. rc_chan .. "_TRIM", 1500)
  local rmax = p("RC" .. rc_chan .. "_MAX", 1900)
  local smin = p("SERVO" .. servo_n .. "_MIN", 1100)
  local strim = p("SERVO" .. servo_n .. "_TRIM", 1500)
  local smax = p("SERVO" .. servo_n .. "_MAX", 1900)
  local norm = 0
  if raw > rtrim and rmax > rtrim then
    norm = (raw - rtrim) / (rmax - rtrim)
  elseif raw < rtrim and rtrim > rmin then
    norm = (raw - rtrim) / (rtrim - rmin)
  end
  norm = math.max(-1, math.min(1, norm))
  if norm >= 0 then
    return math.floor(strim + norm * (smax - strim) + 0.5)
  end
  return math.floor(strim + norm * (strim - smin) + 0.5)
end

local function band(us)
  if us >= 900 and us <= BAND_RELEASE_MAX then return BAND_REL end
  if us >= BAND_ASSERT_MIN and us <= 2100 then return BAND_ASSERT end
  return BAND_INVALID
end

-- A band only counts once it has been stable for EDGE_STABLE_MS.
local function new_filter() return { cand = nil, since = 0, stable = nil } end
local function filter(f, b, now)
  if b ~= f.cand then f.cand = b; f.since = now end
  if now - f.since >= EDGE_STABLE_MS then f.stable = f.cand end
  return f.stable
end

-- ---------- arbiter state ----------
local arm_req      = false
local arm_source   = "none"
local boot_hold    = true          -- S1 at 1500 until status or a command resolves it
local pending_until = nil          -- app ARM REQUEST awaiting CONFIRM
local sb_filter    = new_filter()
local se_filter    = new_filter()
local sb_last_definite = nil       -- last stable REL/ASSERT; nil until first seen
local fire_gate_open = false
local rc_was_valid = nil

local function set_arm(req, source, why)
  boot_hold = false
  pending_until = nil
  if req ~= arm_req then
    arm_req = req
    arm_source = source
    say(SEV_NOTICE, string.format("Safety ARM request %s (%s)", req and "SET" or "CLEARED", why))
  end
end

-- ---------- ESP32 status ----------
local sd = { state = "UNKNOWN", standoff = 0, enable = -1, faults = -1, fires = -1,
             reason = "", uptime = -1, hold = 0, last_ms = nil }
local rx_buf = ""
local status_lost_reported = false

local STATE_CODE = { SAFE = 0, STANDOFF = 1, ARMED = 2, FAULT = 3, UNKNOWN = -1 }

-- ESP32 fault reasons -> its yellow-LED fault codes.
local function fault_code(reason)
  if reason:find("SENSE") then return 2 end
  if reason:find("CONTACT") or reason:find("FIRE WHILE") or reason:find("FIRE DURING") then return 3 end
  if reason:find("ENABLE LOST") then return 4 end
  if reason:find("PWM") then return 5 end
  if reason:find("BATTERY") then return 6 end
  return 0
end

local function handle_status_line(line)
  local state = line:match('"state":"(%u+)"')
  if not state or STATE_CODE[state] == nil then return end
  local now = now_ms()
  local prev = sd.state
  local standoff = tonumber(line:match('"standoff_s":(%-?%d+)')) or 0
  local faults = tonumber(line:match('"faults":(%d+)')) or -1
  local fires = tonumber(line:match('"fires":(%d+)')) or -1
  local uptime = tonumber(line:match('"uptime_s":(%d+)')) or -1
  local reason = line:match('"fault_reason":"([^"]*)"') or ""

  if sd.uptime >= 0 and uptime >= 0 and uptime < sd.uptime then
    say(SEV_WARN, "Safety device rebooted")
  end
  if status_lost_reported then
    say(SEV_NOTICE, "Safety status restored")
    status_lost_reported = false
  end
  if state ~= prev then
    if state == "FAULT" then
      say(SEV_ERR, "Safety FAULT " .. reason)
    elseif state == "STANDOFF" then
      say(SEV_NOTICE, string.format("Safety standoff %d", standoff))
    else
      say(SEV_NOTICE, "Safety " .. state)
    end
  end
  if sd.fires >= 0 and fires > sd.fires then
    say(SEV_WARN, string.format("Safety load fired (%d)", fires))
  end

  sd.state, sd.standoff, sd.faults, sd.fires = state, standoff, faults, fires
  sd.uptime, sd.reason = uptime, reason
  sd.enable = tonumber(line:match('"enable":(%d)')) or -1
  sd.hold = tonumber(line:match('"remote_hold":(%d)')) or 0
  sd.last_ms = now

  if boot_hold and state ~= "ARMED" then
    boot_hold = false
  elseif boot_hold and prev == "UNKNOWN" then
    say(SEV_WARN, "Safety ARMED at LUX boot, holding")
  end
end

local function poll_serial()
  if not port then return end
  local n = port:available():toint()
  while n > 0 do
    local chunk = port:readstring(math.min(n, 256))
    if not chunk or #chunk == 0 then break end
    n = n - #chunk
    rx_buf = rx_buf .. chunk
    while true do
      local nl = rx_buf:find("\n", 1, true)
      if not nl then break end
      local line = rx_buf:sub(1, nl - 1)
      rx_buf = rx_buf:sub(nl + 1)
      if line:sub(1, 1) == "{" then handle_status_line(line) end
    end
    if #rx_buf > 600 then rx_buf = "" end   -- no newline in a sane line length
  end
end

local function status_fresh(now)
  return sd.last_ms ~= nil and now - sd.last_ms <= STATUS_STALE_MS
end

-- ---------- app commands ----------
-- result_param2 echoes the action so each ACK can be matched to its tap.
local function send_ack(chan, msg, result)
  mavlink:send_chan(chan, mavlink_msgs.encode("COMMAND_ACK", {
    command = MAV_CMD_SAFETY, result = result, progress = 0,
    result_param2 = (msg.param1 == 0 or msg.param1 == 1 or msg.param1 == 2)
                    and math.floor(msg.param1) or 255,
    target_system = msg.sysid, target_component = msg.compid }))
end

local function handle_safety_command(cmd, now)
  local gcs_sysid = p("MAV_GCS_SYSID", 255)
  local my_sysid = p("SYSID_THISMAV", 1)
  if cmd.sysid ~= gcs_sysid or cmd.target_system ~= my_sysid or
     (cmd.target_component ~= 1 and cmd.target_component ~= 0) then
    return MAV_RESULT_DENIED, "wrong sender/target"
  end
  if cmd.param2 ~= SAFETY_KEY or cmd.param3 ~= 0 or cmd.param4 ~= 0 or
     cmd.param5 ~= 0 or cmd.param6 ~= 0 or cmd.param7 ~= 0 then
    return MAV_RESULT_DENIED, "malformed"
  end
  local act = cmd.param1
  if act == ACT_DISARM then
    set_arm(false, "app", "app DISARM")
    return MAV_RESULT_ACCEPTED
  elseif act == ACT_ARM_REQUEST then
    if arm_req then return MAV_RESULT_ACCEPTED end
    pending_until = now + CONFIRM_WINDOW_MS
    say(SEV_NOTICE, "Safety ARM requested, tap CONFIRM")
    return MAV_RESULT_ACCEPTED
  elseif act == ACT_ARM_CONFIRM then
    if arm_req then return MAV_RESULT_ACCEPTED end
    if pending_until == nil or now > pending_until then
      pending_until = nil
      return MAV_RESULT_DENIED, "CONFIRM without REQUEST"
    end
    set_arm(true, "app", "app ARM")
    if status_fresh(now) and sd.enable == 0 then
      say(SEV_WARN, "Safety SW1 is SAFE")
    end
    return MAV_RESULT_ACCEPTED
  end
  return MAV_RESULT_DENIED, "unknown action"
end

local function poll_mavlink(now)
  for _ = 1, 5 do
    local raw, chan = mavlink:receive_chan()
    if raw == nil then return end
    -- decode() raises on a bad header; one malformed packet must not stop us
    local ok, msg = pcall(mavlink_msgs.decode, raw, msg_map)
    if ok and msg ~= nil and msg.msgid == COMMAND_LONG_ID and msg.command == MAV_CMD_SAFETY then
      local handled, err = pcall(function()
        local result, why = handle_safety_command(msg, now)
        send_ack(chan, msg, result)
        if result ~= MAV_RESULT_ACCEPTED then
          say(SEV_WARN, "Safety command denied: " .. (why or "?"))
        end
      end)
      if not handled then
        say(SEV_WARN, "Safety command error: " .. tostring(err):sub(1, 28))
      end
    end
  end
end

-- ---------- transmitter ----------
local function poll_rc(now)
  local valid = rc:has_valid_input()
  if valid ~= rc_was_valid then
    if rc_was_valid ~= nil then
      say(valid and SEV_NOTICE or SEV_WARN,
          valid and "Transmitter link restored" or "Transmitter link lost")
    end
    rc_was_valid = valid
    sb_filter = new_filter()
    se_filter = new_filter()
    if not valid then fire_gate_open = false end
  end
  if not valid then return PWM_RELEASED end

  -- SB edges drive the ARM latch.
  local sb = filter(sb_filter, band(scaled(RC_ARM, 9)), now)
  if sb == BAND_ASSERT or sb == BAND_REL then
    if sb_last_definite == BAND_REL and sb == BAND_ASSERT then
      set_arm(true, "SB", "SB up")
    elseif sb_last_definite == BAND_ASSERT and sb == BAND_REL then
      set_arm(false, "SB", "SB down")
    end
    sb_last_definite = sb
  end

  -- SE passes through once it has been seen released since the link came up.
  local se_us = scaled(RC_FIRE, 10)
  local se = filter(se_filter, band(se_us), now)
  if not fire_gate_open then
    if se == BAND_REL then fire_gate_open = true end
    return PWM_RELEASED
  end
  return se_us
end

-- ---------- Fly View panel ----------
local GENERATOR_STATUS_ID = 373
local UINT16_MAX, INT16_MAX, INT32_MAX = 65535, 32767, 2147483647

local function panel_status(now)
  if sd.state == "UNKNOWN" or not status_fresh(now) then return 9 end
  if sd.state == "FAULT" then return 30 + fault_code(sd.reason) end
  return STATE_CODE[sd.state]
end

-- Sent to every MAVLink channel. send_chan returns nil for a channel that is
-- not in use, but raises an error past the build's buffer count (8 on SITL,
-- fewer on the LUX), so stop at the first error instead of letting it end
-- the script.
local function send_panel(now)
  local runtime = (sd.state == "STANDOFF" and status_fresh(now)) and sd.standoff or 0
  local payload = string.pack("<I8fffffI4i4I2i2i2", panel_status(now),
    0, 0, 0, 0, 0, runtime, INT32_MAX, UINT16_MAX, INT16_MAX, INT16_MAX)
  for chan = 0, 15 do
    if not pcall(mavlink.send_chan, mavlink, chan, GENERATOR_STATUS_ID, payload) then
      break
    end
  end
end

-- ---------- main loop ----------
local status_period = 0
local function update()
  local now = now_ms()
  poll_serial()
  poll_mavlink(now)
  if pending_until ~= nil and now > pending_until then
    pending_until = nil
    say(SEV_NOTICE, "Safety ARM request expired")
  end
  local fire_us = poll_rc(now)

  local arm_us
  if arm_req then
    arm_us = PWM_ASSERTED
  elseif boot_hold then
    arm_us = PWM_HOLD
  else
    arm_us = PWM_RELEASED
  end
  SRV_Channels:set_output_pwm_chan_timeout(chan_arm, arm_us, OVERRIDE_MS)
  SRV_Channels:set_output_pwm_chan_timeout(chan_fire, fire_us, OVERRIDE_MS)

  if port and sd.last_ms ~= nil and not status_fresh(now) and not status_lost_reported then
    say(SEV_WARN, "Safety status LOST")
    status_lost_reported = true
    sd.state = "UNKNOWN"
  end

  status_period = status_period + LOOP_MS
  if status_period >= 500 then
    status_period = 0
    gcs:send_named_float("SD_STATE", STATE_CODE[sd.state] or -1)
    gcs:send_named_float("SD_CD", sd.state == "STANDOFF" and sd.standoff or 0)
    gcs:send_named_float("SD_REQ", arm_req and 1 or (boot_hold and 2 or 0))
    gcs:send_named_float("SD_TXOK", rc:has_valid_input() and 1 or 0)
    send_panel(now)
  end
  return update, LOOP_MS
end

-- A runtime error stops the script; the overrides then time out to trim
-- (S1 hold, S2 inhibit) rather than freezing at their last values.
local function protected()
  local ok, fn_or_err, delay = pcall(update)
  if not ok then
    gcs:send_text(SEV_CRIT, "Safety ARBITER STOPPED: S1 hold, S2 inhibit")
    gcs:send_text(SEV_CRIT, tostring(fn_or_err):sub(1, 50))
    return
  end
  return protected, delay
end

if chan_arm == nil or chan_fire == nil then
  gcs:send_text(SEV_CRIT, "Safety arbiter: SERVO9/10 not Script1/2")
  return
end
-- ArduPilot boots with every output flagged as holding a fixed PWM. Nothing
-- clears that flag for a scripting function, and while it is set an expired
-- override FREEZES at its last value instead of returning to SERVOx_TRIM.
-- Setting the scaled output once clears it, so if this script stops, S1 and
-- S2 really do fall back to 1500 us within OVERRIDE_MS.
SRV_Channels:set_output_scaled(FUNC_ARM, 0)
SRV_Channels:set_output_scaled(FUNC_FIRE, 0)
mavlink:init(8, 1)
mavlink:register_rx_msgid(COMMAND_LONG_ID)
mavlink:block_command(MAV_CMD_SAFETY)
if port then port:begin(ESP32_BAUD) else
  gcs:send_text(SEV_WARN, "Safety arbiter: no status serial port")
end
gcs:send_text(SEV_INFO, "Safety arbiter running, ARM request cleared")
return protected, 1000
