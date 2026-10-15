"""Filtered MAVLink bridge: LUX F765 serial <-> QGC over the mesh (UDP).

Runs on the Pi. Everything from the flight controller is forwarded to QGC.
From QGC, only the same traffic the bench relay (tmp/qgc_readonly_udp_relay.py)
allowed is passed, plus exactly one addition: the safety-device command
(MAV_CMD_USER_1 = 31010, param1 in {0,1,2}, param2 = 7713, params 3-7 = 0).

Still blocked: parameter writes, vehicle arm/disarm, mode changes, manual
control, RC overrides, actuator/servo commands, fence and rally writes, and any
other COMMAND_LONG/COMMAND_INT.

Nothing is queued: a request is written to the serial port as soon as it is
received, or dropped.

Usage:
  python3 safety_mavlink_filter.py --serial /dev/serial0 --baud 115200 \
      --udp-target 10.223.58.11:14550 --udp-listen 14551
"""

import argparse
import json
import os
import socket
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("MAVLINK20", "1")   # QGC and ArduPilot speak MAVLink 2
from pymavlink import mavutil  # noqa: E402

mavutil.set_dialect("ardupilotmega")
mav = mavutil.mavlink

SAFE_MESSAGE_TYPES = {
    "AUTOPILOT_VERSION_REQUEST",
    "HEARTBEAT",
    "MISSION_ACK",
    "MISSION_REQUEST",
    "MISSION_REQUEST_INT",
    "MISSION_REQUEST_LIST",
    "PARAM_EXT_REQUEST_LIST",
    "PARAM_EXT_REQUEST_READ",
    "PARAM_REQUEST_LIST",
    "PARAM_REQUEST_READ",
    "PING",
    "REQUEST_DATA_STREAM",
    "TIMESYNC",
}

MISSION_WRITE_TYPES = {
    "MISSION_CLEAR_ALL",
    "MISSION_COUNT",
    "MISSION_ITEM",
    "MISSION_ITEM_INT",
    "MISSION_WRITE_PARTIAL_LIST",
}

SAFE_COMMANDS = {
    mav.MAV_CMD_GET_HOME_POSITION,
    mav.MAV_CMD_SET_MESSAGE_INTERVAL,
    mav.MAV_CMD_REQUEST_MESSAGE,
    mav.MAV_CMD_REQUEST_PROTOCOL_VERSION,
    mav.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES,
    mav.MAV_CMD_REQUEST_CAMERA_INFORMATION,
}

SAFETY_CMD = 31010
SAFETY_KEY = 7713.0
SAFETY_ACTIONS = {0.0, 1.0, 2.0}


def safety_command_ok(request):
    """Exact shape of the three QGC safety actions; anything else is dropped."""
    return (
        int(request.command) == SAFETY_CMD
        and request.param1 in SAFETY_ACTIONS
        and request.param2 == SAFETY_KEY
        and request.param3 == 0.0
        and request.param4 == 0.0
        and request.param5 == 0.0
        and request.param6 == 0.0
        and request.param7 == 0.0
    )


def is_allowed(request):
    request_type = request.get_type()
    if request_type in SAFE_MESSAGE_TYPES:
        return True
    if request_type in MISSION_WRITE_TYPES:
        mission_type = getattr(request, "mission_type", mav.MAV_MISSION_TYPE_MISSION)
        return mission_type == mav.MAV_MISSION_TYPE_MISSION
    if request_type == "COMMAND_LONG":
        return int(request.command) in SAFE_COMMANDS or safety_command_ok(request)
    return False


def parse_hostport(text):
    host, port = text.rsplit(":", 1)
    return host, int(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--udp-target", type=parse_hostport, required=True,
                    help="QGC address, e.g. the Galaxy on the mesh 10.223.58.11:14550")
    ap.add_argument("--udp-listen", type=int, default=14551)
    ap.add_argument("--status", type=Path, default=Path("/tmp/safety_mavlink_filter_status.json"))
    args = ap.parse_args()

    link = mavutil.mavlink_connection(args.serial, baud=args.baud, autoreconnect=True)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("0.0.0.0", args.udp_listen))
    udp.setblocking(False)
    # Optional read-only fleet copy. Missing observer never blocks the pilot path.
    mirror = None
    if os.environ.get("CRUZA_FLEET_MIRROR", "0") == "1":
        mirror = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        mirror.setblocking(False)

    parser = mav.MAVLink(None)
    parser.robust_parsing = True

    counts = Counter()
    blocked = Counter()
    safety_forwarded = Counter()
    last_phone = None
    last_status = 0.0
    started = time.time()

    while True:
        message = link.recv_msg()
        if message is not None:
            payload = message.get_msgbuf()
            if payload:
                if mirror is not None:
                    try:
                        mirror.sendto(payload, ("127.0.0.1", 15612))
                    except OSError:
                        pass
                udp.sendto(payload, args.udp_target)
                if last_phone and last_phone != args.udp_target:
                    udp.sendto(payload, last_phone)
                counts["to_qgc"] += 1
        else:
            time.sleep(0.002)

        while True:
            try:
                datagram, sender = udp.recvfrom(65535)
            except BlockingIOError:
                break
            last_phone = sender
            for request in parser.parse_buffer(datagram) or []:
                if is_allowed(request):
                    link.write(request.get_msgbuf())
                    counts["to_fc"] += 1
                    if request.get_type() == "COMMAND_LONG" and int(request.command) == SAFETY_CMD:
                        safety_forwarded[int(request.param1)] += 1
                else:
                    blocked[request.get_type()] += 1

        now = time.time()
        if now - last_status >= 2:
            args.status.write_text(json.dumps({
                "mode": "filtered mission management + safety command",
                "serial": args.serial,
                "udp_target": "%s:%d" % args.udp_target,
                "last_phone": "%s:%d" % last_phone if last_phone else None,
                "counts": dict(counts),
                "blocked": dict(blocked),
                "safety_forwarded_by_action": {str(k): v for k, v in safety_forwarded.items()},
                "uptime_s": round(now - started, 1),
            }, indent=2), encoding="utf-8")
            last_status = now


if __name__ == "__main__":
    main()
