"""Bench session recorder + safety command sender (stage 1, laptop as ground station).

Records to bench/bench_log_<date>.txt:
  ESP32  - its own USB serial output (COM6), the ground truth
  LUX    - STATUSTEXT, S1/S2 (SERVO_OUTPUT_RAW), SD_* values, boot/watchdog, direct on USB (COM9)
  MESH   - what arrives over mesh -> Pi filter -> this laptop (ACKs, STATUSTEXT, SD_* values)
Commands are read from bench/cmd.txt, one per line:
  req | conf | disarm | badkey | builtin_arm | quit
They are sent exactly as the QGC SafetyDevice.json actions, over the mesh through the Pi filter.
"""
import os, sys, socket, threading, time, json
os.environ["MAVLINK20"] = "1"
import serial
from pymavlink import mavutil
mav = mavutil.mavlink

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "bench_log_%s.txt" % time.strftime("%Y-%m-%d"))
CMD = os.path.join(HERE, "cmd.txt")
STATE = os.path.join(HERE, "state.json")
PI = ("10.223.79.20", 14551)
lock = threading.Lock()
t0 = time.time()
state = {"esp": None, "lux": {}, "mesh": {}, "acks": []}
alive = True

def log(src, text):
    line = "%s %8.2f %-5s %s" % (time.strftime("%H:%M:%S"), time.time() - t0, src, text)
    with lock:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def esp_thread():
    s = serial.Serial(); s.port, s.baudrate, s.timeout = "COM6", 115200, 0.3
    s.dtr = False; s.rts = False; s.open(); s.reset_input_buffer()
    buf, last_state = b"", None
    while alive:
        buf += s.read(512)
        while b"\n" in buf:
            l, buf = buf.split(b"\n", 1)
            l = l.decode(errors="replace").strip()
            if not l: continue
            if l.startswith("{"):
                try:
                    j = json.loads(l)
                except ValueError:
                    log("ESP32", "bad json: " + l[:120]); continue
                state["esp"] = j
                key = (j["state"], j["enable"], j["arm"], j["fire"], j["load"], j["remote_hold"], j["faults"])
                if key != last_state or j["state"] == "STANDOFF":
                    log("ESP32", "state=%s en=%d arm=%d(%dus) fire=%d(%dus) hold=%d standoff=%d load=%d fires=%d faults=%d reason=%s up=%d"
                        % (j["state"], j["enable"], j["arm"], j["arm_in_us"], j["fire"], j["fire_in_us"], j["remote_hold"],
                           j["standoff_s"], j["load"], j["fires"], j["faults"], j["fault_reason"], j["uptime_s"]))
                    last_state = key
            else:
                log("ESP32", "event: " + l)

lux_reboot = False

def lux_connect():
    while alive:
        try:
            m = mavutil.mavlink_connection("COM9", baud=115200, source_system=255, source_component=191)
            if m.wait_heartbeat(timeout=5):
                m.mav.command_long_send(1, 1, mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 100000, 0, 0, 0, 0, 0)
                m.mav.command_long_send(1, 1, mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 2, 1000000, 0, 0, 0, 0, 0)
                return m
            m.close()
        except Exception:
            pass
        time.sleep(0.5)

