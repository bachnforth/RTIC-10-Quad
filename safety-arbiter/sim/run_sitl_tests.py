"""Closed-loop SITL test of safety_arbiter.lua.

  ArduCopter 4.7.1 SITL  (SERVO9=Script1, SERVO10=Script2, SERIAL2=Scripting)
    serial0 tcp:5760  <- instrument: RC overrides (SB/SE), SERVO_OUTPUT_RAW, params
    serial1 tcp:5762  <- pi/safety_mavlink_filter.py <- UDP <- "QGC" (this script)
    serial2 tcp:5763  <- ESP32 model (esp32_model.py) sending its JSON status

The ESP32 model reads S1/S2 from SERVO_OUTPUT_RAW; missing data for 250 ms is
treated as "no pulses", as the real input capture would see it.

Usage: python run_sitl_tests.py <sitl_dir> <results_dir>
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("MAVLINK20", "1")
from pymavlink import mavutil  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from esp32_model import Esp32Model  # noqa: E402

mavutil.set_dialect("ardupilotmega")
mav = mavutil.mavlink

HERE = Path(__file__).resolve().parent
FILTER = HERE.parent / "pi" / "safety_mavlink_filter.py"
SAFETY_CMD, KEY = 31010, 7713
DISARM, REQUEST, CONFIRM = 0, 1, 2
SB_UP, SB_DOWN, SE_PRESS, SE_REL = 2000, 1000, 1900, 1100

SIM_PARAMS = """
SCR_ENABLE 1
SCR_HEAP_SIZE 102400
SERVO9_FUNCTION 94
SERVO10_FUNCTION 95
SERVO9_MIN 1100
SERVO9_TRIM 1500
SERVO9_MAX 1900
SERVO10_MIN 1100
SERVO10_TRIM 1500
SERVO10_MAX 1900
SERIAL1_PROTOCOL 2
SERIAL2_PROTOCOL 28
SERIAL2_BAUD 115
RC6_MIN 999
RC6_TRIM 1503
RC6_MAX 2000
RC9_MIN 1100
RC9_TRIM 1500
RC9_MAX 1900
RC_OVERRIDE_TIME 3
MAV_GCS_SYSID 255
FS_THR_ENABLE 1
SIM_RC_FAIL 0
"""


def ms():
    return int(time.monotonic() * 1000)


class Log:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        self.t0 = time.monotonic()
        self.lock = threading.Lock()

    def __call__(self, text):
        line = "%8.2f  %s" % (time.monotonic() - self.t0, text)
        with self.lock:
            print(line, flush=True)
            self.f.write(line + "\n")
            self.f.flush()


# ---------------------------------------------------------------- SITL process
class Sitl:
    def __init__(self, sitl_dir, log):
        self.dir = Path(sitl_dir)
        self.log = log
        self.proc = None
        self.parm = self.dir / "safety_test.parm"
        base = (self.dir / "default_params" / "copter.parm").read_text()
        self.parm.write_text(base + "\n" + SIM_PARAMS)

    def start(self, wipe):
        args = [str(self.dir / "ArduCopter.exe"), "-M+", "-O35.0495395,-79.4901843,100,0",
                "-s1", "--serial0", "tcp:0", "--serial1", "tcp:2", "--serial2", "tcp:3",
                "--defaults", str(self.parm)]
        if wipe:
            args.insert(1, "-w")
        out = open(self.dir / "sitl_stdout.txt", "a")
        self.proc = subprocess.Popen(args, cwd=self.dir, stdout=out, stderr=subprocess.STDOUT)
        self.log("SITL started (wipe=%s) pid %d" % (wipe, self.proc.pid))

    def kill(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.log("SITL killed (simulated LUX power loss)")
            self.proc = None


# ---------------------------------------------------------------- instrument
class Instrument:
    """Test-bench view of the LUX: RC overrides, outputs, params, messages."""

    def __init__(self, log):
        self.log = log
        self.conn = None
        self.lock = threading.Lock()
        self.s1 = self.s2 = None
        self.servo_ms = 0
        self.named = {}
        self.texts = []
        self.acks = []
        self.sb, self.se = SB_DOWN, SE_REL
        self.overrides_on = True
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._rc_sender, daemon=True).start()

    def connect(self):
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                c = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=255,
                                               source_component=191, autoreconnect=False)
                if c.wait_heartbeat(timeout=5):
                    self.conn = c
                    self.send(lambda m: m.command_long_send(1, 1, mav.MAV_CMD_SET_MESSAGE_INTERVAL,
                                                            0, 36, 20000, 0, 0, 0, 0, 0))
                    self.log("instrument connected")
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError("no SITL heartbeat")

    def drop(self):
        c, self.conn = self.conn, None
        if c:
            try:
                c.close()
            except Exception:
                pass

    def send(self, fn):
        with self.lock:
            if self.conn:
                try:
                    fn(self.conn.mav)
                except OSError:
                    pass

    def _reader(self):
        while self.alive:
            c = self.conn
            if c is None:
                time.sleep(0.05)
                continue
            try:
                m = c.recv_match(blocking=True, timeout=0.2)
            except Exception:
                time.sleep(0.05)
                continue
            if m is None:
                continue
            t = m.get_type()
            if t == "SERVO_OUTPUT_RAW" and m.port == 0:
                self.s1, self.s2, self.servo_ms = m.servo9_raw, m.servo10_raw, ms()
            elif t == "NAMED_VALUE_FLOAT":
                self.named[m.name.rstrip("\x00")] = m.value
            elif t == "STATUSTEXT":
                self.texts.append((ms(), m.severity, m.text.rstrip("\x00")))
                self.log("  LUX> [%d] %s" % (m.severity, m.text.rstrip("\x00")))
            elif t == "COMMAND_ACK":
                self.acks.append((ms(), m.command, m.result))

    def _rc_sender(self):
        while self.alive:
            if self.overrides_on:
                ign = 65535
                self.send(lambda m: m.rc_channels_override_send(
                    1, 1, 0, 0, 0, 0, 0, self.sb, 0, 0,
                    self.se, ign, ign, ign, ign, ign, ign, ign, ign, ign))
            time.sleep(0.1)

    def outputs(self):
        """(S1, S2) as the ESP32 input capture would see them; -2 = no pulses."""
        if ms() - self.servo_ms > 250 or self.s1 is None:
            return -2, -2
        return self.s1, self.s2

    def set_param(self, name, value):
        self.send(lambda m: m.param_set_send(1, 1, name.encode(), float(value),
                                             mav.MAV_PARAM_TYPE_REAL32))

    def command(self, action, key=KEY):
        self.send(lambda m: m.command_long_send(1, 1, SAFETY_CMD, 0, action, key, 0, 0, 0, 0, 0))


# ---------------------------------------------------------------- ESP32 link
class Esp32Link:
    def __init__(self, inst, log):
        self.inst = inst
        self.log = log
        self.model = Esp32Model(ms())
        self.sock = None
        self.alive = True
        self.logged = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.alive:
            now = ms()
            s1, s2 = self.inst.outputs()
            self.model.step(now, s1, s2)
            while self.logged < len(self.model.log):
                self.log("  ESP32> %s" % self.model.log[self.logged][1])
                self.logged += 1
            if self.model.json_due(now):
                line = self.model.json_line(now).encode()
                try:
                    if self.sock is None:
                        self.sock = socket.create_connection(("127.0.0.1", 5763), timeout=0.5)
                    self.sock.sendall(line)
                except OSError:
                    if self.sock:
                        self.sock.close()
                    self.sock = None
            time.sleep(0.005)


# ---------------------------------------------------------------- QGC via filter
class Qgc:
    def __init__(self, log, sysid=255):
        self.log = log
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 14560))
        self.sock.settimeout(0.2)
        self.enc = {s: mav.MAVLink(None, srcSystem=s, srcComponent=190) for s in (255, 42)}
        self.parser = mav.MAVLink(None)
        self.parser.robust_parsing = True
        self.acks = []
        self.texts = []
        self.named = {}
        self.panel = []            # (ms, status, runtime) from GENERATOR_STATUS
        self.heartbeats = True
        self.alive = True
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._hb, daemon=True).start()

    def _send(self, msg, sysid=255):
        self.sock.sendto(msg.pack(self.enc[sysid]), ("127.0.0.1", 14561))

    def _hb(self):
        while self.alive:
            if self.heartbeats:
                self._send(mav.MAVLink_heartbeat_message(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID,
                                                         0, 0, 0, 3))
            time.sleep(1)

    def _rx(self):
        while self.alive:
            try:
                data, _ = self.sock.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            for m in self.parser.parse_buffer(data) or []:
                t = m.get_type()
                if t == "COMMAND_ACK":
                    self.acks.append((ms(), m.command, m.result, m.result_param2))
                    self.log("  QGC< ACK cmd %d result %d action %d" % (m.command, m.result, m.result_param2))
                elif t == "STATUSTEXT":
                    self.texts.append((ms(), m.severity, m.text.rstrip("\x00")))
                elif t == "NAMED_VALUE_FLOAT":
                    self.named[m.name.rstrip("\x00")] = m.value
                elif t == "GENERATOR_STATUS":
                    self.panel.append((ms(), m.status, m.runtime))

    def command_long(self, command, p1=0, p2=0, sysid=255):
        self._send(mav.MAVLink_command_long_message(1, 1, command, 0, p1, p2, 0, 0, 0, 0, 0), sysid)

    def safety(self, action, key=KEY, sysid=255, wait=3.0):
        """Send like QGC's MavlinkAction; return ACK result or None on timeout."""
        start = ms()
        seen = len(self.acks)
        self.command_long(SAFETY_CMD, action, key, sysid)
        while ms() - start < wait * 1000:
            for t, cmd, res, act in self.acks[seen:]:
                if cmd == SAFETY_CMD and act == action:
                    return res
            time.sleep(0.02)
        return None


