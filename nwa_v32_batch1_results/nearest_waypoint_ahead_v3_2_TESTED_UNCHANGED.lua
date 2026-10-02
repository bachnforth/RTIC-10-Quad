-- ArduCopter 4.7.1 SITL V3.2 prototype.
-- RCx_OPTION=300 (Scripting1): LOW->HIGH while flying outside AUTO.
-- V3 stages the destination NAV, enters AUTO, applies reconstructed horizontal
-- speed immediately after AUTO init, then verifies the intended NAV is active.
-- SITL only until this version passes testing.

local AUTO = 3
local MAV_TYPE_QUADROTOR = 2
local MISSION_STOPPED, MISSION_RUNNING = 0, 1
local WP, TAKEOFF, LAND, RTL, CHANGE_SPEED = 16, 22, 21, 20, 178
local INFO, WARNING, ERROR = 6, 4, 3
local AUX_FN = 300
local TABLE_KEY = 81
local PREFIX = "NWA_"
local UPDATE_MS = 100
local CONFIRM_TICKS = 30 -- V3.2 rollback-safe candidate
local METERS_PER_DEG = 111319.49079327358
local MAX_LEG_M = 5000
local MIN_SPEED_MPS, MAX_SPEED_MPS = 1, 20

assert(param:add_table(TABLE_KEY, PREFIX, 9), "NWA parameter table unavailable")
local function add_param(short, idx, default)
    assert(param:add_param(TABLE_KEY, idx, short, default), "NWA param " .. short)
    local p = Parameter()
    assert(p:init(PREFIX .. short), "NWA bind " .. short)
    return p
end

local ENABLE  = add_param("ENABLE",  1, 1)
local MAXDIST = add_param("MAXDIST", 2, 100)
local START   = add_param("START",   3, 1)
local END_    = add_param("END",     4, 0)
local MINLEG  = add_param("MINLEG",  5, 2)
local DEBUG   = add_param("DEBUG",   6, 1)
local ONCE    = add_param("ONCE",    7, 1)
local AMBIG   = add_param("AMBIG",   8, 1)
local MINREM  = add_param("MINREM",  9, 20)

local last_mode = vehicle:get_mode()
local last_armed = arming:is_armed()
local last_switch = rc:get_aux_cached(AUX_FN)
local selected_this_arm = false
local requested_auto = false
local pending = nil

local function say(level, message)
    gcs:send_text(level, "NWA: " .. message)
end

local function reject(message)
    say(WARNING, "reject " .. message)
end

local function detail(message)
    local enabled = DEBUG:get()
    if type(enabled) == "number" and enabled >= 0.5 then say(INFO, message) end
end

local function finite(v)
    return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function integer(v)
    return finite(v) and v == math.floor(v)
end

local function valid_coord(lat, lon)
    return integer(lat) and integer(lon)
        and lat >= -900000000 and lat <= 900000000
        and lon >= -1800000000 and lon <= 1800000000
        and not (lat == 0 and lon == 0)
end

local function ne(ref_lat, ref_lon, lat, lon)
    local dlon = (lon - ref_lon) * 1.0e-7
    if dlon > 180 then dlon = dlon - 360 end
    if dlon < -180 then dlon = dlon + 360 end
    local north = (lat - ref_lat) * 1.0e-7 * METERS_PER_DEG
    local east = dlon * METERS_PER_DEG * math.cos(ref_lat * 1.0e-7 * math.pi / 180)
    return north, east
end

local function leg_geometry(an, ae, bn, be)
    local dn, de = bn - an, be - ae
    local length2 = dn * dn + de * de
    if length2 <= 0 then return nil end
    local t = -(an * dn + ae * de) / length2
    local cn, ce = an + t * dn, ae + t * de
    local length = math.sqrt(length2)
    return math.sqrt(cn * cn + ce * ce), t, length
end

-- Copter-4.7.1: types 0/1 change horizontal speed; types 2/3 change vertical
-- speed. target speed <=0 is a no-op and does not clear persistent state.
local function parse_speed_item(item, idx)
    local kind, speed = item:param1(), item:param2()
    local throttle, extra = item:param3(), item:param4()
    if not finite(kind) or not integer(kind) or kind < 0 or kind > 3 then
        return nil, string.format("invalid speed type seq %d", idx)
    end
    if not finite(speed) then
        return nil, string.format("invalid speed seq %d", idx)
    end
    if speed > MAX_SPEED_MPS or (speed > 0 and speed < MIN_SPEED_MPS) then
        return nil, string.format("speed %.2f outside safe envelope seq %d", speed, idx)
    end
    if not finite(throttle) or (throttle ~= 0 and throttle ~= -1)
       or not finite(extra) or extra ~= 0 then
        return nil, string.format("unsupported speed fields seq %d", idx)
    end
    return {seq=idx, kind=kind, speed=speed}
