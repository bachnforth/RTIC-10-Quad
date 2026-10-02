-- ArduCopter 4.7.1 SITL V2 prototype. RCx_OPTION=300 (Scripting1) is the
-- *entry* switch: LOW then HIGH while flying in a manual/LOITER mode.
-- The script stages a mission waypoint, or a DO_CHANGE_SPEED between the
-- selected leg's WPs, while stopped, then requests AUTO. A direct AUTO entry
-- never triggers a jump. Earlier-leg speed state cannot be replayed safely
-- by the 4.7.1 Lua API and is rejected for the selected leg.
-- Test in SITL before considering any flight use.

local AUTO = 3
local MAV_TYPE_QUADROTOR = 2
local MISSION_RUNNING = 1
local WP, TAKEOFF, LAND, RTL, CHANGE_SPEED = 16, 22, 21, 20, 178
local INFO, WARNING, ERROR = 6, 4, 3
local AUX_FN = 300
local TABLE_KEY = 81 -- change if another script already owns this key
local PREFIX = "NWA_"
local UPDATE_MS = 100
local METERS_PER_DEG = 111319.49079327358
local MAX_LEG_M = 5000 -- bound the local-plane approximation and search area
local MIN_SPEED_MPS, MAX_SPEED_MPS = 1, 20 -- conservative SITL speed envelope

assert(param:add_table(TABLE_KEY, PREFIX, 8), "NWA parameter table unavailable")
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

local last_mode = vehicle:get_mode()
local last_armed = arming:is_armed()
local last_switch = rc:get_aux_cached(AUX_FN)
local selected_this_arm = false
local requested_auto = false

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

-- The aircraft is the origin. Only a projection within the leg is eligible;
-- beyond its end we never silently choose the waypoint behind the aircraft.
local function leg_geometry(an, ae, bn, be)
    local dn, de = bn - an, be - ae
    local length2 = dn * dn + de * de
    if length2 <= 0 then return nil end
    local t = -(an * dn + ae * de) / length2
    local cn, ce = an + t * dn, ae + t * de
    return math.sqrt(cn * cn + ce * ce), t, math.sqrt(length2)
end

-- Copter-4.7.1 treats type 0 (airspeed) and type 1 (groundspeed) identically
-- for DO_CHANGE_SPEED: both update horizontal WPNav speed in m/s. Type 2/3
-- affect climb/descent and cannot serve this script's horizontal-speed goal.
-- Param3 (throttle) is ignored by Copter; permit only common "unused" values.
local function speed_item(item, idx)
    local kind, speed = item:param1(), item:param2()
    local throttle, extra = item:param3(), item:param4()
    if kind ~= 0 and kind ~= 1 then
        return nil, string.format("unsupported speed type %s seq %d", tostring(kind), idx)
    end
    if not finite(speed) or speed < 0 or speed > MAX_SPEED_MPS
       or (speed > 0 and speed < MIN_SPEED_MPS) then
        return nil, string.format("invalid speed at seq %d", idx)
    end
    if not finite(throttle) or (throttle ~= 0 and throttle ~= -1)
       or not finite(extra) or extra ~= 0 then
        return nil, string.format("unsupported speed fields seq %d", idx)
    end
    return {seq=idx, speed=speed}
end

local function config(count)
    local start, finish = START:get(), END_:get()
    local maxdist, minleg, ambig = MAXDIST:get(), MINLEG:get(), AMBIG:get()
    if not integer(start) or start < 1 or start >= count then
        return nil, "invalid NWA_START"
    end
    if not integer(finish) or finish < 0 or finish >= count then
        return nil, "invalid NWA_END"
    end
    if finish == 0 then finish = count - 1 end
    if finish < start then return nil, "NWA_END precedes NWA_START" end
    if not finite(maxdist) or maxdist <= 0 or maxdist > 1000 then
        return nil, "NWA_MAXDIST must be >0 and <=1000m"
    end
    if not finite(minleg) or minleg < 1 or minleg > 100 then
        return nil, "NWA_MINLEG must be 1..100m"
    end
    if not finite(ambig) or ambig < 0.1 or ambig > 100 then
        return nil, "NWA_AMBIG must be 0.1..100m"
    end
    return {start=start, finish=finish, maxdist=maxdist,
            minleg=minleg, ambig=ambig}