# ---------------------------------------------------------------- test runner
class Runner:
    def __init__(self, sitl_dir, results):
        self.results_dir = Path(results)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.log = Log(self.results_dir / "sitl_test_log.txt")
        self.sitl = Sitl(sitl_dir, self.log)
        self.checks = []
        self.filter_proc = None

    # -- infrastructure --
    def start_filter(self):
        env = dict(os.environ)
        self.filter_proc = subprocess.Popen(
            [sys.executable, str(FILTER), "--serial", "tcp:127.0.0.1:5762",
             "--udp-target", "127.0.0.1:14560", "--udp-listen", "14561",
             "--status", str(self.results_dir / "filter_status.json")],
            env=env, stdout=open(self.results_dir / "filter_stdout.txt", "a"),
            stderr=subprocess.STDOUT)
        self.log("filter started pid %d" % self.filter_proc.pid)

    def stop_filter(self):
        if self.filter_proc:
            self.filter_proc.kill()
            self.filter_proc.wait()
            self.filter_proc = None
            self.log("filter stopped (app link lost)")

    def check(self, name, ok, evidence=""):
        self.checks.append({"check": name, "pass": bool(ok), "evidence": evidence})
        self.log("%s  %s  %s" % ("PASS" if ok else "FAIL", name, evidence))

    def wait(self, pred, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if pred():
                return True
            time.sleep(0.02)
        return pred()

    def st(self):
        return self.esp.model.state

    def outs(self):
        return self.inst.outputs()

    def settle(self, s=1.0):
        time.sleep(s)

    def to_safe(self):
        """Return to a clean SAFE baseline between tests."""
        self.inst.overrides_on = True
        self.inst.set_param("SIM_RC_FAIL", 0)
        self.esp.model.contact = False
        self.inst.se = SE_REL
        self.qgc.safety(DISARM)
        self.inst.sb = SB_DOWN
        self.settle(1.0)
        if self.st() == "FAULT":
            self.esp.model.sw1_enable = False
            self.settle(0.3)
            self.esp.model.sw1_enable = True
            self.settle(0.3)
            self.esp.model.sw1_enable = False
            self.settle(0.3)
        self.esp.model.sw1_enable = True
        self.settle(0.5)

    def arm_and_time(self, how):
        """Start an arm via SB or app; return (t_S1_asserted, t_ARMED) in ms."""
        t_cmd = ms()
        if how == "SB":
            self.inst.sb = SB_UP
        else:
            self.qgc.safety(REQUEST)
            self.qgc.safety(CONFIRM)
        self.wait(lambda: self.outs()[0] == 1900, 3)
        t_s1 = ms()
        self.wait(lambda: self.st() == "STANDOFF", 3)
        armed = self.wait(lambda: self.st() == "ARMED", 36)
        return t_cmd, t_s1, ms() if armed else None

    # -- tests --
    def run(self):
        self.sitl.start(wipe=True)
        self.inst = Instrument(self.log)
        self.esp = Esp32Link(self.inst, self.log)   # ESP32 powered with the LUX
        self.inst.connect()
        self.start_filter()
        self.qgc = Qgc(self.log)
        try:
            self.t_boot()
            self.t_sb_only()
            self.t_app_only()
            self.t_rejections()
            self.t_conflicts()
            self.t_tx_loss()
            self.t_app_link_loss()
            self.t_fire_before_armed()
            self.t_script_stop()
            self.t_lux_reboot()
        finally:
            self.finish()

    def t_boot(self):
        self.log("=== T1 boot defaults ===")
        ok = self.wait(lambda: self.inst.named.get("SD_STATE") is not None, 20)
        self.settle(2)
        s1, s2 = self.outs()
        self.check("T1 arbiter running and publishing status", ok, str(self.inst.named))
        self.check("T1 ARM request cleared at boot", self.inst.named.get("SD_REQ") == 0,
                   "SD_REQ=%s" % self.inst.named.get("SD_REQ"))
        self.check("T1 S1 released after status seen (ESP32 not ARMED)", s1 == 1100, "S1=%s" % s1)
        self.check("T1 S2 released", s2 == 1100, "S2=%s" % s2)
        self.check("T1 ESP32 not armed after boot", self.st() in ("SAFE", "FAULT"),
                   "state=%s reason=%s" % (self.st(), self.esp.model.fault_reason))
        # Power-up Code 5 (no pulses while the LUX boots) is cleared as today:
        # SW1 to ENABLE and back to SAFE.
        self.to_safe()
        self.check("T1 fault cleared by SW1 cycle -> SAFE", self.st() == "SAFE", self.st())

    def t_sb_only(self):
        self.log("=== T2 SB-only, full standoff ===")
        t_cmd, t_s1, t_armed = self.arm_and_time("SB")
        self.check("T2 SB up asserts S1 within 0.5 s", t_s1 - t_cmd < 500, "%d ms" % (t_s1 - t_cmd))
        self.check("T2 ARMED via SB", t_armed is not None)
        if t_armed:
            d = t_armed - t_s1
            self.check("T2 standoff 31.5 s (+-0.3)", 31200 <= d <= 31900, "%d ms S1->ARMED" % d)
        run = [p for p in self.qgc.panel if p[0] >= t_s1 and p[1] == 1]
        cds = sorted({p[2] for p in run}, reverse=True)
        self.check("T2 Fly View panel: status 1 (STANDOFF), runtime counting 31..1",
                   len(cds) >= 25 and cds[0] >= 30 and cds[-1] <= 2,
                   "runtime %s..%s (%d distinct)" % (cds[:3], cds[-3:], len(cds)))
        def armed_panel():
            return [p for p in self.qgc.panel if t_armed and p[0] >= t_armed + 1000]
        ok = self.wait(lambda: bool(armed_panel()) and armed_panel()[-1][1:] == (2, 0), 3)
        self.check("T2 Fly View panel: status 2 (ARMED), runtime 0", ok,
                   str(armed_panel()[-1] if armed_panel() else None))
        loud = [t for t in self.qgc.texts if t[1] <= 5
                and t[2].startswith(("Safety", "Standoff", "Transmitter"))]
        self.check("T2 no spoken (NOTICE or higher) Safety messages", not loud, str(loud[:3]))
        self.inst.sb = SB_DOWN
        self.check("T2 SB down -> SAFE", self.wait(lambda: self.st() == "SAFE", 2), self.st())

    def t_app_only(self):
        self.log("=== T3 app-only ===")
        r = self.qgc.safety(CONFIRM)
        self.check("T3 CONFIRM without REQUEST denied", r == 2, "ACK=%s" % r)
        r1 = self.qgc.safety(REQUEST)
        self.settle(10.5)
        r2 = self.qgc.safety(CONFIRM)
        self.check("T3 CONFIRM after 10 s window denied", r1 == 0 and r2 == 2, "ACKs=%s,%s" % (r1, r2))
        self.check("T3 no arm from expired request", self.outs()[0] == 1100 and self.st() == "SAFE")
        t_cmd, t_s1, t_armed = self.arm_and_time("app")
        self.check("T3 app REQUEST+CONFIRM asserts S1", t_s1 - t_cmd < 1500, "%d ms" % (t_s1 - t_cmd))
        self.check("T3 ARMED via app", t_armed is not None)
        if t_armed:
            d = t_armed - t_s1
            self.check("T3 standoff 31.5 s (+-0.3)", 31200 <= d <= 31900, "%d ms" % d)
        self.check("T3 QGC sees ESP32 ARMED (SD_STATE=2)",
                   self.wait(lambda: self.qgc.named.get("SD_STATE") == 2, 2),
                   "SD_STATE=%s" % self.qgc.named.get("SD_STATE"))
        r = self.qgc.safety(DISARM)
        self.check("T3/T6 app DISARM while ARMED -> SAFE",
                   r == 0 and self.wait(lambda: self.st() == "SAFE", 2), "ACK=%s %s" % (r, self.st()))
        self.check("T3 QGC sees SAFE (SD_STATE=0)",
                   self.wait(lambda: self.qgc.named.get("SD_STATE") == 0, 3))

    def t_rejections(self):
        self.log("=== rejections ===")
        before = len(self.inst.texts)
        r = self.qgc.safety(REQUEST, key=1234)
        self.check("R1 wrong key blocked by Pi filter (no ACK)", r is None, "ACK=%s" % r)
        self.inst.command(REQUEST, key=1234)
        self.settle(0.5)
        self.inst.command(CONFIRM, key=1234)
        self.settle(0.5)
        denied = [t for t in self.inst.texts[before:] if "denied" in t[2]]
        self.check("R2 wrong key reaching LUX directly denied", len(denied) >= 2, str(denied))
        self.inst.command(float("nan"))
        self.inst.command(1e30)
        self.settle(1.0)
        r = self.qgc.safety(DISARM)
        stopped = any("STOPPED" in t[2] for t in self.inst.texts)
        self.check("R2b NaN/huge action does not stop the arbiter", r == 0 and not stopped,
                   "ACK after=%s stopped=%s" % (r, stopped))
        r = self.qgc.safety(REQUEST, sysid=42)
        self.check("R3 wrong sender system ID denied", r == 2, "ACK=%s" % r)
        self.check("R1-3 nothing asserted", self.outs()[0] == 1100 and self.st() == "SAFE")
        seen = len(self.qgc.acks)
        self.qgc.command_long(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        self.qgc.command_long(mav.MAV_CMD_DO_SET_SERVO, 9, 1900)
        status_path = self.results_dir / "filter_status.json"
        counted = self.wait(lambda: json.loads(status_path.read_text())["blocked"]
                            .get("COMMAND_LONG", 0) >= 3, 5)
        # ArduPilot ACKs every COMMAND_LONG it receives; none may come back.
        leaked = [a for a in self.qgc.acks[seen:] if a[1] in (400, 183)]
        self.check("R4 QGC vehicle Arm and DO_SET_SERVO blocked by filter",
                   counted and not leaked and self.outs()[0] == 1100,
                   "blocked=%s leaked_acks=%s" % (json.loads(status_path.read_text())["blocked"], leaked))

    def t_conflicts(self):
        self.log("=== T4 conflicting commands ===")
        self.inst.sb = SB_UP
        self.wait(lambda: self.st() == "STANDOFF", 3)
        r = self.qgc.safety(DISARM)
        ok = self.wait(lambda: self.outs()[0] == 1100 and self.st() == "SAFE", 2)
        self.check("T4 app DISARM overrides SB held up", r == 0 and ok, "S1=%s %s" % (self.outs()[0], self.st()))
        self.settle(3)
        self.check("T4 stays disarmed while SB remains up", self.outs()[0] == 1100 and self.st() == "SAFE")
        self.inst.sb = SB_DOWN
        self.settle(0.5)
        self.inst.sb = SB_UP
        self.check("T4 SB cycle down/up re-arms", self.wait(lambda: self.st() == "STANDOFF", 3), self.st())
        self.inst.sb = SB_DOWN
        self.wait(lambda: self.st() == "SAFE", 2)
        self.qgc.safety(REQUEST)
        self.qgc.safety(CONFIRM)
        self.wait(lambda: self.st() == "STANDOFF", 3)
        self.inst.sb = SB_UP
        self.settle(0.5)
        self.inst.sb = SB_DOWN
        self.check("T4 SB down clears an app ARM (last command wins)",
                   self.wait(lambda: self.st() == "SAFE", 2), self.st())

    def t_tx_loss(self):
        self.log("=== T7 transmitter loss ===")
        # (a) standoff started by SB continues through TX loss
        self.inst.sb = SB_UP
        self.wait(lambda: self.st() == "STANDOFF", 3)
        t_s1 = ms()
        self.settle(3)
        self.inst.overrides_on = False
        self.inst.set_param("SIM_RC_FAIL", 1)
        lost = self.wait(lambda: self.inst.named.get("SD_TXOK") == 0, 8)
        self.check("T7 transmitter loss detected", lost)
        self.check("T7 S1 stays asserted, S2 released during loss",
                   self.outs() == (1900, 1100), "S1,S2=%s" % (self.outs(),))
        armed = self.wait(lambda: self.st() == "ARMED", 36)
        self.check("T7 standoff completes to ARMED without transmitter", armed,
                   "%d ms after S1 assert" % (ms() - t_s1))
        # (b) contact fires while armed with no transmitter
        self.esp.model.contact = True
        fired = self.wait(lambda: self.esp.model.load, 1)
        self.esp.model.contact = False
        self.check("T7 deflection contact fires while TX lost", fired)
        self.check("T7 load off after contact opens", self.wait(lambda: not self.esp.model.load, 1))
        # (c) app works with no transmitter
        r = self.qgc.safety(DISARM)
        self.check("T7 app DISARM with TX lost -> SAFE", r == 0 and self.wait(lambda: self.st() == "SAFE", 2))
        self.qgc.safety(REQUEST)
        self.qgc.safety(CONFIRM)
        self.check("T7 app ARM with TX lost starts standoff (no Code 5)",
                   self.wait(lambda: self.st() == "STANDOFF", 3), self.st())
        armed = self.wait(lambda: self.st() == "ARMED", 36)
        self.check("T7 app ARM with TX lost reaches ARMED", armed)
        # (d) TX returns with SE held pressed: FIRE stays gated until released
        self.inst.se = SE_PRESS
        self.inst.sb = SB_UP
        self.inst.overrides_on = True
        self.settle(0.5)
        self.inst.set_param("SIM_RC_FAIL", 0)
        self.wait(lambda: self.inst.named.get("SD_TXOK") == 1, 8)
        self.settle(1.5)
        self.check("T7 TX return with SE held: S2 stays released, no fire",
                   self.outs()[1] == 1100 and not self.esp.model.load and self.st() == "ARMED",
                   "S2=%s load=%s" % (self.outs()[1], self.esp.model.load))
        self.inst.se = SE_REL
        self.settle(0.5)
        self.inst.se = SE_PRESS
        fired = self.wait(lambda: self.esp.model.load, 1.5)
        self.inst.se = SE_REL
        self.check("T7 fresh SE press after return fires", fired)
        self.check("T7 app ARM survives TX return with SB up (no edge)", self.st() == "ARMED")
        self.inst.sb = SB_DOWN
        self.check("T7 SB down disarms after return", self.wait(lambda: self.st() == "SAFE", 2), self.st())

    def t_app_link_loss(self):
        self.log("=== T8 app link loss ===")
        self.qgc.safety(REQUEST)
        self.qgc.safety(CONFIRM)
        self.wait(lambda: self.st() == "STANDOFF", 3)
        t = ms()
        self.settle(3)
        self.qgc.heartbeats = False
        self.stop_filter()
        armed = self.wait(lambda: self.st() == "ARMED", 36)
        self.check("T8 standoff completes to ARMED with app link down", armed, "%d ms" % (ms() - t))
        self.settle(3)
        self.check("T8 stays ARMED with app link down", self.st() == "ARMED" and self.outs()[0] == 1900)
        self.start_filter()
        self.qgc.heartbeats = True
        self.settle(3)
        r = self.qgc.safety(DISARM)
        self.check("T8 DISARM after link restored", r == 0 and self.wait(lambda: self.st() == "SAFE", 2))

    def t_fire_before_armed(self):
        self.log("=== T10 FIRE before ARMED ===")
        self.inst.se = SE_PRESS
        f = self.wait(lambda: self.st() == "FAULT" and "FIRE WHILE SAFE" in self.esp.model.fault_reason, 2)
        self.check("T10 SE in SAFE -> Code 3, no load", f and not self.esp.model.load,
                   self.esp.model.fault_reason)
        self.check("T10 Fly View panel shows 33 (FAULT code 3)",
                   self.wait(lambda: bool(self.qgc.panel) and self.qgc.panel[-1][1] == 33, 3),
                   str(self.qgc.panel[-1] if self.qgc.panel else None))
        self.inst.se = SE_REL
        self.check("T10 Code 3 clears after released inputs", self.wait(lambda: self.st() == "SAFE", 3), self.st())
        self.inst.sb = SB_UP
        self.wait(lambda: self.st() == "STANDOFF", 3)
        self.inst.se = SE_PRESS
        f = self.wait(lambda: self.st() == "FAULT", 2)
        self.check("T10 SE during standoff -> Code 3, no load", f and not self.esp.model.load,
                   self.esp.model.fault_reason)
        self.inst.se = SE_REL
        self.inst.sb = SB_DOWN
        self.check("T10 recovered by SB down", self.wait(lambda: self.st() == "SAFE", 3), self.st())
        self.esp.model.contact = True
        f = self.wait(lambda: self.st() == "FAULT", 1)
        self.esp.model.contact = False
        self.check("T10 contact in SAFE -> Code 3, no load", f and not self.esp.model.load)
        self.to_safe()

    def t_script_stop(self):
        self.log("=== T11 arbiter script stops while ARMED ===")
        fires_before = self.esp.model.load_on_count
        self.qgc.safety(REQUEST)
        self.qgc.safety(CONFIRM)
        self.check("T11 ARMED before script stop", self.wait(lambda: self.st() == "ARMED", 36))
        # MAV_CMD_SCRIPTING, SCRIPTING_CMD_STOP: every script ends, as after a Lua error
        self.inst.send(lambda m: m.command_long_send(1, 1, 42701, 0, 2, 0, 0, 0, 0, 0, 0))
        fell = self.wait(lambda: self.outs() == (1500, 1500), 2)
        self.check("T11 S1/S2 fall back to 1500 (not frozen at 1900/1100)", fell,
                   "S1,S2=%s" % (self.outs(),))
        self.settle(2)
        self.check("T11 ESP32 holds ARMED with the arbiter stopped",
                   self.st() == "ARMED" and self.esp.model.remote_hold,
                   "state=%s hold=%s" % (self.st(), self.esp.model.remote_hold))
        self.esp.model.contact = True
        fired = self.wait(lambda: self.esp.model.load, 1)
        self.esp.model.contact = False
        self.check("T11 contact fires with the arbiter stopped", fired)
        self.wait(lambda: not self.esp.model.load, 1)
        # SCRIPTING_CMD_STOP_AND_RESTART: arbiter comes back, sees ARMED, holds
        self.inst.send(lambda m: m.command_long_send(1, 1, 42701, 0, 3, 0, 0, 0, 0, 0, 0))
        back = self.wait(lambda: self.inst.named.get("SD_REQ") == 2 and self.outs()[0] == 1500, 15)
        self.check("T11 after restart the arbiter holds (boot hold) and ESP32 stays ARMED",
                   back and self.st() == "ARMED", "SD_REQ=%s S1=%s %s" % (
                       self.inst.named.get("SD_REQ"), self.outs()[0], self.st()))
        r = self.qgc.safety(DISARM)
        self.check("T11 app DISARM after restart -> SAFE",
                   r == 0 and self.wait(lambda: self.st() == "SAFE", 2), "ACK=%s %s" % (r, self.st()))
        self.check("T11 no unexpected fire", self.esp.model.load_on_count == fires_before + 1,
                   str(self.esp.model.load_on_count))

    def t_lux_reboot(self):
        self.log("=== T9 LUX reboot while ARMED (Option A) ===")
        fires_before = self.esp.model.load_on_count
        self.qgc.safety(REQUEST)
        self.qgc.safety(CONFIRM)
        armed = self.wait(lambda: self.st() == "ARMED", 36)
        self.check("T9 ARMED before reboot", armed)
        self.stop_filter()
        self.inst.drop()
        self.sitl.kill()
        self.settle(2)
        self.check("T9 ESP32 holds ARMED with no pulses", self.st() == "ARMED" and self.esp.model.remote_hold,
                   "state=%s hold=%s" % (self.st(), self.esp.model.remote_hold))
        self.esp.model.contact = True
        fired = self.wait(lambda: self.esp.model.load, 1)
        self.esp.model.contact = False
        self.check("T9 contact fires during LUX outage", fired)
        self.wait(lambda: not self.esp.model.load, 1)
        self.inst.sb = SB_UP          # SB up across the reboot must not re-arm later
        self.sitl.start(wipe=False)
        self.inst.connect()
        self.start_filter()
        held = self.wait(lambda: self.inst.named.get("SD_REQ") == 2, 30)
        self.check("T9 after reboot S1 held (boot hold) because ESP32 reports ARMED", held,
                   "SD_REQ=%s S1=%s" % (self.inst.named.get("SD_REQ"), self.outs()[0]))
        self.settle(3)
        self.check("T9 ESP32 still ARMED after LUX reboot", self.st() == "ARMED" and self.outs()[0] == 1500,
                   "state=%s S1=%s" % (self.st(), self.outs()[0]))
        r = self.qgc.safety(DISARM)
        self.check("T9 app DISARM after reboot -> SAFE",
                   r == 0 and self.wait(lambda: self.st() == "SAFE", 2), "ACK=%s %s" % (r, self.st()))
        self.settle(3)
        self.check("T9 SB up since boot (never seen released) does not arm",
                   self.outs()[0] == 1100 and self.st() == "SAFE", "S1=%s %s" % (self.outs()[0], self.st()))
        self.inst.sb = SB_DOWN
        self.check("T9 fire count = only the deliberate contact test",
                   self.esp.model.load_on_count == fires_before + 1, str(self.esp.model.load_on_count))

    def finish(self):
        passed = sum(c["pass"] for c in self.checks)
        self.log("=== %d/%d checks passed ===" % (passed, len(self.checks)))
        (self.results_dir / "sitl_test_results.json").write_text(json.dumps(
            {"passed": passed, "total": len(self.checks), "checks": self.checks}, indent=2))
        self.inst.alive = self.esp.alive = self.qgc.alive = False
        self.stop_filter()
        self.sitl.kill()


if __name__ == "__main__":
    Runner(sys.argv[1], sys.argv[2]).run()