end

local function config(count)
    local start, finish = START:get(), END_:get()
    local maxdist, minleg = MAXDIST:get(), MINLEG:get()
    local ambig, minrem = AMBIG:get(), MINREM:get()
    if not integer(start) or start < 1 or start >= count then return nil, "invalid NWA_START" end
    if not integer(finish) or finish < 0 or finish >= count then return nil, "invalid NWA_END" end
    if finish == 0 then finish = count - 1 end
    if finish < start then return nil, "NWA_END precedes NWA_START" end
    if not finite(maxdist) or maxdist <= 0 or maxdist > 1000 then return nil, "NWA_MAXDIST must be >0 and <=1000m" end
    if not finite(minleg) or minleg < 1 or minleg > 100 then return nil, "NWA_MINLEG must be 1..100m" end
    if not finite(ambig) or ambig < 0.1 or ambig > 100 then return nil, "NWA_AMBIG must be 0.1..100m" end
    if not finite(minrem) or minrem < 5 or minrem > 500 then return nil, "NWA_MINREM must be 5..500m" end
    return {start=start, finish=finish, maxdist=maxdist, minleg=minleg, ambig=ambig, minrem=minrem}
end

local function choose_segment(ref_lat, ref_lon)
    local count = mission:num_commands()
    if not count or count < 3 then return nil, "mission too short" end
    local cfg, err = config(count)
    if not cfg then return nil, err end

    local prev, best, second, terminal = nil, nil, nil, false
    local horizontal_speed, vertical_speed = nil, nil
    local wp_count = 0

    for idx = 1, count - 1 do
        local item = mission:get_item(idx)
        if not item then return nil, string.format("cannot read mission item %d", idx) end
        local command = item:command()
        if not integer(command) then return nil, string.format("invalid command at seq %d", idx) end

        if command == TAKEOFF and idx == 1 then
            -- leading TAKEOFF only
        elseif (command == LAND or command == RTL) and idx == count - 1 then
            terminal = true
        elseif command == CHANGE_SPEED and not terminal then
            local parsed, speed_err = parse_speed_item(item, idx)
            if not parsed then return nil, speed_err end
            if parsed.speed > 0 then
                if parsed.kind == 0 or parsed.kind == 1 then
                    horizontal_speed = {seq=idx, speed=parsed.speed}
                else
                    vertical_speed = {seq=idx, kind=parsed.kind, speed=parsed.speed}
                end
            end
        elseif command == WP and not terminal then
            local lat, lon = item:x(), item:y()
            if not valid_coord(lat, lon) then return nil, string.format("invalid/implicit WP coordinates at %d", idx) end
            if math.abs(lat) > 800000000 then return nil, "waypoint latitude above 80 degrees" end
            wp_count = wp_count + 1
            local n, e = ne(ref_lat, ref_lon, lat, lon)

            if prev then
                local dist, t, length = leg_geometry(prev.n, prev.e, n, e)
                if not dist or not finite(dist) or not finite(length)
                   or length < cfg.minleg or length > MAX_LEG_M then
                    return nil, string.format("invalid leg %d->%d (length %.1fm)", prev.idx, idx, length or -1)
                end
                local remaining = (1 - t) * length
                if prev.idx >= cfg.start and idx <= cfg.finish
                   and t >= 0 and t <= 1 and remaining >= cfg.minrem then
                    local candidate = {
                        from=prev.idx, to=idx, dist=dist, t=t, length=length,
                        remaining=remaining, speed=horizontal_speed, vertical=vertical_speed,
                        to_lat=lat, to_lon=lon
                    }
                    if not best or dist < best.dist then
                        second, best = best, candidate
                    elseif not second or dist < second.dist then
                        second = candidate
                    end
                end
            end
            prev = {idx=idx, n=n, e=e}
        else
            return nil, string.format("unsupported mission cmd %d at seq %d", command, idx)
        end
    end

    if wp_count < 2 then return nil, "need at least two explicit WPs" end
    if not best then return nil, string.format("no eligible leg with >=%.1fm remaining", cfg.minrem) end

    detail(string.format("candidate %d->%d xtrack %.1fm t=%.2f rem %.1fm",
                         best.from, best.to, best.dist, best.t, best.remaining))
    if best.dist > cfg.maxdist then return nil, string.format("nearest leg %.1fm > limit %.1fm", best.dist, cfg.maxdist) end
    if second and second.dist - best.dist < cfg.ambig then
        return nil, string.format("ambig %d>%d %.1fm vs %d>%d %.1fm",
                                  best.from, best.to, best.dist, second.from, second.to, second.dist)
    end
    if best.vertical then
        return nil, string.format("persistent vertical speed type %d seq %d unsupported",
                                  best.vertical.kind, best.vertical.seq)
    end
    if mission:num_commands() ~= count then return nil, "mission count changed during scan" end

    if not best.speed then
        local default_speed = param:get("WP_SPD")
        if not finite(default_speed) or default_speed < MIN_SPEED_MPS or default_speed > MAX_SPEED_MPS then
            return nil, "WP_SPD unavailable/outside safe envelope"
        end
        best.speed = {seq=nil, speed=default_speed}
    end
    return best, nil, count
