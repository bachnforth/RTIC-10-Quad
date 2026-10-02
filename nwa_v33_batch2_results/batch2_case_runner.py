from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pymavlink import mavutil


CASE = sys.argv[1]
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)

HOME_LAT = 35.0495415
HOME_LON = -79.4901810
HOME_ALT = 100.44

events = []
samples = []
latest_boot = None
last_seq = None
last_mode = None


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def event(kind, text, **extra):
    row = {"utc": utcnow(), "boot_ms": latest_boot, "kind": kind, "text": text, **extra}
    events.append(row)
    print(json.dumps(row), flush=True)


m = mavutil.mavlink_connection("tcp:127.0.0.1:5762", source_system=255)
heartbeat = m.wait_heartbeat(timeout=20)
if not heartbeat:
    raise RuntimeError("no SITL heartbeat")
m.target_system = heartbeat.get_srcSystem()
m.target_component = heartbeat.get_srcComponent()
event("HEARTBEAT", "connected", mode=heartbeat.custom_mode, base_mode=heartbeat.base_mode)


def recv(timeout=0.1):
    global latest_boot, last_seq, last_mode
    message = m.recv_match(blocking=True, timeout=timeout)
    if not message:
        return None
    data = message.to_dict()
    kind = message.get_type()
    if "time_boot_ms" in data:
        latest_boot = data["time_boot_ms"]
    if kind == "STATUSTEXT":
        event("STATUSTEXT", message.text, severity=message.severity)
    elif kind == "MISSION_CURRENT":
        if message.seq != last_seq:
            last_seq = message.seq
            event("MISSION_CURRENT", f"seq {message.seq}", seq=message.seq)
    elif kind == "HEARTBEAT":
        if message.custom_mode != last_mode:
            last_mode = message.custom_mode
            event("MODE", f"mode {message.custom_mode}", mode=message.custom_mode)
    elif kind == "COMMAND_ACK":
        event("COMMAND_ACK", f"cmd {message.command} result {message.result}", command=message.command, result=message.result)
    elif kind == "GLOBAL_POSITION_INT":
        vx, vy = message.vx * 0.01, message.vy * 0.01
        samples.append(
            {
                "utc": utcnow(),
                "boot_ms": latest_boot,
                "seq": last_seq,
                "mode": last_mode,
                "lat": message.lat * 1e-7,
                "lon": message.lon * 1e-7,
                "rel_alt_m": message.relative_alt * 0.001,
                "vx_mps": vx,
                "vy_mps": vy,
                "hvel_mps": math.hypot(vx, vy),
            }
        )
    return message


def pump(duration):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        recv(min(0.05, deadline - time.monotonic()))