end

local function choose_segment(ref_lat, ref_lon)
    local count = mission:num_commands() -- includes home at sequence 0
    if not count or count < 3 then return nil, "mission too short" end
    local cfg, err = config(count)
    if not cfg then return nil, err end

    local prev, best, second, terminal = nil, nil, nil, false
    local speed_state, block_last_positive, block_count = nil, nil, 0
    local wp_count = 0
    for idx = 1, count - 1 do
        local item = mission:get_item(idx)
        if not item then return nil, string.format("cannot read mission item %d", idx) end
        local command = item:command()
        if not integer(command) then
            return nil, string.format("invalid command at seq %d", idx)
        end
        if command == TAKEOFF and idx == 1 then
            -- Only a leading TAKEOFF is allowed, and this script requires flight.
        elseif (command == LAND or command == RTL) and idx == count - 1 then
            terminal = true
        elseif command == CHANGE_SPEED and not terminal then
            local parsed, speed_err = speed_item(item, idx)
            if not parsed then return nil, speed_err end
            block_count = block_count + 1
            if parsed.speed > 0 then
                speed_state = parsed
                block_last_positive = parsed
            end
        elseif command == WP and not terminal then
            local lat, lon = item:x(), item:y()
            if not valid_coord(lat, lon) then
                return nil, string.format("invalid/implicit WP coordinates at %d", idx)
            end
            if math.abs(lat) > 800000000 then
                return nil, "waypoint latitude above 80 degrees"
            end
            wp_count = wp_count + 1
            local n, e = ne(ref_lat, ref_lon, lat, lon)
            if prev then
                local dist, t, length = leg_geometry(prev.n, prev.e, n, e)
                if not dist or not finite(dist) or not finite(length)
                   or length < cfg.minleg or length > MAX_LEG_M then
                    return nil, string.format("invalid leg %d->%d (length %.1fm)",
                                              prev.idx, idx, length or -1)
                end
                if prev.idx >= cfg.start and idx <= cfg.finish and t >= 0 and t <= 1 then
                    local candidate = {from=prev.idx, to=idx, dist=dist,
                                       t=t, length=length,
                                       speed=speed_state, block_count=block_count,
                                       block_replay=block_last_positive}
                    if not best or dist < best.dist then
                        second, best = best, candidate
                    elseif not second or dist < second.dist then
                        second = candidate
                    end
                end
            end
            prev = {idx=idx, n=n, e=e}
            block_last_positive, block_count = nil, 0
        else
            return nil, string.format("unsupported mission cmd %d at seq %d", command, idx)
        end
    end
    if wp_count < 2 then return nil, "need at least two explicit WPs" end
    if not best then return nil, "no eligible leg projection (before/after route or range)" end
    detail(string.format("candidate %d->%d xtrack %.1fm t=%.2f",
                         best.from, best.to, best.dist, best.t))
    if best.dist > cfg.maxdist then
        return nil, string.format("nearest leg %.1fm > limit %.1fm", best.dist, cfg.maxdist)
    end
    if second and second.dist - best.dist < cfg.ambig then
        return nil, string.format("ambig %d>%d %.1fm vs %d>%d %.1fm",
                                  best.from, best.to, best.dist,
                                  second.from, second.to, second.dist)
    end
    if mission:num_commands() ~= count then return nil, "mission count changed during scan" end
    if best.speed then
        if not best.block_replay or best.block_replay.seq ~= best.speed.seq then
            return nil, string.format("speed seq %d persists to %d; no safe replay",
                                      best.speed.seq, best.to)
        end
        best.stage = best.speed.seq
    else
        best.stage = best.to -- no positive mission speed yet: AUTO uses WP_SPD
    end
    return best
end