end

local function restore_mode(mode)
    if vehicle:get_mode() == mode then return true end
    return vehicle:set_mode(mode) and vehicle:get_mode() == mode
end

local function restore_mission_index(index)
    if vehicle:get_mode() == AUTO or mission:state() ~= MISSION_STOPPED then
        return false
    end
    if not integer(index) or index < 0 or index >= mission:num_commands() then
        return false
    end
    if not mission:set_current_cmd(index) then return false end
    if index == 0 then return true end
    return mission:get_current_nav_index() == index
end

-- Roll back only while the script-requested AUTO is still in control.
-- Never override a pilot/failsafe mode change, and never initiate rollback
-- after armed/flying state has been lost.
local function fail_pending(message)
    if not pending then say(ERROR, message); return end

    local p = pending
    pending = nil
    requested_auto = false

    if not arming:is_armed() or not vehicle:get_likely_flying() then
        say(ERROR, message .. "; no rollback after flying/armed state lost")
        return
    end

    local observed = vehicle:get_mode()
    if observed ~= AUTO then
        say(ERROR, string.format("%s; mode changed to %d externally; no rollback",
                                 message, observed))
        return
    end

    local mode_restored = restore_mode(p.prior_mode)
    local index_restored = false
    if mode_restored and vehicle:get_mode() == p.prior_mode
       and mission:state() == MISSION_STOPPED then
        index_restored = restore_mission_index(p.old_index)
    end
    say(ERROR, string.format("%s; prior mode restored=%s mission index restored=%s",
                             message, tostring(mode_restored), tostring(index_restored)))
end

local function process_pending()
    if not pending then return end

    if not arming:is_armed() or not vehicle:get_likely_flying() then
        fail_pending("entry verification lost flying state"); return
    end

    local mode = vehicle:get_mode()
    if mode ~= AUTO then
        -- A pilot/failsafe/other system has already taken control. fail_pending()
        -- deliberately reports this without trying to restore the earlier mode.
        fail_pending("left AUTO before NAV confirmation"); return
    end

    pending.ticks = pending.ticks + 1
    local target = vehicle:get_target_location()
    local nav_ok =
        pending.speed_applied
        and mission:state() == MISSION_RUNNING
        and mission:get_current_nav_index() == pending.to
        and mission:get_current_nav_id() == WP
        and target ~= nil

    if nav_ok then
        selected_this_arm = true
        say(INFO, string.format("NAV %d confirmed active", pending.to))
        say(INFO, "scripted entry complete")
        pending = nil
        return
    end

    local nav_idx = mission:get_current_nav_index()
    if mission:state() == MISSION_RUNNING and nav_idx ~= 0 and nav_idx ~= pending.to then
        fail_pending(string.format("NAV advanced to %d before confirmation", nav_idx)); return
    end
    if pending.ticks >= CONFIRM_TICKS then
        fail_pending(string.format("NAV %d confirmation timeout", pending.to))
    end
end

