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
    if case in ("persistent", "persistent_repeat"):
        return prefix + [
            item(2, 3, 16, 0, 0, 0, 0, *wp1, 20),
            item(3, 2, 178, 1, 5, -1, 0, 0, 0, 0),
            item(4, 3, 16, 0, 0, 0, 0, *wp2, 20),
            item(5, 3, 16, 0, 0, 0, 0, *wp3, 20),
            item(6, 2, 178, 1, 10, -1, 0, 0, 0, 0),
            item(7, 3, 16, 0, 0, 0, 0, *wp4, 20),
            item(8, 2, 20, 0, 0, 0, 0, 0, 0, 0),
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


mission = mission_for(CASE)


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


def trigger(intervention=None):
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
        if message and message.get_type() == "STATUSTEXT" and message.text == "NWA: AUTO entered":
            intervention()
            event("INTERVENTION", "sent immediately after AUTO entered")
            return
    raise RuntimeError("AUTO entered message not observed for intervention")


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
    ("ARMING_SKIPCHK", 65535),
    ("SCR_ENABLE", 1),
    ("MIS_RESTART", 0),
    ("RC7_OPTION", 300),
    ("WP_SPD", 6),
    ("NWA_ENABLE", 1),
    ("NWA_MAXDIST", 100),
    ("NWA_MINREM", 20),
    ("NWA_DEBUG", 1),
    ("NWA_ONCE", 1),
    ("NWA_AMBIG", 1),
]
if CASE in ("fallback", "direct", "once", "external", "rollback0", "rollback_nonzero"):
    PARAMS += [("NWA_START", 3), ("NWA_END", 4)]
elif CASE in ("persistent", "persistent_repeat", "vertical"):
    PARAMS += [("NWA_START", 4), ("NWA_END", 5)]
elif CASE == "minrem":
    PARAMS += [("NWA_START", 3), ("NWA_END", 4)]


try:
    request_streams()
    for name, value in PARAMS:
        set_param(name, value)
    upload_mission()
    rc7(1000)
    arm_takeoff()
    # Preserve the natural post-upload index 0 for the dedicated rollback0
    # case.  Explicit MISSION_SET_CURRENT(0) is normalized by Copter to the
    # leading TAKEOFF NAV index and would not test index-zero restoration.
    if CASE != "rollback0":
        set_current(0)

    if CASE in ("fallback", "persistent", "persistent_repeat"):
        trigger()
        if not wait_text("scripted entry complete", 6):
            raise RuntimeError("scripted entry did not complete")
        target = 4 if CASE == "fallback" else 5
        next_nav = 6 if CASE == "fallback" else 7
        if not wait_for({"MISSION_CURRENT"}, 55, lambda message: message.seq == next_nav):
            raise RuntimeError(f"mission did not advance from target {target} to {next_nav}")
        pump(8)

    elif CASE == "direct":
        set_mode(5)  # LOITER gives a clean stopped-mission starting mode.
        set_current(2)
        event("DIRECT_AUTO", "ordinary GCS mode request from LOITER", old_seq=2)
        set_mode(3)
        pump(3)

    elif CASE in ("minrem", "vertical"):
        trigger()
        pump(3)

    elif CASE == "once":
        trigger()
        if not wait_text("scripted entry complete", 6):
            raise RuntimeError("first scripted entry did not complete")
        set_mode(5)
        pump(0.5)
        trigger()
        if not wait_text("already selected this arm", 4):
            raise RuntimeError("second same-arm request was not rejected")
        pump(1)
        set_mode(9)  # LAND and allow normal auto-disarm.
        if not wait_disarmed(45):
            raise RuntimeError("LAND did not auto-disarm")
        event("ARM", "auto-disarmed after LAND")
        rc7(1000)
        arm_takeoff()
        trigger()
        if not wait_text("scripted entry complete", 6):
            raise RuntimeError("post-rearm scripted entry did not complete")
        pump(1)

    elif CASE == "external":
        def loiter_now():
            for _ in range(3):
                m.set_mode_apm(5)
                time.sleep(0.005)

        trigger(loiter_now)
        if not wait_text("left AUTO before NAV confirmation", 4):
            raise RuntimeError("LOITER external-mode diagnostic absent")
        pump(1)

        # Repeat for RTL while still armed.  Returning to LOITER first keeps the
        # second entry geometry stable and proves there is no delayed rollback.
        set_mode(5)
        pump(0.5)

        def rtl_now():
            for _ in range(3):
                m.set_mode_apm(6)
                time.sleep(0.005)

        trigger(rtl_now)
        if not wait_text("left AUTO before NAV confirmation", 4):
            raise RuntimeError("RTL external-mode diagnostic absent")
        pump(1.5)

    elif CASE in ("rollback0", "rollback_nonzero"):
        old_seq = 0 if CASE == "rollback0" else 3
        if CASE == "rollback0":
            event("START_INDEX", "preserved natural mission index 0", seq=last_seq)
            if last_seq != 0:
                raise RuntimeError(f"natural mission index is {last_seq}, expected 0")
        else:
            set_current(old_seq)

        def advance_nav():
            # Bypass the instant DO at seq 5 and activate NAV 6.  Pending expects
            # NAV 4, so this should invoke the script-controlled rollback path.
            for _ in range(3):
                m.mav.mission_set_current_send(m.target_system, m.target_component, 6)
                time.sleep(0.005)

        trigger(advance_nav)
        if not wait_text("NAV advanced to 6 before confirmation", 5):
            raise RuntimeError("rollback failure diagnostic absent")
        pump(2)

    else:
        raise RuntimeError(f"unknown case {CASE}")

    event("CASE_COMPLETE", CASE)
finally:
    try:
        # End each case without adding a mission transition to the interval under
        # test.  Forced disarm is only test teardown in SITL.
        if last_mode != 5:
            m.set_mode_apm(5)
            pump(0.5)
        force_disarm()
        pump(0.5)
    except Exception as exc:
        event("TEARDOWN_ERROR", repr(exc))
    save()