def lux_thread():
    global lux_reboot
    m = lux_connect()
    last_out, last_boot = None, None
    while alive:
        if lux_reboot:
            lux_reboot = False
            m.mav.command_long_send(1, 1, mav.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0)
            log("CMD", "LUX reboot command sent over USB")
            time.sleep(1.5)
            try: m.close()
            except Exception: pass
            m = lux_connect()
            log("LUX", "USB reconnected after reboot")
            continue
        try:
            msg = m.recv_match(blocking=True, timeout=1)
        except Exception:
            log("LUX", "USB link error - reconnecting"); m = lux_connect(); continue
        if not msg: continue
        t = msg.get_type()
        if t == "STATUSTEXT":
            txt = msg.text.rstrip("\x00")
            if "waiting for terrain" in txt or "Battery 1 critical" in txt: continue
            log("LUX", "[%d] %s" % (msg.severity, txt))
        elif t == "SERVO_OUTPUT_RAW" and msg.port == 0:
            out = (msg.servo9_raw, msg.servo10_raw)
            state["lux"]["S1"], state["lux"]["S2"] = out
            if out != last_out:
                log("LUX", "S1=%d S2=%d" % out); last_out = out
        elif t == "NAMED_VALUE_FLOAT":
            state["lux"][msg.name.rstrip("\x00")] = msg.value
        elif t == "SYSTEM_TIME":
            b = msg.time_boot_ms / 1000.0
            if last_boot is not None and b < last_boot:
                log("LUX", "!!! LUX REBOOTED (uptime went %.0f -> %.0f s)" % (last_boot, b))
            last_boot = b; state["lux"]["uptime"] = round(b)

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(("0.0.0.0", 14560)); udp.settimeout(0.3)
enc = mav.MAVLink(None, srcSystem=255, srcComponent=190)
parser = mav.MAVLink(None); parser.robust_parsing = True

def send(msg): udp.sendto(msg.pack(enc), PI)

def mesh_thread():
    last_named = {}
    while alive:
        try:
            data, _ = udp.recvfrom(65535)
        except (socket.timeout, OSError):
            continue
        for m in parser.parse_buffer(data) or []:
            t = m.get_type()
            if t == "COMMAND_ACK" and m.command == 31010:
                state["acks"].append((time.time(), m.result, m.result_param2))
                log("MESH", "ACK safety action %d -> %s" % (m.result_param2, {0: "ACCEPTED", 2: "DENIED"}.get(m.result, m.result)))
            elif t == "COMMAND_ACK":
                if m.command in (400, 183, 187): log("MESH", "!!! ACK for blocked command %d -> %d" % (m.command, m.result))
            elif t == "STATUSTEXT":
                txt = m.text.rstrip("\x00")
                if txt.startswith(("Safety", "Standoff", "Transmitter")):
                    log("MESH", "[%d] %s" % (m.severity, txt))
            elif t == "NAMED_VALUE_FLOAT":
                n = m.name.rstrip("\x00"); state["mesh"][n] = m.value
            elif t == "HEARTBEAT":
                state["mesh"]["hb"] = round(time.time() - t0, 1)

def hb_thread():
    while alive:
        send(mav.MAVLink_heartbeat_message(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0, 3))
        time.sleep(1)

ACTIONS = {"disarm": (0, 7713), "req": (1, 7713), "conf": (2, 7713), "badkey": (1, 1234)}
for fn in (esp_thread, lux_thread, mesh_thread, hb_thread):
    threading.Thread(target=fn, daemon=True).start()
log("INFO", "bench session started; log " + LOG)
open(CMD, "a").close()
done = len(open(CMD).read().splitlines())
while alive:
    lines = open(CMD).read().splitlines()
    for c in lines[done:]:
        c = c.strip().lower()
        if c in ACTIONS:
            a, k = ACTIONS[c]
            send(mav.MAVLink_command_long_message(1, 1, 31010, 0, a, k, 0, 0, 0, 0, 0))
            log("CMD", "sent safety %s (param1=%d key=%d) over mesh" % (c, a, k))
        elif c == "builtin_arm":
            send(mav.MAVLink_command_long_message(1, 1, 400, 0, 1, 0, 0, 0, 0, 0, 0))
            log("CMD", "sent QGC built-in vehicle ARM (400) - filter must block it")
        elif c == "lux_reboot":
            lux_reboot = True
        elif c == "quit":
            alive = False
        elif c:
            log("CMD", "unknown command " + c)
    done = len(lines)
    with open(STATE, "w") as f:
        json.dump({"t": round(time.time() - t0, 1), **state, "acks": state["acks"][-3:]}, f, default=str)
    time.sleep(0.2)
log("INFO", "bench session stopped")