local function attempt_entry()
    local enabled, once = ENABLE:get(), ONCE:get()
    if not finite(enabled) or (enabled ~= 0 and enabled ~= 1)
       or not finite(once) or (once ~= 0 and once ~= 1) then
        reject("invalid NWA_ENABLE/ONCE"); return
    end
    if enabled == 0 then reject("disabled"); return end
    if pending then reject("entry already pending"); return end
    if gcs:frame_type() ~= MAV_TYPE_QUADROTOR then reject("requires ArduCopter quadrotor"); return end
    if once == 1 and selected_this_arm then reject("already selected this arm"); return end
    if not arming:is_armed() or not vehicle:get_likely_flying() then reject("aircraft must be armed and flying"); return end

    local prior_mode = vehicle:get_mode()
    if prior_mode == AUTO then reject("already in AUTO"); return end
    if mission:state() ~= MISSION_STOPPED then reject("mission must be stopped outside AUTO"); return end
    if param:get("MIS_RESTART") ~= 0 then reject("set MIS_RESTART=0 (resume)"); return end
    if not ahrs:healthy() then reject("AHRS/EKF unhealthy"); return end

    local position = ahrs:get_position()
    if not position then reject("position unavailable"); return end
    local lat, lon = position:lat(), position:lng()
    if not valid_coord(lat, lon) or math.abs(lat) > 800000000 then reject("invalid aircraft position"); return end
    say(INFO, string.format("position %.7f,%.7f", lat * 1.0e-7, lon * 1.0e-7))

    local best, err, count = choose_segment(lat, lon)
    if not best then reject(err); return end

    say(INFO, string.format("selected NAV %d leg %d->%d xtrk %.1fm rem %.1fm",
                            best.to, best.from, best.to, best.dist, best.remaining))
    if best.speed.seq then
        say(INFO, string.format("effective speed %.1fm/s from DO seq %d", best.speed.speed, best.speed.seq))
    else
        say(INFO, string.format("effective speed %.1fm/s from WP_SPD", best.speed.speed))
    end

    if mission:num_commands() ~= count then reject("mission count changed before staging"); return end
    local dest = mission:get_item(best.to)
    if not dest or dest:command() ~= WP or dest:x() ~= best.to_lat or dest:y() ~= best.to_lon then
        reject("destination changed before staging"); return
    end
    if vehicle:get_mode() ~= prior_mode or mission:state() ~= MISSION_STOPPED then
        reject("mode/mission changed during selection"); return
    end

    local old_index = mission:get_current_nav_index()
    local function restore_index()
        return restore_mission_index(old_index)
    end

    if not mission:set_current_cmd(best.to) then
        local restored = restore_index()
        say(ERROR, string.format("stage NAV %d failed; restored=%s", best.to, tostring(restored))); return
    end
    if mission:get_current_nav_index() ~= best.to then
        local restored = restore_index()
        say(ERROR, string.format("staged NAV %d mismatch; restored=%s", best.to, tostring(restored))); return
    end
    say(INFO, string.format("staged NAV %d", best.to))

    -- set_mode(AUTO) synchronously runs ModeAuto::init(), including clearing
    -- desired_speed_override_ms, before returning success.
    if not vehicle:set_mode(AUTO) then
        local restored = restore_index()
        say(ERROR, string.format("AUTO denied; NAV restored=%s", tostring(restored))); return
    end
    local observed = vehicle:get_mode()
    if observed ~= AUTO then
        -- Another mode already won the race. Never override a pilot/failsafe
        -- change here; only restore the staged mission position if it is safe.
        local index_restored = restore_mission_index(old_index)
        say(ERROR, string.format(
            "AUTO replaced by mode %d; no mode rollback; mission index restored=%s",
            observed, tostring(index_restored)))
        return
    end

    requested_auto = true
    say(INFO, "AUTO entered")

    -- Establish rollback/diagnostic state before applying speed.
    pending = {
        to=best.to,
        prior_mode=prior_mode,
        old_index=old_index,
        speed=best.speed.speed,
        to_lat=best.to_lat,
        to_lon=best.to_lon,
        speed_applied=false,
        ticks=0
    }

    -- Apply once, immediately after AUTO init; never reapply during confirmation.
    if not vehicle:set_desired_speed(best.speed.speed) then
        fail_pending("speed apply failed")
        return
    end
    pending.speed_applied = true
    say(INFO, string.format("speed applied %.1fm/s", best.speed.speed))
end

local function update()
    local armed = arming:is_armed()
    if last_armed and not armed then
        if pending then
            say(ERROR, "entry verification aborted by disarm; no rollback")
        end
        selected_this_arm = false
        pending = nil
        requested_auto = false
    end
    last_armed = armed

    local mode = vehicle:get_mode()
    if mode == AUTO and last_mode ~= AUTO then
        if requested_auto then
            detail("AUTO transition: scripted entry")
        else
            say(WARNING, "AUTO transition detected directly; no mission selection")
        end
    end
    if mode ~= AUTO and not pending then requested_auto = false end
    last_mode = mode

    process_pending()

    local switch = rc:get_aux_cached(AUX_FN)
    if switch ~= nil and last_switch ~= nil and last_switch ~= 2 and switch == 2 then
        detail("Scripting1 entry switch HIGH")
        attempt_entry()
    end
    last_switch = switch
    return update, UPDATE_MS
end

say(INFO, "V3.2 loaded; Scripting1 LOW->HIGH for staged AUTO entry")
return update, UPDATE_MS