def wait_for(types, timeout, predicate=lambda _: True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = recv(min(0.1, deadline - time.monotonic()))
        if message and message.get_type() in types and predicate(message):
            return message
    return None


def wait_text(fragment, timeout):
    for row in reversed(events):
        if row.get("kind") == "STATUSTEXT" and fragment in row.get("text", ""):
            return row
    return wait_for({"STATUSTEXT"}, timeout, lambda message: fragment in message.text)


def set_param(name, value):
    m.mav.param_set_send(
        m.target_system,
        m.target_component,
        name.encode(),
        float(value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )
    response = wait_for({"PARAM_VALUE"}, 5, lambda message: message.param_id == name)
    if not response or abs(response.param_value - value) > 0.01:
        raise RuntimeError(f"parameter {name} failed: {response}")
    event("PARAM", f"{name}={response.param_value}", name=name, value=response.param_value)


def request_streams():
    # HEARTBEAT, GPS_RAW_INT, LOCAL_POSITION_NED, GLOBAL_POSITION_INT,
    # MISSION_CURRENT, NAV_CONTROLLER_OUTPUT, VFR_HUD, POSITION_TARGET_*.
    for message_id, hz in [(0, 10), (24, 5), (32, 10), (33, 10), (42, 10), (62, 10), (74, 10), (85, 10), (87, 10)]:
        m.mav.command_long_send(
            m.target_system,
            m.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            message_id,
            1e6 / hz,
            0,
            0,
            0,
            0,
            0,
        )
        time.sleep(0.02)
    pump(0.3)


def item(seq, frame, command, p1, p2, p3, p4, lat, lon, alt, current=0):
    return (seq, frame, command, p1, p2, p3, p4, lat, lon, alt, current)


def base_points():
    # The aircraft hovers at HOME.  The selected leg runs north through HOME,
    # from roughly 56 m south to 167 m north, leaving enough distance to settle.
    wp1 = (HOME_LAT - 0.0015, HOME_LON - 0.0020)
    wp2 = (HOME_LAT - 0.0005, HOME_LON)
    wp3 = (HOME_LAT + 0.0015, HOME_LON)
    wp4 = (HOME_LAT + 0.0060, HOME_LON - 0.0010)
    return wp1, wp2, wp3, wp4


def mission_for(case):
    wp1, wp2, wp3, wp4 = base_points()
    prefix = [
        item(0, 0, 16, 0, 0, 0, 0, HOME_LAT, HOME_LON, HOME_ALT, 1),
        item(1, 3, 22, 0, 0, 0, 0, HOME_LAT, HOME_LON, 20),
    ]
    if case.startswith("persistent"):
        return prefix + [
            item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
            item(3, 2, 178, 1, 5, -1, 0, 0, 0, 0),
            item(4, 3, 16, 0, 0, 0, 0, *wp2, 20),
            item(5, 3, 16, 0, 0, 0, 0, *wp3, 20),
            item(6, 2, 178, 1, 10, -1, 0, 0, 0, 0),
            item(7, 3, 16, 0, 0, 0, 0, *wp4, 20),
            item(8, 2, 20, 0, 0, 0, 0, 0, 0, 0),
        ]
    if case == "local":
        return prefix + [
            item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
            item(3, 2, 178, 1, 8, -1, 0, 0, 0, 0),
            item(4, 3, 16, 0, 0, 0, 0, *wp2, 20),
            item(5, 2, 178, 1, 5, -1, 0, 0, 0, 0),
            item(6, 3, 16, 0, 0, 0, 0, *wp3, 20),
            item(7, 2, 178, 1, 10, -1, 0, 0, 0, 0),
            item(8, 3, 16, 0, 0, 0, 0, *wp4, 20),
            item(9, 2, 20, 0, 0, 0, 0, 0, 0, 0),
        ]
    if case == "vertical":
        return prefix + [
            item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
            item(3, 2, 178, 2, 3, -1, 0, 0, 0, 0),
            item(4, 3, 16, 0, 0, 0, 0, *wp2, 20),
            item(5, 3, 16, 0, 0, 0, 0, *wp3, 20),
            item(6, 2, 20, 0, 0, 0, 0, 0, 0, 0),
        ]
    if case == "minrem":
        wp2_short = (HOME_LAT - 0.0009, HOME_LON)
        wp3_short = (HOME_LAT + 0.00009, HOME_LON)
        return prefix + [
            item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
            item(3, 3, 16, 0, 0, 0, 0, *wp2_short, 20),
            item(4, 3, 16, 0, 0, 0, 0, *wp3_short, 20),
            item(5, 2, 20, 0, 0, 0, 0, 0, 0, 0),
        ]
    # Fallback mission used by fallback, direct, once, external and rollback.
    return prefix + [
        item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
        item(3, 3, 16, 0, 0, 0, 0, *wp2, 20),
        item(4, 3, 16, 0, 0, 0, 0, *wp3, 20),
        item(5, 2, 178, 1, 10, -1, 0, 0, 0, 0),
        item(6, 3, 16, 0, 0, 0, 0, *wp4, 20),
        item(7, 2, 20, 0, 0, 0, 0, 0, 0, 0),
    ]


def wp_ne(north_m, east_m):
    lat = HOME_LAT + north_m / 111319.49079327358
    lon = HOME_LON + east_m / (111319.49079327358 * math.cos(math.radians(HOME_LAT)))
    return lat, lon


def batch2_mission(entries, terminal="rtl"):
    rows = [
        item(0, 0, 16, 0, 0, 0, 0, HOME_LAT, HOME_LON, HOME_ALT, 1),
        item(1, 3, 22, 0, 0, 0, 0, HOME_LAT, HOME_LON, 20),
    ]
    for entry in entries:
        kind = entry[0]
        seq = len(rows)
        if kind == "wp":
            lat, lon = wp_ne(entry[1], entry[2])
            rows.append(item(seq, 3, 16, 0, 0, 0, 0, lat, lon, 20))
        elif kind == "raw_wp":
            rows.append(item(seq, 3, 16, 0, 0, 0, 0, entry[1], entry[2], 20))
        elif kind == "speed":
            rows.append(item(seq, 2, 178, entry[1], entry[2], -1, 0, 0, 0, 0))
        elif kind == "cmd":
            command = entry[1]
            p1 = entry[2] if len(entry) > 2 else 0
            rows.append(item(seq, 2, command, p1, 0, 0, 0, 0, 0, 0))
        else:
            raise ValueError(entry)
    seq = len(rows)
    if terminal == "rtl":
        rows.append(item(seq, 2, 20, 0, 0, 0, 0, 0, 0, 0))
    elif terminal == "land":
        rows.append(item(seq, 3, 21, 0, 0, 0, 0, HOME_LAT, HOME_LON, 0))
    return rows


def case_definition(case):
    common = {"NWA_START": 2, "NWA_END": 3, "NWA_MINREM": 30,
              "NWA_MAXDIST": 100, "NWA_MINLEG": 2, "NWA_AMBIG": 1,
              "NWA_ENABLE": 1, "NWA_ONCE": 0, "MIS_RESTART": 0}
    action, expected = "accept", {"to": 3}
    entries = [("wp", -100, 0), ("wp", 100, 0)]
    terminal = "rtl"

    if case == "01_mid_leg": pass
    elif case == "02_leg_begin": entries = [("wp", -5, 0), ("wp", 195, 0)]
    elif case == "03_beyond_destination": entries = [("wp", -200, 0), ("wp", -100, 0)]; action="reject"; expected={}
    elif case == "04_before_start": entries = [("wp", 100, 0), ("wp", 200, 0)]; action="reject"; expected={}
    elif case == "05_maxdist_inside": entries = [("wp", -100, 99), ("wp", 100, 99)]
    elif case == "06_maxdist_outside": entries = [("wp", -100, 101), ("wp", 100, 101)]; action="reject"; expected={}
    elif case == "07_minrem_above": entries = [("wp", -100, 0), ("wp", 30.5, 0)]
    elif case == "08_minrem_below": entries = [("wp", -100, 0), ("wp", 29.5, 0)]; action="reject"; expected={}
    elif case == "09_short_leg": entries = [("wp", -0.5, 0), ("wp", 0.5, 0)]; action="reject"; expected={}
    elif case == "10_ambiguous_parallel":
        entries=[("wp",-100,10),("wp",100,10),("wp",-100,10.5)]; common.update(NWA_END=4); action="reject"; expected={}
    elif case == "11_intersecting":
        entries=[("wp",-100,-100),("wp",100,100),("wp",-100,100),("wp",100,-100)]; common.update(NWA_END=5); action="reject"; expected={}
    elif case in ("12_takeoff_waypoints", "13_final_rtl"): pass
    elif case == "14_final_land": terminal="land"
    elif case == "15_multiple_speed":
        entries=[("wp",-100,0),("speed",1,4),("speed",1,7),("wp",-50,0),("wp",150,0),("speed",1,10),("wp",600,0)]
        common.update(NWA_START=5,NWA_END=6); expected={"to":6,"speed":7,"speed_seq":4}; action="speed"
    elif case == "16_speed_zero":
        entries=[("wp",-100,0),("speed",1,5),("speed",1,0),("wp",-50,0),("wp",150,0),("speed",1,10),("wp",600,0)]
        common.update(NWA_START=5,NWA_END=6); expected={"to":6,"speed":5,"speed_seq":3}; action="speed"
    elif case == "17_speed_type0":
        entries=[("wp",-100,0),("speed",0,5),("wp",-50,0),("wp",150,0),("speed",1,10),("wp",600,0)]
        common.update(NWA_START=4,NWA_END=5); expected={"to":5,"speed":5,"speed_seq":3}; action="speed"
    elif case == "18_speed_type1":
        entries=[("wp",-100,0),("speed",1,5),("wp",-50,0),("wp",150,0),("speed",1,10),("wp",600,0)]
        common.update(NWA_START=4,NWA_END=5); expected={"to":5,"speed":5,"speed_seq":3}; action="speed"
    elif case == "19_vertical_type2": entries=[("wp",-100,0),("speed",2,3),("wp",-50,0),("wp",150,0)]; common.update(NWA_START=4,NWA_END=5); action="reject"; expected={}
    elif case == "20_vertical_type3": entries=[("wp",-100,0),("speed",3,3),("wp",-50,0),("wp",150,0)]; common.update(NWA_START=4,NWA_END=5); action="reject"; expected={}
    elif case == "21a_do_jump": entries=[("wp",-100,0),("cmd",177,2),("wp",100,0)]; common.update(NWA_END=4); action="reject"; expected={}
    elif case == "21b_condition": entries=[("wp",-100,0),("cmd",112,5),("wp",100,0)]; common.update(NWA_END=4); action="reject"; expected={}
    elif case == "22_malformed": entries=[("raw_wp",0,0),("wp",100,0)]; action="reject"; expected={}
    elif case == "23_disabled": common["NWA_ENABLE"]=0; action="reject"; expected={}
    elif case == "24_enabled": pass
    elif case == "25_once": common["NWA_ONCE"]=1; action="once"; expected={"to":3}
    elif case == "26_rearm": common["NWA_ONCE"]=1; action="rearm"; expected={"to":3}
    elif case == "27_high_no_edge": action="high_hold"; expected={"to":3}
    elif case == "28_edges_pending": common["NWA_ONCE"]=0; action="pending_edges"; expected={"to":3}
    elif case == "29_mis_restart": common["MIS_RESTART"]=1; action="reject"; expected={}
    elif case == "30a_maxdist_zero": common["NWA_MAXDIST"]=0; action="reject"; expected={}
    elif case == "30b_maxdist_1000": common["NWA_MAXDIST"]=1000; entries=[("wp",-100,999),("wp",100,999)]
    elif case == "30c_maxdist_1001": common["NWA_MAXDIST"]=1001; action="reject"; expected={}
    elif case == "31a_minleg_one": common["NWA_MINLEG"]=1; entries=[("wp",-5.5,0),("wp",5.5,0)]; common["NWA_MINREM"]=5
    elif case == "31b_minleg_100": common["NWA_MINLEG"]=100; entries=[("wp",-50.5,0),("wp",50.5,0)]
    elif case == "31c_minleg_101": common["NWA_MINLEG"]=101; action="reject"; expected={}
    elif case == "32a_minrem_five": common["NWA_MINREM"]=5; entries=[("wp",-100,0),("wp",5.5,0)]
    elif case == "32b_minrem_500": common["NWA_MINREM"]=500; entries=[("wp",-100,0),("wp",500.5,0)]
    elif case == "32c_minrem_501": common["NWA_MINREM"]=501; action="reject"; expected={}
    elif case == "33a_enable_invalid": common["NWA_ENABLE"]=2; action="reject"; expected={}
    elif case == "33b_ambig_invalid": common["NWA_AMBIG"]=0; action="reject"; expected={}
    elif case == "33c_maxdist_negative": common["NWA_MAXDIST"]=-1; action="reject"; expected={}
    elif case == "35_loiter_wait_init": action="loiter_init"; expected={"to":3}
    elif case == "36_loiter_wait_stable": action="loiter_stable"; expected={"to":3}
    elif case == "37_rtl_pending": action="rtl_pending"; expected={"to":3}
    elif case == "38_disarm_pending": action="disarm_pending"; expected={"to":3}
    elif case == "40_nav_advance": entries=[("wp",-100,0),("wp",100,0),("wp",300,0)]; common.update(NWA_END=4); action="nav_advance"; expected={"to":3}
    elif case == "42_direct_after_success": action="direct_after"; expected={"to":3}
    elif case == "43_arm_cycles": common["NWA_ONCE"]=1; action="arm_cycles"; expected={"to":3}
    elif case == "44_index_zero": entries=[("wp",-100,0),("wp",100,0),("wp",300,0)]; common.update(NWA_END=4); action="rollback0"; expected={"to":3,"rollback":1}
    elif case == "45_index_nonzero": entries=[("wp",-100,0),("wp",100,0),("wp",300,0)]; common.update(NWA_END=4); action="rollback_nonzero"; expected={"to":3,"rollback":2}
    else: raise ValueError(f"unknown case {case}")
    return batch2_mission(entries, terminal), common, action, expected


mission, CASE_PARAMS, CASE_ACTION, CASE_EXPECTED = case_definition(CASE)


def upload_mission():
    m.mav.mission_clear_all_send(m.target_system, m.target_component)
    wait_for({"MISSION_ACK"}, 3)
    m.mav.mission_count_send(m.target_system, m.target_component, len(mission))
    sent = set()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        message = recv(0.3)
        if not message:
            continue
        if message.get_type() in ("MISSION_REQUEST", "MISSION_REQUEST_INT"):
            seq = message.seq
            _, frame, command, p1, p2, p3, p4, lat, lon, alt, current = mission[seq]
            m.mav.mission_item_int_send(
                m.target_system,
                m.target_component,
                seq,
                frame,
                command,
                current,
                1,
                p1,
                p2,
                p3,
                p4,
                int(round(lat * 1e7)),
                int(round(lon * 1e7)),
                alt,
            )
            sent.add(seq)
        elif message.get_type() == "MISSION_ACK":
            if message.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
                raise RuntimeError(f"mission rejected: {message}")
            break
    if len(sent) != len(mission):
        raise RuntimeError(f"mission upload incomplete: {sorted(sent)}")
    event("MISSION_UPLOAD", "accepted", count=len(mission))

    m.mav.mission_request_list_send(m.target_system, m.target_component)
    count = wait_for({"MISSION_COUNT"}, 4)
    if not count or count.count != len(mission):
        raise RuntimeError(f"mission count mismatch: {count}")
    downloaded = []
    for seq in range(count.count):
        m.mav.mission_request_int_send(m.target_system, m.target_component, seq)
        response = wait_for({"MISSION_ITEM_INT", "MISSION_ITEM"}, 3, lambda message: message.seq == seq)
        if not response:
            raise RuntimeError(f"cannot download mission item {seq}")
        downloaded.append(response.to_dict())
    (OUT / "mission_download.json").write_text(json.dumps(downloaded, indent=2), encoding="utf-8")
    event("MISSION_VERIFY", "download verified", commands=[row[2] for row in mission])

    with (OUT / "mission.waypoints").open("w", encoding="ascii", newline="\n") as stream:
        stream.write("QGC WPL 110\n")
        for row in mission:
            seq, frame, command, p1, p2, p3, p4, lat, lon, alt, current = row
            stream.write(
                f"{seq}\t{current}\t{frame}\t{command}\t{p1}\t{p2}\t{p3}\t{p4}\t{lat:.7f}\t{lon:.7f}\t{alt:.3f}\t1\n"
            )


def set_mode(mode, timeout=5):
    m.set_mode_apm(mode)
    response = wait_for({"HEARTBEAT"}, timeout, lambda message: message.custom_mode == mode)
    if not response:
        raise RuntimeError(f"mode {mode} not observed")
    return response


def rc7(pwm):
    values = [65535] * 8
    values[6] = pwm
    for _ in range(5):
        m.mav.rc_channels_override_send(m.target_system, m.target_component, *values)
        pump(0.05)
    event("RC7", str(pwm), pwm=pwm)


def set_current(seq):
    m.mav.mission_set_current_send(m.target_system, m.target_component, seq)
    response = wait_for({"MISSION_CURRENT"}, 4, lambda message: message.seq == seq)
    if not response:
        raise RuntimeError(f"mission index {seq} not observed")
    event("SET_CURRENT", f"seq {seq}", seq=seq)


def arm_takeoff():
    set_mode(4)  # GUIDED
    # Allow GPS/EKF origin and position estimates to initialize before flight.
    # ARMING_SKIPCHK is enabled only for repeatable SITL setup; the frozen script
    # still independently requires a healthy AHRS and a valid position.
    while latest_boot is None or latest_boot < 25_000:
        pump(0.2)
    armed = None
    arm_deadline = time.monotonic() + 35
    while time.monotonic() < arm_deadline and not armed:
        m.arducopter_arm()
        armed = wait_for(
            {"HEARTBEAT"},
            2,
            lambda message: bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
        )
    if not armed:
        raise RuntimeError("arming timeout")
    event("ARM", "armed")
    m.mav.command_long_send(
        m.target_system,
        m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        20,
    )
    reached = wait_for({"GLOBAL_POSITION_INT"}, 45, lambda message: message.relative_alt >= 18_000)
    if not reached:
        raise RuntimeError("takeoff altitude timeout")
    event("TAKEOFF", "altitude reached")
    pump(2)


def trigger(intervention=None, intervention_fragment="NWA: AUTO entered"):
    rc7(1000)
    pump(0.3)
    values = [65535] * 8
    values[6] = 2000
    for _ in range(4):
        m.mav.rc_channels_override_send(m.target_system, m.target_component, *values)
        pump(0.02)
    event("TRIGGER", "Scripting1 LOW->HIGH")
    if intervention is None:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        message = recv(0.02)
        if message and message.get_type() == "STATUSTEXT" and intervention_fragment in message.text:
            intervention()
            event("INTERVENTION", f"sent immediately after {intervention_fragment}")
            return
    raise RuntimeError(f"{intervention_fragment} message not observed for intervention")


def wait_disarmed(timeout=45):
    return wait_for(
        {"HEARTBEAT"},
        timeout,
        lambda message: not bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
    )


def force_disarm():
    m.mav.command_long_send(
        m.target_system,
        m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        0,
        21196,
        0,
        0,
        0,
        0,
        0,
    )
    wait_disarmed(5)


def save():
    (OUT / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    with (OUT / "telemetry_live.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["utc", "boot_ms", "seq", "mode", "lat", "lon", "rel_alt_m", "vx_mps", "vy_mps", "hvel_mps"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(samples)


PARAMS = [
    ("ARMING_SKIPCHK", 65535), ("SCR_ENABLE", 1), ("RC7_OPTION", 300),
    ("WP_SPD", 6), ("NWA_DEBUG", 1),
] + list(CASE_PARAMS.items())


def nwa_texts(start):
    return [row["text"] for row in events[start:] if row["kind"] == "STATUSTEXT" and row["text"].startswith("NWA:")]


def send_current(seq):
    for _ in range(3):
        m.mav.mission_set_current_send(m.target_system, m.target_component, seq)
        time.sleep(0.005)


def raw_rc7(pwm, duration=0.04):
    values = [65535] * 8
    values[6] = pwm
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        m.mav.rc_channels_override_send(m.target_system, m.target_component, *values)
        recv(0.005)


result = {
    "case": CASE, "parameters": dict(PARAMS), "mission": mission,
    "action": CASE_ACTION, "expected": CASE_EXPECTED, "verdict": "FAIL",
}
case_start = 0
try:
    request_streams()
    for name, value in PARAMS:
        set_param(name, value)
    upload_mission()
    rc7(1000)
    arm_takeoff()
    if CASE_ACTION == "rollback0":
        event("START_INDEX", "preserved natural mission index 0", seq=last_seq)
    elif CASE_ACTION == "rollback_nonzero":
        set_current(CASE_EXPECTED["rollback"])
    else:
        set_current(1)

    case_start = len(events)
    result["start_mode"] = last_mode
    result["start_index"] = last_seq
    if samples:
        result["aircraft_position"] = {k: samples[-1][k] for k in ("lat", "lon", "rel_alt_m")}

    if CASE_ACTION == "reject":
        trigger(); pump(1.2)

    elif CASE_ACTION in ("accept", "speed"):
        trigger()
        if not wait_text("scripted entry complete", 5):
            raise RuntimeError("scripted entry did not complete")
        if CASE_ACTION == "speed":
            target = CASE_EXPECTED["to"]
            next_nav = target + 2
            if not wait_for({"MISSION_CURRENT"}, 15, lambda message: message.seq == next_nav):
                raise RuntimeError(f"mission did not reach following NAV {next_nav}")
            pump(5)

    elif CASE_ACTION == "once":
        trigger()
        if not wait_text("scripted entry complete", 5): raise RuntimeError("first entry failed")
        set_mode(5); pump(.2); trigger(); pump(.8)

    elif CASE_ACTION == "rearm" or CASE_ACTION == "arm_cycles":
        trigger()
        if not wait_text("scripted entry complete", 5): raise RuntimeError("first arm entry failed")
        set_mode(5); force_disarm(); pump(.4); rc7(1000); arm_takeoff(); set_current(1)
        trigger()
        if not wait_text("scripted entry complete", 5): raise RuntimeError("second arm entry failed")
        pump(.5)

    elif CASE_ACTION == "high_hold":
        trigger()
        if not wait_text("scripted entry complete", 5): raise RuntimeError("entry failed")
        set_mode(5); pump(1.5)

    elif CASE_ACTION == "pending_edges":
        trigger(lambda: (raw_rc7(1000, .03), raw_rc7(2000, .03)))
        pump(1)

    elif CASE_ACTION in ("loiter_init", "rtl_pending", "disarm_pending"):
        if CASE_ACTION == "loiter_init": intervention = lambda: set_mode(5)
        elif CASE_ACTION == "rtl_pending": intervention = lambda: set_mode(6)
        else: intervention = force_disarm
        trigger(intervention)
        pump(1)

    elif CASE_ACTION == "loiter_stable":
        trigger(lambda: set_mode(5), "initialized")
        pump(1)

    elif CASE_ACTION == "nav_advance":
        trigger(lambda: send_current(CASE_EXPECTED["to"] + 1), "initialized")
        pump(1.5)

    elif CASE_ACTION in ("rollback0", "rollback_nonzero"):
        trigger(lambda: send_current(CASE_EXPECTED["to"] + 1))
        pump(1.5)

    elif CASE_ACTION == "direct_after":
        trigger()
        if not wait_text("scripted entry complete", 5): raise RuntimeError("entry failed")
        set_mode(5); pump(.3)
        before_direct = len(events)
        set_mode(3); pump(1)
        result["direct_phase_start"] = before_direct

    texts = nwa_texts(case_start)
    staged = sum("staged NAV" in text for text in texts)
    speed_count = sum("speed applied" in text for text in texts)
    completes = sum("scripted entry complete" in text for text in texts)
    mode3_count = sum(row.get("mode") == 3 for row in events[case_start:] if row["kind"] == "MODE")
    result.update({
        "nwa_statustext": texts, "staged_count": staged,
        "speed_setter_count": speed_count, "completion_count": completes,
        "auto_transition_count": mode3_count, "mission_transitions": [row.get("seq") for row in events[case_start:] if row["kind"] == "MISSION_CURRENT"],
        "mode_transitions": [row.get("mode") for row in events[case_start:] if row["kind"] == "MODE"],
        "final_mode": last_mode, "final_index": last_seq,
    })

    passed = False
    if CASE_ACTION == "reject":
        passed = staged == 0 and speed_count == 0 and mode3_count == 0
    elif CASE_ACTION in ("accept", "speed"):
        passed = staged == 1 and speed_count == 1 and completes == 1
    elif CASE_ACTION == "once":
        passed = staged == 1 and speed_count == 1 and completes == 1 and any("already selected this arm" in t for t in texts)
    elif CASE_ACTION in ("rearm", "arm_cycles"):
        passed = staged == 2 and speed_count == 2 and completes == 2
    elif CASE_ACTION == "high_hold":
        passed = staged == 1 and speed_count == 1 and completes == 1
    elif CASE_ACTION == "pending_edges":
        passed = staged == 1 and speed_count <= 1
    elif CASE_ACTION in ("loiter_init", "loiter_stable", "rtl_pending"):
        requested = 6 if CASE_ACTION == "rtl_pending" else 5
        passed = speed_count == 0 and last_mode == requested and any("externally; no rollback" in t for t in texts)
    elif CASE_ACTION == "disarm_pending":
        passed = speed_count == 0 and any("disarm" in t for t in texts)
    elif CASE_ACTION == "nav_advance":
        passed = speed_count == 0 and any("before speed application" in t or "advanced" in t for t in texts)
    elif CASE_ACTION in ("rollback0", "rollback_nonzero"):
        passed = speed_count == 0 and last_seq == CASE_EXPECTED["rollback"]
    elif CASE_ACTION == "direct_after":
        later = events[result["direct_phase_start"]:]
        passed = staged == 1 and speed_count == 1 and any(row["kind"]=="STATUSTEXT" and "directly; no mission selection" in row["text"] for row in later)
    result["verdict"] = "PASS" if passed else "FAIL"
    event("CASE_COMPLETE", CASE, verdict=result["verdict"])
except Exception as exc:
    result["error"] = repr(exc)
    event("CASE_ERROR", repr(exc))
finally:
    result["nwa_statustext"] = nwa_texts(case_start)
    result["final_mode"] = last_mode
    result["final_index"] = last_seq
    (OUT / "case_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    try:
        if last_mode != 5:
            m.set_mode_apm(5); pump(.2)
        force_disarm(); pump(.2)
    except Exception as exc:
        event("TEARDOWN_ERROR", repr(exc))
    save()
    if result["verdict"] != "PASS":
        sys.exit(2)