local function attempt_entry()
    local enabled, once = ENABLE:get(), ONCE:get()
    if not finite(enabled) or (enabled ~= 0 and enabled ~= 1)
       or not finite(once) or (once ~= 0 and once ~= 1) then
        reject("invalid NWA_ENABLE/ONCE"); return
    end
    if enabled == 0 then reject("disabled"); return end
    if gcs:frame_type() ~= MAV_TYPE_QUADROTOR then
        reject("requires ArduCopter quadrotor"); return
    end
    if once == 1 and selected_this_arm then
        reject("already selected this arm"); return
    end
    if not arming:is_armed() or not vehicle:get_likely_flying() then
        reject("aircraft must be armed and flying"); return
    end
    if vehicle:get_mode() == AUTO then reject("already in AUTO"); return end
    if mission:state() == MISSION_RUNNING then
        reject("mission still running outside AUTO"); return
    end
    local restart = param:get("MIS_RESTART")
    if restart ~= 0 then reject("set MIS_RESTART=0 (resume)"); return end
    if not ahrs:healthy() then reject("AHRS/EKF unhealthy"); return end
    local position = ahrs:get_position()
    if not position then reject("position unavailable"); return end
    local lat, lon = position:lat(), position:lng()
    if not valid_coord(lat, lon) or math.abs(lat) > 800000000 then
        reject("invalid aircraft position"); return
    end
    say(INFO, string.format("position %.7f,%.7f", lat * 1.0e-7, lon * 1.0e-7))

    local best, err = choose_segment(lat, lon)
    if not best then reject(err); return end
    if best.speed then
        say(INFO, string.format("speed %.1fm/s from DO seq %d",
                                best.speed.speed, best.speed.seq))
        if best.block_count > 1 then
            detail(string.format("%d speed DOs; replay last positive", best.block_count))
        end
        say(INFO, string.format("stage DO seq %d before NAV %d", best.stage, best.to))
    else
        local default_speed = param:get("WP_SPD")
        if not finite(default_speed) or default_speed <= 0 then
            reject("WP_SPD unavailable/invalid"); return
        end
        say(INFO, string.format("no prior speed DO; WP_SPD %.1fm/s", default_speed))
    end
    -- A changed mode/mission during Lua work invalidates the selection.
    if vehicle:get_mode() == AUTO or mission:state() == MISSION_RUNNING then
        reject("mode/mission changed during selection"); return
    end
    local old_index = mission:get_current_nav_index()
    local function restore_index()
        if vehicle:get_mode() == AUTO or mission:state() == MISSION_RUNNING then
            return false
        end
        if old_index > 0 and old_index < mission:num_commands() then
            return mission:set_current_cmd(old_index)
               and mission:get_current_nav_index() == old_index
        end
        return false
    end
    if not mission:set_current_cmd(best.stage) then
        local restored = restore_index()
        say(ERROR, string.format("stage %d failed; restored=%s", best.stage, tostring(restored)))
        return
    end
    if mission:get_current_nav_index() ~= best.to then
        local restored = restore_index()
        say(ERROR, string.format("NAV %d mismatch; restored=%s", best.to, tostring(restored)))
        return
    end
    say(INFO, string.format("selected NAV %d leg %d->%d xtrk %.1fm",
                            best.to, best.from, best.to, best.dist))
    if not vehicle:set_mode(AUTO) then
        local restored = restore_index()
        say(ERROR, string.format("AUTO denied; NAV restored=%s", tostring(restored)))
        return
    end
    selected_this_arm = true
    requested_auto = true
    say(INFO, "AUTO requested after cmd staging")
end

local function update()
    local armed = arming:is_armed()
    if last_armed and not armed then selected_this_arm = false end
    last_armed = armed

    local mode = vehicle:get_mode()
    if mode == AUTO and last_mode ~= AUTO then
        if requested_auto then
            say(INFO, "AUTO transition: scripted entry")
        else
            say(WARNING, "AUTO transition detected directly; no mission selection")
        end
    end
    if mode ~= AUTO then requested_auto = false end
    last_mode = mode

    local switch = rc:get_aux_cached(AUX_FN)
    if switch ~= nil and last_switch ~= nil and last_switch ~= 2 and switch == 2 then
        detail("Scripting1 entry switch HIGH")
        attempt_entry()
    end
    last_switch = switch
    return update, UPDATE_MS
end

say(INFO, "loaded; use Scripting1 LOW->HIGH for staged AUTO entry")
return update, UPDATE_MS
